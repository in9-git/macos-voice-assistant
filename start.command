#!/bin/bash
# 음성비서 실행기 — Finder에서 더블클릭하면 터미널에서 자동 실행됨.
cd "$(dirname "$0")"

# 음소거 해제 + 설정된 볼륨 적용 (소리가 안 나는 사고 방지)
VOL=$(.venv/bin/python -c "import config; print(config.get('volume'))" 2>/dev/null || echo 50)
osascript -e "set volume output muted false" -e "set volume output volume ${VOL:-50}" 2>/dev/null

# 모드 분기 — live: Gemini가 직접 듣고 답함(클라우드) / local: gemma+Whisper+Melo(오프라인)
MODE=$(.venv/bin/python -c "import config; print(config.get('mode'))" 2>/dev/null || echo live)
if [ "$MODE" = "live" ]; then
  echo "음성비서 Live 모드 — Gemini가 직접 듣고 답해요 (클라우드·인터넷 필요)."
  exec .venv/bin/python live.py
fi

# ── 이하 로컬 모드: ollama 두뇌 + Melo 음성 서버 + loop.py ──
# ollama 서버가 떠 있는지 확인, 없으면 켜고 최대 15초 대기
if ! curl -s -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "ollama 서버 켜는 중…"
  open -a Ollama 2>/dev/null || (ollama serve >/tmp/ollama_serve.log 2>&1 &)
  for i in $(seq 1 15); do
    curl -s -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
    sleep 1
  done
fi

# 음성 서버(MeloTTS, 3.11 전용 환경) 떠 있나 확인 — 없으면 백그라운드 기동 후 대기
if ! curl -s -m 1 http://127.0.0.1:11435/health >/dev/null 2>&1; then
  echo "음성 서버 켜는 중… (모델 로딩 몇 초)"
  .venv-tts/bin/python tts_server.py >/tmp/voiceassistant_tts_server.log 2>&1 &
  for i in $(seq 1 30); do
    curl -s -m 1 http://127.0.0.1:11435/health >/dev/null 2>&1 && break
    sleep 1
  done
fi

exec .venv/bin/python loop.py
