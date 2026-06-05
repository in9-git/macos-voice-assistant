"""STT: faster-whisper로 음성 → 텍스트.

모델 크기와 인식 언어는 config.json에서 읽는다.
audio 인자는 파일 경로 또는 float32 numpy 배열(16kHz mono) 둘 다 받는다.
ctranslate2는 Metal(GPU)을 못 써서 device='cpu' (M4 CPU로도 충분히 빠름).
"""
import time

import config
from faster_whisper import WhisperModel

_model = None
_model_size = None


def load(size=None):
    """모델 로드(처음이면 HuggingFace에서 자동 다운로드). 로딩 초 반환.
    size 생략 시 config.json의 stt_model 사용."""
    global _model, _model_size
    size = size or config.get("stt_model")
    _model_size = size
    t0 = time.time()
    _model = WhisperModel(size, device="cpu", compute_type="int8")
    return time.time() - t0


def transcribe(audio, language=None):
    """audio: 파일경로 or float32 numpy(16kHz mono) → (텍스트, info).
    language 생략 시 config.json의 language 사용."""
    if _model is None:
        load()
    language = language or config.get("language")
    segments, info = _model.transcribe(audio, language=language, beam_size=5)
    text = "".join(s.text for s in segments).strip()
    return text, info


if __name__ == "__main__":
    import sys
    audio = sys.argv[1] if len(sys.argv) > 1 else "/tmp/voiceassistant_test.aiff"
    size = sys.argv[2] if len(sys.argv) > 2 else None
    print(f"[모델 로딩: {size or config.get('stt_model')}]  (처음이면 다운로드 중…)")
    dt = load(size)
    print(f"로딩 완료 {dt:.1f}s")
    t0 = time.time()
    text, info = transcribe(audio)
    print(f"받아쓰기 결과: {text!r}")
    print(f"감지언어={info.language}({info.language_probability:.2f})  전사={time.time()-t0:.1f}s")
