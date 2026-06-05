"""음성비서 음성 루프 (MVP, 푸시투토크).

흐름:  [Enter] → 🎤 녹음 → [Enter] → 📝 Whisper → 🧠 e4b → 🔊 Yuna → 반복
실행:  .venv/bin/python loop.py
종료:  Ctrl+C
"""
import config
import stt
import brain
import tts
from record import record_until_enter, SR


def main():
    cfg = config.load()
    print(f"음성비서 로딩 중… (Whisper {cfg['stt_model']} + {cfg['brain_model']}, 언어 {cfg['language']})")
    stt.load()
    print("준비 완료!  [Enter] 누르고 말하세요.  (종료: Ctrl+C)\n")
    tts.say("음성비서 준비됐어요. 말 걸어 주세요.")

    history = []
    while True:
        try:
            input("──[Enter]── ")
            audio = record_until_enter()
            if audio.size < SR * 0.3:            # 0.3초 미만 = 무시
                print("(너무 짧아요)\n")
                continue

            text, _ = stt.transcribe(audio)
            text = text.strip()
            if not text:
                print("(못 알아들었어요)\n")
                continue
            print(f"🗣️  나      : {text}")

            # "클로드" 호출 감지 — 어려운 작업은 Claude로 승격 (다음 단계에서 연결)
            if "클로드" in text or "클라우드" in text:
                print("   → [클로드 호출 감지 — Claude API 연결은 다음 단계]")

            reply = brain.ask(text, history=history[-6:])  # 최근 3턴 기억
            print(f"🤖  음성비서  : {reply}\n")
            tts.say_stream(reply)   # 문장별 스트리밍: 첫 문장부터 바로 재생

            history += [{"role": "user", "content": text},
                        {"role": "assistant", "content": reply}]
        except KeyboardInterrupt:
            print("\n음성비서를 종료합니다. 안녕!")
            break
        except Exception as e:
            print(f"[오류] {e}\n")


if __name__ == "__main__":
    main()
