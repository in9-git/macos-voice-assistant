"""TTS: 로컬 MeloTTS(한국어) 음성 서버 우선 → Gemini → macOS say 순으로 폴백.

엔진 선택은 config.json의 tts_engine:
  - "melo"   : 로컬 음성 서버(127.0.0.1:11435, .venv-tts의 MeloTTS 상주).
               인터넷 불필요, 화자 한 명이라 목소리 고정, 문장당 ~0.5초로 빠름.
  - "gemini" : 구글 Gemini 클라우드 TTS(품질 좋지만 문장마다 톤이 흔들릴 수 있음).
  - "say"    : macOS 내장 say.
melo/gemini 호출이 안 되면 macOS say로 자동 폴백 → 어떤 경우든 소리는 난다.

설정(목소리/속도/모델 등)은 config.json에서 읽는다 — 하드코딩 안 함.
Gemini API 키는 코드에 절대 넣지 않고 환경변수/.env에서만 읽는다.

■ 문장별 스트리밍(say_stream)
  답을 문장 단위로 쪼개 뒤 문장을 만드는 동안 앞 문장을 먼저 재생 → 첫 소리가 빨리 난다.
  melo는 단일 화자라 문장별로 쪼개도 목소리가 안 바뀐다(순수 이득).
"""
import os
import re
import json
import base64
import wave
import subprocess
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import config

_HERE = Path(__file__).resolve().parent

# ── 로컬 음성 서버(MeloTTS) ──
MELO_BASE = "http://127.0.0.1:11435"
_MELO_SPEED = {"slow": 0.8, "normal": 1.0, "fast": 1.2}   # 배속(1.0=보통, 클수록 빠름)

# ── Gemini 클라우드 ──
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# 동시에 미리 만들 문장 수(앞 문장 재생 중 뒤 문장 준비)
_TTS_WORKERS = 3

# 속도 → Gemini 스타일 문구 / macOS say 속도(wpm)
_STYLE_BASE = "친근하고 자연스러운 대화체로"
_SPEED_STYLE = {
    "slow": "아주 천천히 또박또박 차분하게",
    "normal": "너무 빠르지 않게 편안하게",
    "fast": "활기차고 약간 빠른 템포로",
}
_SPEED_RATE = {"slow": 150, "normal": 190, "fast": 240}


def _style_for(speed):
    tail = _SPEED_STYLE.get(speed, _SPEED_STYLE["normal"])
    return f"{_STYLE_BASE}, {tail} 읽어줘"


def _split_sentences(text):
    """문장 끝부호/줄바꿈으로 나누되, 너무 짧은 조각은 앞 문장에 합친다.

    - ASCII(. ! ?)는 뒤에 공백이 있을 때만 분리(소수점 '3.5' 오분리 방지).
    - CJK(。！？…)는 공백 없이도 분리.
    """
    parts = re.split(r"(?<=[.!?])\s+|(?<=[。！？…])|\n+", text.strip())
    out = []
    for p in (s.strip() for s in parts):
        if not p:
            continue
        if out and len(out[-1]) < 6:
            out[-1] = f"{out[-1]} {p}"
        else:
            out.append(p)
    return out or [text.strip()]


# ── Gemini API 키 로딩 (값은 로그/출력에 절대 노출하지 않음) ──
_ENV_CANDIDATES = (
    config.PROJECT_DIR / ".env",             # 프로젝트 폴더의 .env (git 제외)
)


def _key_from_env_file(path):
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("export "):
            s = s[len("export "):].strip()
        for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            if s.startswith(name + "="):
                v = s.split("=", 1)[1].strip().strip('"').strip("'")
                if v and not v.startswith("여기"):   # placeholder 제외
                    return v
    return ""


def _load_key():
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    for path in _ENV_CANDIDATES:
        v = _key_from_env_file(path)
        if v:
            return v
    return ""


# ── 합성 백엔드들 ──
def _melo_alive():
    """로컬 음성 서버가 떠 있는지 빠르게 확인."""
    try:
        with urllib.request.urlopen(MELO_BASE + "/health", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def _melo_synth(text, speed, out_path):
    """로컬 음성 서버에 한 문장을 보내 wav 바이트를 받아 저장."""
    body = json.dumps({"text": text, "speed": _MELO_SPEED.get(speed, 1.0)}).encode()
    req = urllib.request.Request(
        MELO_BASE + "/tts", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        wav = r.read()
    Path(out_path).write_bytes(wav)
    return out_path


def _gemini_synth(text, key, model, voice, style, out_path):
    """Gemini로 음성을 만들어 out_path(wav)에 저장만(재생은 호출 측)."""
    url = f"{GEMINI_BASE}/{model}:generateContent"
    prompt = f"{style}: {text}"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
            },
        },
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.load(r)
    part = d["candidates"][0]["content"]["parts"][0]["inlineData"]
    pcm = base64.b64decode(part["data"])
    m = re.search(r"rate=(\d+)", part.get("mimeType", ""))
    rate = int(m.group(1)) if m else 24000
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out_path


def _say_fallback(text, voice="Yuna", rate=190):
    subprocess.run(["say", "-v", voice, "-r", str(rate), text])


def _play(path):
    subprocess.run(["afplay", str(path)])


def _active_engine(cfg):
    """설정된 엔진을 쓰되, 못 쓰는 상황이면 say로 자동 강등."""
    engine = cfg.get("tts_engine", "melo")
    if engine == "melo" and not _melo_alive():
        print("[음성서버 미응답 → 이번엔 macOS say로 폴백]")
        return "say"
    if engine == "gemini" and not _load_key():
        return "say"
    return engine


def _synth_one(text, cfg, voice, speed, out_path, engine):
    """엔진별로 한 덩어리를 wav로 합성. 성공 시 out_path 반환, 실패 시 예외."""
    if engine == "melo":
        return _melo_synth(text, speed, out_path)
    key = _load_key()                         # gemini (없으면 위에서 say로 강등됨)
    return _gemini_synth(text, key, cfg["gemini_model"], voice, _style_for(speed), out_path)


def say(text, voice=None, speed=None):
    """한 번에 합성·재생(짧은 문장·미리듣기·인사용). 엔진은 config 기준, 실패 시 say 폴백."""
    text = (text or "").strip()
    if not text:
        return
    cfg = config.load()
    voice = voice or cfg["voice"]
    speed = speed or cfg["speed"]
    engine = _active_engine(cfg)
    if engine in ("melo", "gemini"):
        try:
            out = config.PROJECT_DIR / ".tts_out.wav"
            _synth_one(text, cfg, voice, speed, out, engine)
            _play(out)
            return
        except Exception as e:
            print(f"[{engine} TTS 실패 → say 폴백: {e}]")
    _say_fallback(text, voice=cfg["fallback_voice"], rate=_SPEED_RATE.get(speed, 190))


def say_stream(text, voice=None, speed=None):
    """긴 답을 문장별로 나눠, 뒤 문장을 만드는 동안 앞 문장을 먼저 재생한다."""
    text = (text or "").strip()
    if not text:
        return
    cfg = config.load()
    voice = voice or cfg["voice"]
    speed = speed or cfg["speed"]
    rate = _SPEED_RATE.get(speed, 190)
    engine = _active_engine(cfg)
    if engine == "say":                       # 폴백 상황 — 통째로 say
        _say_fallback(text, voice=cfg["fallback_voice"], rate=rate)
        return

    sents = _split_sentences(text)
    if len(sents) == 1:                       # 한 문장이면 그냥 단발 재생
        say(sents[0], voice=voice, speed=speed)
        return

    def synth(i, s):
        return _synth_one(s, cfg, voice, speed,
                          config.PROJECT_DIR / f".tts_out_{i}.wav", engine)

    # 문장을 동시에(최대 _TTS_WORKERS개) 합성 → 순서대로 재생.
    with ThreadPoolExecutor(max_workers=_TTS_WORKERS) as pool:
        futures = [pool.submit(synth, i, s) for i, s in enumerate(sents)]
        for i, fut in enumerate(futures):
            out = None
            try:
                out = fut.result()
                _play(out)
            except Exception as e:            # 이 문장만 say로 폴백
                print(f"[문장 TTS 실패 → say 폴백: {e}]")
                _say_fallback(sents[i], voice=cfg["fallback_voice"], rate=rate)
            finally:
                if out is not None:
                    try:
                        Path(out).unlink()
                    except OSError:
                        pass


if __name__ == "__main__":
    import sys
    cfg = config.load()
    eng = _active_engine(cfg)
    print(f"[음성 엔진: {eng}]")
    say_stream(" ".join(sys.argv[1:])
               or "안녕하세요, 음성비서입니다. 이제 제 목소리로 더 빠르게 말해요. 어때요, 자연스럽죠?")
