"""음성비서 Live 모드 — Gemini Live API가 듣기·생각·말하기를 한 모델로 실시간 처리.

기존 파이프라인(Whisper STT → ollama 두뇌 → TTS)과 달리, 마이크 음성을 그대로
Gemini에 보내고 음성을 돌려받아 재생한다. 대화 맥락은 세션이 자체 유지한다.

  · 푸시투토크:  [Enter] 누르고 말하고 → [Enter] → 답변 음성 재생.  (종료 Ctrl+C)
  · 음성/언어 페르소나는 config.json + brain._system() 을 그대로 사용.
  · ⚠ 클라우드·분당 과금·인터넷 필요. 마이크 음성이 구글로 전송된다.

실행:  .venv/bin/python live.py
API 키는 코드에 넣지 않고 tts._load_key()로 환경/.env에서만 읽는다(값 미출력).
"""
import asyncio
import queue
import threading
import time

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types

import config
import brain
import tts
from record import record_until_enter, SR

OUT_SR = 24000                         # Live 음성 출력은 항상 24kHz
MODEL = "gemini-3.1-flash-live-preview"
_IN_CHUNK = 32000                      # 한 번에 보낼 입력 PCM 바이트(~1초)


def new_client():
    """API 키로 Gemini 클라이언트 생성 (키 값은 절대 출력하지 않음)."""
    return genai.Client(api_key=tts._load_key())


def make_config(cfg):
    """음성·페르소나·푸시투토크(수동 VAD)·양방향 자막을 담은 Live 설정."""
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=cfg["voice"])
            )
        ),
        system_instruction=brain._system(cfg["language"]),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )


def _audio_bytes(response):
    """LiveServerMessage에서 PCM 바이트 추출 (.data 우선, 없으면 parts 파싱)."""
    data = getattr(response, "data", None)
    if data:
        return data
    sc = getattr(response, "server_content", None)
    if sc and getattr(sc, "model_turn", None):
        out = b"".join(
            p.inline_data.data
            for p in (sc.model_turn.parts or [])
            if getattr(p, "inline_data", None) and p.inline_data.data
        )
        return out or None
    return None


def _player_thread(q):
    """큐에서 PCM 청크를 꺼내 도착하는 대로 재생(끊김 없는 스트리밍 재생)."""
    with sd.OutputStream(samplerate=OUT_SR, channels=1, dtype="int16") as out:
        while True:
            item = q.get()
            if item is None:
                break
            out.write(np.frombuffer(item, dtype="int16").reshape(-1, 1))


def float_to_pcm16(audio):
    """float32(-1~1) 마이크 신호 → 16-bit little-endian PCM 바이트."""
    return (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


async def send_audio(session, pcm16):
    """수동 VAD: 발화 시작 → 오디오 청크들 → 발화 끝 신호 전송."""
    await session.send_realtime_input(activity_start=types.ActivityStart())
    for i in range(0, len(pcm16), _IN_CHUNK):
        await session.send_realtime_input(
            audio=types.Blob(data=pcm16[i:i + _IN_CHUNK], mime_type="audio/pcm;rate=16000")
        )
    await session.send_realtime_input(activity_end=types.ActivityEnd())


async def play_response(session):
    """한 턴의 응답을 스트리밍 재생하며 (들은말, 한말, 첫소리지연초)를 돌려준다."""
    q = queue.Queue()
    player = threading.Thread(target=_player_thread, args=(q,), daemon=True)
    player.start()
    heard, said, first = "", "", None
    t0 = time.time()
    try:
        async for response in session.receive():
            b = _audio_bytes(response)
            if b:
                if first is None:
                    first = time.time() - t0
                q.put(b)
            sc = getattr(response, "server_content", None)
            if sc:
                it = getattr(sc, "input_transcription", None)
                if it and getattr(it, "text", None):
                    heard += it.text
                ot = getattr(sc, "output_transcription", None)
                if ot and getattr(ot, "text", None):
                    said += ot.text
                if getattr(sc, "turn_complete", False):
                    break
    finally:
        q.put(None)
        player.join()
    return heard.strip(), said.strip(), first


_BLOCK = 1600                          # 마이크 콜백 블록(0.1초 @16k) = 실시간 전송 단위


async def stream_and_send(session):
    """말하는 동안 마이크를 실시간으로 흘려보낸다. [Enter] 누르면 발화 종료.

    녹음을 다 마친 뒤 통째로 올리지 않고 말하는 즉시 청크를 보내므로, 말을 끝낸
    순간엔 음성이 거의 다 올라가 있어 응답 첫 소리가 빨라진다. (유효 발화면 True)
    """
    loop = asyncio.get_running_loop()
    aq = asyncio.Queue()
    sentinel = object()

    def cb(indata, frames, time_info, status):    # 오디오 스레드 → 큐(스레드세이프)
        pcm = (np.clip(indata[:, 0], -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
        loop.call_soon_threadsafe(aq.put_nowait, pcm)

    async def sender():                            # 큐 → 세션으로 청크 실시간 전송
        started = False
        while True:
            chunk = await aq.get()
            if chunk is sentinel:
                break
            if not started:                        # 첫 실제 청크 직전에 '발화 시작' 신호
                await session.send_realtime_input(activity_start=types.ActivityStart())
                started = True
            await session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
        if started:                                # 보낸 음성이 있을 때만 '발화 끝' 신호
            await session.send_realtime_input(activity_end=types.ActivityEnd())
        return started

    stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                            blocksize=_BLOCK, callback=cb)
    stream.start()
    task = asyncio.create_task(sender())
    try:
        await asyncio.to_thread(input, "🎤 녹음 중 — 다 말하면 [Enter]…")
    finally:
        stream.stop()
        stream.close()
        loop.call_soon_threadsafe(aq.put_nowait, sentinel)   # 마지막 청크 뒤에 끼움(순서 보존)
        started = await task
    return started                                  # 실제 음성이 있었으면 True


async def conversation(session, cfg):
    """푸시투토크 대화 루프 — 말하는 동안 실시간 전송. 사용자가 Ctrl+C 할 때까지 반복."""
    while True:
        await asyncio.to_thread(input, "\n──[Enter] 누르고 말하세요──")
        if not await stream_and_send(session):     # 말하는 동안 실시간 업로드
            print("(소리가 없었어요)")
            continue
        heard, said, first = await play_response(session)
        if heard:
            print(f"🗣️  나      : {heard}")
        if said:
            tail = f"   (첫소리 {first:.2f}s)" if first else ""
            print(f"🤖  음성비서  : {said}{tail}")


async def run():
    cfg = config.load()
    client = new_client()
    live_cfg = make_config(cfg)
    print(f"음성비서 Live 모드 — Gemini가 직접 듣고 답해요 "
          f"(음성 {cfg['voice']}, 언어 {cfg['language']}).")
    print("⚠ 클라우드·분당 과금·인터넷 사용.  [Enter] 눌러 말하고, 끝나면 [Enter].  (종료 Ctrl+C)")
    while True:                                    # 세션이 끊기면 재연결
        try:
            async with client.aio.live.connect(model=MODEL, config=live_cfg) as session:
                await conversation(session, cfg)
                return
        except (KeyboardInterrupt, asyncio.CancelledError, EOFError):
            return                                 # Ctrl+C / Ctrl+D / 입력 종료 → 깔끔히 종료
        except Exception as e:
            print(f"\n[세션 끊김 → 재연결: {type(e).__name__}: {str(e)[:120]}]")
            await asyncio.sleep(1.0)


def main():
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n안녕히 가세요.")


if __name__ == "__main__":
    main()
