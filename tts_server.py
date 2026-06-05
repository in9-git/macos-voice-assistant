"""음성비서 로컬 음성 서버 — MeloTTS(한국어) 모델을 메모리에 상주시킨다.

Ollama처럼 항상 떠 있으면서, 텍스트를 받아 즉시 음성(wav)으로 합성해 돌려준다.
화자가 한 명뿐이라 문장마다 목소리가 바뀌지 않고, 로컬이라 인터넷 왕복이 없다.

반드시 음성 전용 3.11 환경으로 실행:
    .venv-tts/bin/python tts_server.py
포트 11435. 첫 기동 시 한국어 모델을 Hugging Face에서 1회 다운로드(캐시됨).

API:
    GET  /health              → 200 "ok"  (모델 로드 완료 후에만 응답)
    POST /tts  {text, speed}  → audio/wav 바이트   (speed: 배속, 1.0=보통)
"""
import os
import json
import time
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 11435
_TMP = os.path.join(tempfile.gettempdir(), "voiceassistant_melo.wav")
_lock = threading.Lock()          # PyTorch 추론은 직렬화(동시 추론 충돌 방지)

print("[음성서버] MeloTTS 한국어 모델 로딩 중… (첫 기동은 다운로드로 느릴 수 있음)", flush=True)
_t = time.time()
from melo.api import TTS                       # noqa: E402  (무거운 import는 여기서)
_model = TTS(language="KR", device="cpu")
_spk = _model.hps.data.spk2id                  # 한국어는 화자 한 명 {'KR': 0}
_KR = list(_spk.values())[0]
# 워밍업 — 첫 실제 요청의 콜드스타트 제거
try:
    _model.tts_to_file("준비됐어요.", _KR, _TMP, speed=1.0)
except Exception as e:
    print(f"[음성서버] 워밍업 경고: {e}", flush=True)
print(f"[음성서버] 준비 완료 ({time.time() - _t:.1f}초). http://127.0.0.1:{PORT}", flush=True)


def _synth(text, speed):
    with _lock:                                # 한 번에 한 문장만 합성
        _model.tts_to_file(text, _KR, _TMP, speed=speed)
        with open(_TMP, "rb") as f:
            return f.read()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):                 # 액세스 로그 끔
        pass

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/tts":
            self.send_error(404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            text = (req.get("text") or "").strip()
            speed = float(req.get("speed", 1.0))
            if not text:
                self.send_error(400, "empty text")
                return
            wav = _synth(text, speed)
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav)))
            self.end_headers()
            self.wfile.write(wav)
        except Exception as e:
            self.send_error(500, str(e))


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[음성서버] 대기 중… (종료: Ctrl+C)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[음성서버] 종료")
