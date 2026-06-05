# macOS Voice Assistant — Local + Cloud Dual-Mode

A push-to-talk voice assistant for macOS that runs **two interchangeable ways**:

- **local** — fully offline pipeline: `faster-whisper` (STT) → a local LLM via [Ollama](https://ollama.com) → [MeloTTS](https://github.com/myshell-ai/MeloTTS) (speech). Costs nothing, works without internet.
- **live** — real-time cloud pipeline using a single multimodal model (e.g. Google **Gemini Live API**) that does listening + reasoning + speaking with native audio. Best pronunciation and lowest perceived latency; metered and needs internet.

This is a **build guide and a record of the design dead-ends** — so you can reproduce the system, or skip the mistakes I already made.

> Developed and tested on a Mac mini (Apple Silicon). The architecture is general and language-agnostic; the example uses Korean as the UI/voice language, but nothing here is Korean-specific.

**Languages:** English (below) · [한국어](#한국어)

> **This repo includes the full runnable source**, sanitized for public release (no keys, no personal paths). Copy `.env.example` to `.env` and add your own Gemini API key. Install deps with `requirements.txt` (main app) and `requirements-tts.txt` (local TTS server).

---

## What you get

- **Push-to-talk:** press <kbd>Enter</kbd>, speak, press <kbd>Enter</kbd> → spoken reply.
- **One config flag** switches the entire stack between `local` and `live`.
- **Menu-bar app** (no Dock icon) via [`rumps`](https://github.com/jaredks/rumps), packaged with `py2app`.
- A persona/system prompt shared by both modes (short replies, no markdown, current-time injection so "what time is it?" works).

---

## Architecture

### Mode branch

```
launcher → read mode from config
  ├─ "live"  → live entrypoint                         (no extra servers needed)
  └─ "local" → start Ollama (:11434) + MeloTTS server (:11435), then local loop
```

### Live mode data flow

```
[Enter] → mic InputStream (16 kHz / float32, blocksize = 1600 = 0.1 s)
        → callback converts to int16 PCM, hands off to an asyncio.Queue
        → a sender task streams chunks in real time (audio/pcm;rate=16000)
        → [Enter] ends the turn → activity_end
   Live model (native audio, single model does STT + LLM + TTS)
        → 24 kHz PCM reply streamed straight to an OutputStream (gapless playback)
        → bidirectional transcription (what you said / what it said) printed live
   Conversation memory is kept by the session itself — no manual history list.
```

### Local mode data flow

```
[Enter] → record until [Enter]   (sounddevice, 16 kHz mono float32)
        → STT                    (faster-whisper, CPU, int8)
        → LLM                    (Ollama /api/chat, streaming off, last ~3 turns as history)
        → TTS                    (sentence-by-sentence streaming: MeloTTS → cloud TTS → OS `say` fallback)
```

---

## Lessons learned (read this before you build)

These are the non-obvious things that cost me time.

1. **Per-sentence cloud TTS makes the voice wobble.** An early version split the reply into sentences and called a TTS endpoint per sentence to start playback sooner. Problem: each call re-rolls the prosody, so the *timbre drifts between sentences*. Two ways out: a single-speaker **local** TTS (consistent voice, but pronunciation suffers), or a **single streaming session** (Live API) that keeps one voice for the whole turn.

2. **Manual VAD push-to-talk: never send an empty turn.** With automatic activity detection disabled, you wrap speech as `activity_start` … audio … `activity_end`. If you send the start/end markers with **no real audio in between, the server closes the socket (close code 1007)**. Only emit the markers when you actually captured audio.

3. **Stream the mic *while* the user speaks — don't record-then-upload.** Push 0.1 s PCM chunks to the socket as they arrive. By the time the user releases <kbd>Enter</kbd>, the audio is already uploaded, so the first response sound comes back fast. Hand off from the audio callback to your async loop with `loop.call_soon_threadsafe(...)`, and push a **sentinel** after the last chunk so ordering is preserved when you stop the stream.

4. **MeloTTS wants an older Python — give it its own environment.** Its Torch stack pinned to Python **3.11** while the rest of the app ran on **3.13**. Instead of downgrading everything, run MeloTTS as a tiny **resident HTTP server in its own venv** and call it over `localhost`. The main app stays modern; no dependency hell. Warm the model once on startup and serialize inference with a lock.

5. **`faster-whisper` on Apple Silicon = CPU + int8.** Its `ctranslate2` backend does **not** use Metal/GPU. `device="cpu", compute_type="int8"` is the practical sweet spot; `small` is a good size/quality trade-off.

6. **Keep the local LLM warm.** Set a `keep_alive` so the model stays resident between turns (cold reloads kill conversational feel), and turn *off* "thinking"/reasoning output for snappy short replies.

7. **Never hardcode the API key.** Load it from an environment variable or a **git-ignored** `.env`, and never print or log the value. Treat a placeholder `.env` as the committed default.

---

## Technical specs

| Item | Value |
|---|---|
| Live model | a native-audio realtime model via an async live-connect client (e.g. `gemini-*-flash-live`) |
| Live audio | input 16 kHz · 16-bit · PCM · mono / output 24 kHz · 16-bit · PCM · mono |
| Local LLM | Ollama `/api/chat`, a small instruct model, `think: false`, `keep_alive: 30m` |
| STT | `faster-whisper`, size `small`, `device=cpu`, `compute_type=int8`, `beam_size=5` |
| Local TTS | MeloTTS (single speaker), resident HTTP server on `127.0.0.1:11435` (`/health`, `POST /tts {text, speed}`) |
| Mic capture | `sounddevice`, 16 kHz, mono; realtime `blocksize=1600` (0.1 s) |
| Playback | OS player for local files / `sd.OutputStream` for live streaming |

---

## Configuration

A single JSON file is the one source of truth; nothing is hardcoded in code.

```jsonc
{
  "mode": "live",          // live | local
  "voice": "<voice-name>", // cloud voice id (live + cloud-TTS engine)
  "language": "ko",        // ko | en | ja  (STT recognition + reply language)
  "speed": "normal",       // slow | normal | fast (local only)
  "volume": 75,            // system output volume at startup, 0–100
  "stt_model": "small",    // Whisper size (local)
  "brain_model": "<ollama-model>", // local LLM (local mode)
  "tts_engine": "melo"     // local TTS: melo | cloud | say
}
```

In `live` mode only `voice` / `language` matter; the local-only keys are ignored.

---

## Suggested project layout

| File | Role |
|---|---|
| `start.command` (launcher) | applies volume → branches on `mode` → starts live entrypoint, or starts servers + local loop (double-click to run on macOS) |
| `config.py` / `config.json` | central settings (read/write), valid-value lists |
| `live.py` | **entire live mode**: live session, manual VAD, mic/playback streaming, transcripts |
| `loop.py` | **local mode orchestration**: record → STT → LLM → TTS loop |
| `record.py` | mic capture (sounddevice, 16 kHz float32) |
| `stt.py` | `faster-whisper` STT |
| `brain.py` | Ollama call + persona/system prompt + current-time injection |
| `tts.py` | TTS engine switch (melo / cloud / `say`) + sentence streaming + key loading |
| `tts_server.py` | MeloTTS resident server (separate 3.11 environment) |
| `menubar.py` | `rumps` menu-bar app (the `.app` entry point) |
| `setup.py` | `py2app` bundle build (menu-bar only, `LSUIElement`) |

---

## Dependencies & setup

- **Main venv (Python 3.13)** — `google-genai`, `sounddevice`, `numpy`, `rumps`, `faster-whisper`. (HTTP calls to Ollama / local TTS use the standard library.)
- **Second venv (Python 3.11)** — MeloTTS only (`melotts` + Torch). Kept separate because of the Python-version pin.
- **Ollama** running with a small model pulled (e.g. a 3–4B instruct model).
- On first run, Whisper and MeloTTS download their model weights from Hugging Face once and cache them.

---

## Running

```bash
# live mode (default): just needs internet + an API key in the environment / .env
.venv/bin/python live.py

# local mode: start the servers first
ollama serve &                          # with your local model already pulled
.venv-tts/bin/python tts_server.py &    # MeloTTS resident server on :11435
.venv/bin/python loop.py

# unified launcher (auto-branches on `mode`)
./start.command

# build the menu-bar app
.venv/bin/python setup.py py2app -A
```

---

## Cost model (cloud / live mode)

Local mode is **$0**. For the cloud/live mode, native-audio models are billed per token, and audio is far more tokens than text, so use published rates to estimate. As a rough order of magnitude with Gemini Live–class pricing at time of writing:

- audio **in** ≈ \$3 / 1M tokens (≈ \$0.005 / min), audio **out** ≈ \$12 / 1M tokens (≈ \$0.018 / min)
- → on the order of a few cents per minute of back-and-forth conversation.

**Always check the provider's current official pricing** — these numbers move, and audio token accounting differs from text. Set a budget cap on your cloud project; live audio burns rate-limit quota much faster than text.

---

## Key code patterns

Illustrative, cleaned-up snippets of the three things that matter most.

**Manual VAD — only mark a turn if there's real audio:**

```python
async def send_utterance(session, pcm16: bytes, chunk: int = 32000):
    await session.send_realtime_input(activity_start=ActivityStart())
    for i in range(0, len(pcm16), chunk):
        await session.send_realtime_input(
            audio=Blob(data=pcm16[i:i + chunk], mime_type="audio/pcm;rate=16000"))
    await session.send_realtime_input(activity_end=ActivityEnd())
```

**Real-time mic streaming — audio thread → asyncio queue, with a sentinel:**

```python
def callback(indata, frames, time_info, status):       # runs on the audio thread
    pcm = (np.clip(indata[:, 0], -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    loop.call_soon_threadsafe(queue.put_nowait, pcm)    # thread-safe handoff

async def sender():
    started = False
    while True:
        chunk = await queue.get()
        if chunk is SENTINEL:
            break
        if not started:                                 # 'start' right before the first real chunk
            await session.send_realtime_input(activity_start=ActivityStart())
            started = True
        await session.send_realtime_input(
            audio=Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
    if started:                                          # only close the turn if we sent audio
        await session.send_realtime_input(activity_end=ActivityEnd())
```

**Gapless streaming playback — play 24 kHz PCM as it arrives:**

```python
def player(q):
    with sd.OutputStream(samplerate=24000, channels=1, dtype="int16") as out:
        while (item := q.get()) is not None:
            out.write(np.frombuffer(item, dtype="int16").reshape(-1, 1))
```

---

## Reproduction checklist

1. Create two venvs: main (Python 3.13) + MeloTTS (Python 3.11). Install the deps above.
2. Write `config.json` (schema above). Provide the API key via an environment variable or a git-ignored `.env`.
3. **To reproduce live mode only:** `live.py` + `config.py` + the persona prompt + mic capture + the live-connect client are enough.
4. **To also reproduce local mode:** Ollama + a small model, the second venv + MeloTTS, and the resident TTS server.
5. The three traps that will bite you: ① empty live turns → 1007 disconnect (mark turns only with real audio); ② MeloTTS needs its own 3.11 env; ③ `faster-whisper`/`ctranslate2` has no GPU path → CPU/int8.

---

## License

MIT — see [`LICENSE`](LICENSE). Use it however you like; attribution appreciated but not required.

---
---

<a name="한국어"></a>
# macOS 음성 비서 — 로컬 + 클라우드 듀얼 모드

**English:** [English version above](#macos-voice-assistant--local--cloud-dual-mode)

> **이 저장소에는 실행 가능한 전체 소스가 포함**돼 있습니다(공개용으로 정제 — 키·개인 경로 없음). `.env.example`을 `.env`로 복사해 본인 Gemini API 키를 넣으세요. 설치는 `requirements.txt`(메인 앱) + `requirements-tts.txt`(로컬 TTS 서버).

macOS용 푸시투토크 음성 비서. **두 가지 모드로 교체 가능**합니다.

- **local** — 완전 오프라인: `faster-whisper`(STT) → [Ollama](https://ollama.com)의 로컬 LLM → [MeloTTS](https://github.com/myshell-ai/MeloTTS)(음성). 비용 0, 인터넷 불필요.
- **live** — 실시간 클라우드: 하나의 멀티모달 모델(예: Google **Gemini Live API**)이 듣기·생각·말하기를 네이티브 오디오로 처리. 발음이 가장 좋고 체감 지연이 가장 짧음. 과금되고 인터넷 필요.

이 문서는 **구축 가이드이자 막다른 길의 기록**입니다 — 시스템을 그대로 재현하거나, 제가 이미 한 실수를 건너뛰는 데 쓰세요.

> Mac mini(Apple Silicon)에서 개발·검증. 아키텍처는 일반적이고 언어 비종속입니다. 예시는 한국어를 UI/음성 언어로 쓰지만, 한국어에 묶인 부분은 없습니다.

---

## 무엇을 얻나

- **푸시투토크:** <kbd>Enter</kbd> 누르고 말하고 <kbd>Enter</kbd> → 음성으로 답.
- **설정 한 줄**로 전체 스택을 `local` ↔ `live` 전환.
- **메뉴바 앱**(Dock 아이콘 없음) — [`rumps`](https://github.com/jaredks/rumps) + `py2app`.
- 두 모드 공용 페르소나/시스템 프롬프트(짧은 답변, 마크다운 금지, "지금 몇 시?"가 되도록 현재 시각 주입).

---

## 아키텍처

### 모드 분기

```
런처 → 설정에서 mode 읽기
  ├─ "live"  → live 진입점                              (추가 서버 불필요)
  └─ "local" → Ollama(:11434) + MeloTTS 서버(:11435) 기동 후 로컬 루프
```

### live 모드 데이터 흐름

```
[Enter] → 마이크 InputStream (16 kHz / float32, blocksize = 1600 = 0.1초)
        → 콜백이 int16 PCM으로 변환해 asyncio.Queue로 전달
        → sender 태스크가 청크를 실시간 전송 (audio/pcm;rate=16000)
        → [Enter]로 턴 종료 → activity_end
   Live 모델 (네이티브 오디오, 한 모델이 STT + LLM + TTS)
        → 24 kHz PCM 응답을 OutputStream으로 바로 스트리밍 재생(끊김 없음)
        → 양방향 자막(내가 한 말 / 모델이 한 말) 실시간 출력
   대화 맥락은 세션이 자체 유지 — 수동 history 리스트 없음.
```

### local 모드 데이터 흐름

```
[Enter] → [Enter]까지 녹음   (sounddevice, 16 kHz mono float32)
        → STT               (faster-whisper, CPU, int8)
        → LLM               (Ollama /api/chat, 스트리밍 off, 최근 3턴 history)
        → TTS               (문장별 스트리밍: MeloTTS → 클라우드 TTS → OS `say` 폴백)
```

---

## 막다른 길에서 배운 것 (구축 전에 읽으세요)

시간을 잡아먹은, 직관에 안 보이는 것들입니다.

1. **문장별 클라우드 TTS는 목소리가 흔들린다.** 초기 버전은 응답을 문장으로 쪼개 문장마다 TTS를 호출해 재생을 빨리 시작했습니다. 문제는 호출마다 운율이 새로 결정돼 **문장 사이로 음색이 표류**한다는 것. 해결은 둘 중 하나 — 단일 화자 **로컬** TTS(음색 일관, 발음은 손해), 또는 한 턴 내내 한 목소리를 유지하는 **단일 스트리밍 세션**(Live API).

2. **수동 VAD 푸시투토크: 빈 턴을 절대 보내지 마라.** 자동 음성감지를 끄면 발화를 `activity_start` … 오디오 … `activity_end`로 감쌉니다. 그런데 그 사이에 **실제 오디오가 없는데 시작/끝 신호를 보내면 서버가 소켓을 닫습니다(종료 코드 1007).** 실제로 오디오를 캡처했을 때만 신호를 보내세요.

3. **녹음 후 업로드가 아니라, 말하는 동안 마이크를 흘려보내라.** 0.1초 PCM 청크가 들어오는 즉시 소켓으로 전송합니다. 사용자가 <kbd>Enter</kbd>를 떼는 순간 오디오는 이미 다 올라가 있어 첫 응답 소리가 빨라집니다. 오디오 콜백 → 비동기 루프 전달은 `loop.call_soon_threadsafe(...)`로, 마지막 청크 뒤에 **sentinel**을 넣어 스트림 종료 시 순서를 보존하세요.

4. **MeloTTS는 구버전 파이썬을 원한다 — 별도 환경을 줘라.** Torch 스택이 Python **3.11**에 묶여 있는데 나머지 앱은 **3.13**이었습니다. 전부 다운그레이드하는 대신, MeloTTS를 **자기 venv에서 작은 상주 HTTP 서버**로 띄우고 `localhost`로 호출하세요. 본체는 최신 유지, 의존성 지옥 회피. 시작 시 모델을 한 번 워밍업하고 추론은 락으로 직렬화합니다.

5. **Apple Silicon의 `faster-whisper`는 CPU + int8.** 백엔드(`ctranslate2`)는 Metal/GPU를 **쓰지 않습니다.** `device="cpu", compute_type="int8"`가 실용적 최적점이고, 크기는 `small`이 무난합니다.

6. **로컬 LLM을 따뜻하게 유지하라.** `keep_alive`를 줘서 턴 사이에 모델이 상주하게 하고(콜드 리로드는 대화감을 죽임), "thinking"/추론 출력을 *꺼서* 짧은 답을 빠르게.

7. **API 키를 코드에 박지 마라.** 환경변수나 **git에서 제외한** `.env`에서 읽고, 값을 출력/로그하지 마세요. 커밋되는 기본값은 빈 placeholder `.env`로.

---

## 기술 사양

| 항목 | 값 |
|---|---|
| Live 모델 | async live-connect 클라이언트로 붙는 네이티브 오디오 실시간 모델 (예: `gemini-*-flash-live`) |
| Live 오디오 | 입력 16 kHz · 16-bit · PCM · mono / 출력 24 kHz · 16-bit · PCM · mono |
| 로컬 LLM | Ollama `/api/chat`, 소형 instruct 모델, `think: false`, `keep_alive: 30m` |
| STT | `faster-whisper`, size `small`, `device=cpu`, `compute_type=int8`, `beam_size=5` |
| 로컬 TTS | MeloTTS(단일 화자), 상주 HTTP 서버 `127.0.0.1:11435` (`/health`, `POST /tts {text, speed}`) |
| 마이크 캡처 | `sounddevice`, 16 kHz, mono; 실시간 `blocksize=1600` (0.1초) |
| 재생 | 로컬 파일은 OS 플레이어 / live는 `sd.OutputStream` 스트리밍 |

---

## 설정

JSON 파일 하나가 단일 출처입니다. 코드에 값을 하드코딩하지 않습니다.

```jsonc
{
  "mode": "live",          // live | local
  "voice": "<voice-name>", // 클라우드 음성 id (live + 클라우드 TTS 엔진)
  "language": "ko",        // ko | en | ja  (STT 인식 + 응답 언어)
  "speed": "normal",       // slow | normal | fast (local 전용)
  "volume": 75,            // 시작 시 시스템 출력 볼륨 0–100
  "stt_model": "small",    // Whisper 크기 (local)
  "brain_model": "<ollama-model>", // 로컬 LLM (local 모드)
  "tts_engine": "melo"     // 로컬 TTS: melo | cloud | say
}
```

`live` 모드에선 `voice` / `language`만 유효하고 로컬 전용 키는 무시됩니다.

---

## 권장 프로젝트 구성

| 파일 | 역할 |
|---|---|
| `start.command`(런처) | 볼륨 적용 → `mode` 분기 → live 진입점, 또는 서버 기동 + 로컬 루프 (macOS 더블클릭 실행) |
| `config.py` / `config.json` | 중앙 설정(읽기/쓰기), 유효값 목록 |
| `live.py` | **live 모드 전체**: live 세션, 수동 VAD, 마이크/재생 스트리밍, 자막 |
| `loop.py` | **local 모드 오케스트레이션**: 녹음 → STT → LLM → TTS 루프 |
| `record.py` | 마이크 캡처(sounddevice, 16 kHz float32) |
| `stt.py` | `faster-whisper` STT |
| `brain.py` | Ollama 호출 + 페르소나/시스템 프롬프트 + 현재 시각 주입 |
| `tts.py` | TTS 엔진 스위치(melo / cloud / `say`) + 문장 스트리밍 + 키 로딩 |
| `tts_server.py` | MeloTTS 상주 서버(별도 3.11 환경) |
| `menubar.py` | `rumps` 메뉴바 앱(`.app` 진입점) |
| `setup.py` | `py2app` 번들 빌드(메뉴바 전용, `LSUIElement`) |

---

## 의존성 & 셋업

- **메인 venv (Python 3.13)** — `google-genai`, `sounddevice`, `numpy`, `rumps`, `faster-whisper`. (Ollama / 로컬 TTS 호출은 표준 라이브러리.)
- **두 번째 venv (Python 3.11)** — MeloTTS 전용(`melotts` + Torch). 파이썬 버전 핀 때문에 분리.
- **Ollama** 실행 + 소형 모델 pull(예: 3–4B instruct).
- 첫 실행 시 Whisper / MeloTTS가 Hugging Face에서 가중치를 1회 받아 캐시합니다.

---

## 실행

```bash
# live 모드(기본): 인터넷 + 환경변수/.env의 API 키만 있으면 됨
.venv/bin/python live.py

# local 모드: 서버 먼저 기동
ollama serve &                          # 로컬 모델 미리 pull
.venv-tts/bin/python tts_server.py &    # MeloTTS 상주 서버 :11435
.venv/bin/python loop.py

# 통합 런처 (mode 자동 분기)
./start.command

# 메뉴바 앱 빌드
.venv/bin/python setup.py py2app -A
```

---

## 비용 모델 (클라우드 / live 모드)

local 모드는 **$0**. 클라우드/live 모드의 네이티브 오디오 모델은 토큰당 과금되고, 오디오는 텍스트보다 토큰이 훨씬 많으니 공개 단가로 추정하세요. 작성 시점 Gemini Live급 단가 기준 대략:

- 오디오 **입력** ≈ \$3 / 1M 토큰(≈ \$0.005/분), 오디오 **출력** ≈ \$12 / 1M 토큰(≈ \$0.018/분)
- → 대화가 오가는 1분당 몇 센트 수준.

**반드시 제공사의 현재 공식 단가를 확인하세요** — 숫자는 변하고, 오디오 토큰 산정은 텍스트와 다릅니다. 클라우드 프로젝트에 예산 한도를 거세요. live 오디오는 텍스트보다 레이트리밋 한도를 훨씬 빨리 소모합니다.

---

## 핵심 코드 패턴

가장 중요한 세 가지를 정리한 예시 스니펫(영어 주석은 위 English 섹션 참고).

**수동 VAD — 실제 오디오가 있을 때만 턴 신호:**

```python
async def send_utterance(session, pcm16: bytes, chunk: int = 32000):
    await session.send_realtime_input(activity_start=ActivityStart())
    for i in range(0, len(pcm16), chunk):
        await session.send_realtime_input(
            audio=Blob(data=pcm16[i:i + chunk], mime_type="audio/pcm;rate=16000"))
    await session.send_realtime_input(activity_end=ActivityEnd())
```

**실시간 마이크 스트리밍 — 오디오 스레드 → asyncio 큐, sentinel로 순서 보존:**

```python
def callback(indata, frames, time_info, status):       # 오디오 스레드에서 실행
    pcm = (np.clip(indata[:, 0], -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    loop.call_soon_threadsafe(queue.put_nowait, pcm)    # 스레드 세이프 전달

async def sender():
    started = False
    while True:
        chunk = await queue.get()
        if chunk is SENTINEL:
            break
        if not started:                                 # 첫 실제 청크 직전에 'start'
            await session.send_realtime_input(activity_start=ActivityStart())
            started = True
        await session.send_realtime_input(
            audio=Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
    if started:                                          # 보낸 오디오가 있을 때만 턴 종료
        await session.send_realtime_input(activity_end=ActivityEnd())
```

**끊김 없는 스트리밍 재생 — 24 kHz PCM을 도착하는 대로:**

```python
def player(q):
    with sd.OutputStream(samplerate=24000, channels=1, dtype="int16") as out:
        while (item := q.get()) is not None:
            out.write(np.frombuffer(item, dtype="int16").reshape(-1, 1))
```

---

## 재현 체크리스트

1. venv 두 개 생성: 메인(Python 3.13) + MeloTTS(Python 3.11). 위 의존성 설치.
2. `config.json` 작성(위 스키마). API 키는 환경변수나 git 제외 `.env`로 제공.
3. **live 모드만 재현:** `live.py` + `config.py` + 페르소나 프롬프트 + 마이크 캡처 + live-connect 클라이언트면 충분.
4. **local 모드도 재현:** Ollama + 소형 모델, 두 번째 venv + MeloTTS, 상주 TTS 서버.
5. 발목 잡는 함정 3가지: ① 빈 live 턴 → 1007 끊김(실제 오디오가 있을 때만 턴 신호); ② MeloTTS는 3.11 별도 환경; ③ `faster-whisper`/`ctranslate2`는 GPU 경로 없음 → CPU/int8.

---

## 라이선스

MIT — [`LICENSE`](LICENSE) 참고. 자유롭게 사용하세요. 출처 표기는 환영하지만 필수는 아닙니다.
