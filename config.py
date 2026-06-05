"""음성비서 설정 중앙 관리 — 모든 값은 config.json 한 곳에서 읽고 쓴다.

코드에 목소리/속도/언어 같은 값을 하드코딩하지 않는다.
settings.command(더블클릭 메뉴)가 이 모듈로 값을 바꾼다.
"""
import os
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# 외부 파일(config.json, .env, venv 등)을 읽고 쓸 기준 경로.
# py2app(.app) 번들이면 __file__이 번들 내부를 가리키므로, 필요하면
# VOICE_ASSISTANT_HOME 환경변수로 소스 폴더를 가리키게 할 수 있다.
PROJECT_DIR = Path(os.environ.get("VOICE_ASSISTANT_HOME", _HERE))
_PATH = PROJECT_DIR / "config.json"

# 기본값 — config.json이 없거나 일부 키가 빠졌을 때 이 값으로 채운다.
DEFAULTS = {
    "voice": "Kore",          # Gemini 음성 (Kore/Aoede/Leda/Zephyr/Puck …)
    "language": "ko",         # 인식+응답 언어  ko / en / ja
    "speed": "normal",        # 말 속도  slow / normal / fast
    "volume": 50,             # 시작 시 시스템 출력 볼륨 0~100
    "gemini_model": "gemini-2.5-flash-preview-tts",
    "fallback_voice": "Yuna",  # macOS say 음성 (클라우드 실패 시 폴백)
    "stt_model": "small",     # Whisper 크기  tiny/base/small/medium
    "brain_model": "gemma4:e4b",  # ollama 모델 (로컬 모드 두뇌)
    "tts_engine": "melo",     # 로컬 모드 음성 엔진  melo(로컬·빠름·목소리고정) / gemini(클라우드) / say(맥 내장)
    "mode": "live",           # 대화 모드  live(Gemini가 직접 듣고 답함·클라우드) / local(gemma+Whisper+Melo·오프라인)
}

# ── 사람이 고르기 쉬운 보기들 (settings 메뉴가 사용) ──────────────
VOICES = {  # Gemini 음성 → 한 줄 설명
    "Kore": "차분한 여성 (기본)",
    "Aoede": "부드러운 여성",
    "Leda": "밝고 어린 느낌",
    "Zephyr": "차분한 중성",
    "Puck": "활기찬 남성",
    "Charon": "묵직한 남성",
    "Fenrir": "또렷한 남성",
    "Callirrhoe": "온화한 여성",
}
LANGUAGES = {"ko": "한국어", "en": "English", "ja": "日本語"}
SPEEDS = {"slow": "느리게", "normal": "보통", "fast": "빠르게"}
MODES = {  # 대화 모드 → 한 줄 설명 (메뉴/설정용)
    "live": "Live · Gemini 실시간(클라우드)",
    "local": "로컬 · gemma+Melo(오프라인)",
}

# 언어별 폴백(macOS say) 추천 음성
SAY_VOICE_BY_LANG = {"ko": "Yuna", "en": "Samantha", "ja": "Kyoko"}


def load():
    """config.json을 읽어 기본값과 합쳐서 돌려준다 (없는 키는 기본값으로)."""
    cfg = dict(DEFAULTS)
    if _PATH.exists():
        try:
            cfg.update(json.loads(_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass  # 깨진 json이면 기본값으로 동작
    return cfg


def save(cfg):
    """알려진 키만 골라 사람이 읽기 좋은 json으로 저장."""
    clean = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
    _PATH.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return clean


def get(key):
    return load().get(key, DEFAULTS.get(key))


def set_one(key, value):
    """키 하나만 바꿔 저장하고, 저장된 전체 설정을 돌려준다."""
    cfg = load()
    cfg[key] = value
    return save(cfg)
