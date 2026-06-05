"""마이크 캡처 (sounddevice, 16kHz mono float32 — Whisper가 원하는 포맷)."""
import sys
import numpy as np
import sounddevice as sd

SR = 16000


def list_devices():
    print(sd.query_devices())


def record_until_enter():
    """[Enter] 누를 때까지 녹음 → float32 numpy(mono)."""
    frames = []

    def cb(indata, n, time_info, status):
        frames.append(indata.copy())

    with sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=cb):
        input("🎤 녹음 중 — 다 말하면 [Enter]…")
    if not frames:
        return np.zeros(0, dtype="float32")
    return np.concatenate(frames).reshape(-1)


def record_fixed(seconds=4.0):
    """고정 시간 녹음(테스트용)."""
    audio = sd.rec(int(seconds * SR), samplerate=SR, channels=1, dtype="float32")
    sd.wait()
    return audio.reshape(-1)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "fixed"
    if arg == "list":
        list_devices()
    else:
        secs = float(arg) if arg.replace(".", "", 1).isdigit() else 4.0
        print(f"[{secs}초 녹음 — 지금 말해보세요…]")
        a = record_fixed(secs)
        rms = float(np.sqrt(np.mean(a ** 2))) if a.size else 0.0
        peak = float(np.max(np.abs(a))) if a.size else 0.0
        print(f"{a.size} 샘플, RMS={rms:.4f}, peak={peak:.4f}")
        print("✅ 소리 잡힘" if peak > 0.005 else "⚠️ 소리 거의 없음 (마이크 권한/입력장치 확인)")
