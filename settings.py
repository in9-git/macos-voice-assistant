"""음성비서 음성 설정 — 더블클릭 메뉴 (settings.command가 이걸 실행).

목소리·속도·볼륨·언어·폴백음성을 번호로 고르고 그 자리에서 미리듣기.
값은 config.json에 저장된다. 코드 수정은 필요 없다.
"""
import re
import subprocess

import config
import tts

SAMPLE = {
    "ko": "안녕하세요, 음성비서입니다. 이 목소리 어떠세요?",
    "en": "Hi, this is VoiceAssistant. How does this voice sound?",
    "ja": "こんにちは、voice assistantです。この声はいかがですか。",
}


def _preview(cfg, voice=None, speed=None):
    text = SAMPLE.get(cfg["language"], SAMPLE["ko"])
    print("   ♪ 미리듣기…")
    try:
        tts.say(text, voice=voice or cfg["voice"], speed=speed or cfg["speed"])
    except Exception as e:
        print(f"   (미리듣기 실패: {e})")


def _apply_volume(vol):
    vol = max(0, min(100, int(vol)))
    subprocess.run(["osascript",
                    "-e", "set volume output muted false",
                    "-e", f"set volume output volume {vol}"])
    return vol


def _mac_say_voices(lang):
    """macOS say 음성 목록에서 현재 언어에 맞는 것만 추린다."""
    try:
        out = subprocess.run(["say", "-v", "?"],
                             capture_output=True, text=True).stdout
    except Exception:
        return []
    pref = {"ko": "ko_", "en": "en_", "ja": "ja_"}.get(lang, "")
    names = []
    for line in out.splitlines():
        m = re.match(r"^(.+?)\s+([a-z]{2}_[A-Z]{2})", line)
        if m and (not pref or m.group(2).startswith(pref)):
            names.append(m.group(1).strip())
    return names


def _choose(title, options, current):
    """options: {key: label} → 번호로 고름. 고른 key 반환(취소 시 None)."""
    keys = list(options)
    print(f"\n  ── {title} ──")
    for i, k in enumerate(keys, 1):
        mark = "   ← 지금" if k == current else ""
        print(f"    {i}) {options[k]}{mark}")
    sel = input("  번호 (Enter=취소): ").strip()
    if sel.isdigit() and 1 <= int(sel) <= len(keys):
        return keys[int(sel) - 1]
    return None


def _status(cfg):
    vdesc = config.VOICES.get(cfg["voice"], cfg["voice"])
    return ("\n" + "=" * 42 +
            "\n  🎙  음성비서 음성 설정"
            f"\n   목소리 : {cfg['voice']} ({vdesc})"
            f"\n   언어   : {config.LANGUAGES.get(cfg['language'], cfg['language'])}"
            f"\n   속도   : {config.SPEEDS.get(cfg['speed'], cfg['speed'])}"
            f"\n   볼륨   : {cfg['volume']}"
            f"\n   폴백   : {cfg['fallback_voice']} (클라우드 실패 시 macOS 음성)"
            "\n" + "=" * 42)


MENU = ("\n  1) 목소리 바꾸기"
        "\n  2) 말 속도"
        "\n  3) 볼륨"
        "\n  4) 언어"
        "\n  5) 폴백 음성 (클라우드 안 될 때 macOS 음성)"
        "\n  6) 지금 설정으로 들어보기"
        "\n  0) 저장하고 나가기")


def main():
    print("음성비서 설정을 엽니다. (값은 고를 때마다 바로 저장돼요)")
    while True:
        cfg = config.load()
        print(_status(cfg))
        print(MENU)
        sel = input("\n선택: ").strip()

        if sel == "1":
            k = _choose("목소리", config.VOICES, cfg["voice"])
            if k:
                _preview(cfg, voice=k)
                if input(f"  '{k}'로 정할까? (y/n): ").strip().lower().startswith("y"):
                    config.set_one("voice", k)
                    print("  ✅ 저장됨")
        elif sel == "2":
            k = _choose("말 속도", config.SPEEDS, cfg["speed"])
            if k:
                _preview(cfg, speed=k)
                if input("  이 속도로 정할까? (y/n): ").strip().lower().startswith("y"):
                    config.set_one("speed", k)
                    print("  ✅ 저장됨")
        elif sel == "3":
            raw = input(f"  볼륨 0~100 입력 (지금 {cfg['volume']}): ").strip()
            if raw.isdigit():
                vv = _apply_volume(raw)
                config.set_one("volume", vv)
                _preview(cfg)
                print(f"  ✅ 볼륨 {vv} 저장+적용됨")
            else:
                print("  (숫자가 아니라 취소했어요)")
        elif sel == "4":
            k = _choose("언어", config.LANGUAGES, cfg["language"])
            if k:
                config.set_one("language", k)
                rec = config.SAY_VOICE_BY_LANG.get(k)
                if rec and rec != cfg["fallback_voice"]:
                    if input(f"  폴백 음성도 {rec}(으)로 바꿀까? (y/n): ").strip().lower().startswith("y"):
                        config.set_one("fallback_voice", rec)
                        print(f"  ✅ 폴백 음성 {rec} 저장")
                print(f"  ✅ 언어 {config.LANGUAGES[k]} 저장됨 (음성비서 다시 켜면 적용)")
        elif sel == "5":
            voices = _mac_say_voices(cfg["language"])
            if not voices:
                print("  (이 언어에 맞는 macOS 음성을 못 찾았어요)")
            else:
                k = _choose("폴백 음성", {nm: nm for nm in voices}, cfg["fallback_voice"])
                if k:
                    config.set_one("fallback_voice", k)
                    print(f"   ♪ {k} 미리듣기…")
                    tts._say_fallback(SAMPLE.get(cfg["language"], SAMPLE["ko"]),
                                      voice=k,
                                      rate=tts._SPEED_RATE.get(cfg["speed"], 190))
                    print("  ✅ 저장됨")
        elif sel == "6":
            _preview(cfg)
        elif sel in ("0", ""):
            print("\n설정을 저장하고 나갑니다. 👋\n")
            break
        else:
            print("  (1~6 사이 번호나 0을 눌러주세요)")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n나갑니다. 👋")
