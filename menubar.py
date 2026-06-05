"""voice assistant 메뉴바 앱 (rumps) — 상단 메뉴바에 마이크 아이콘 상주.

클릭 → 대화 시작 / 목소리·속도·언어·볼륨 즉석 조절 / 미리듣기 / 설정 창 열기.
실행: .venv/bin/python menubar.py  (보통은 음성비서.app 더블클릭)
"""
import subprocess
import threading
from pathlib import Path

import rumps

import config
import tts

HERE = Path(__file__).resolve().parent
# 외부 리소스는 프로젝트 실제 위치 기준 — .app 번들 안에서 실행돼도 정상 동작.
START_CMD = config.PROJECT_DIR / "start.command"
SETTINGS_GUI = config.PROJECT_DIR / "settings_gui.py"
PYTHON = config.PROJECT_DIR / ".venv" / "bin" / "python"

SAMPLE = {
    "ko": "안녕하세요, 음성비서입니다.",
    "en": "Hi, this is VoiceAssistant.",
    "ja": "こんにちは、voice assistantです。",
}
VOL_STEPS = [0, 25, 50, 75, 100]


class VoiceAssistantApp(rumps.App):
    def __init__(self):
        # 메뉴바에 마이크 글리프로 표시(PNG 아이콘 렌더 이슈 회피).
        super().__init__("음성비서", title="🎙", quit_button=None)
        self._build()

    def _build(self):
        cfg = config.load()
        is_live = cfg.get("mode", "live") == "live"
        cur_vol = int(cfg["volume"]) if int(cfg["volume"]) in VOL_STEPS else 50
        mode_menu = self._radio(
            "모드", list(config.MODES.items()),
            cfg.get("mode", "live"), self._pick_mode)
        voice_menu = self._radio(
            "목소리", [(k, f"{k} — {v}") for k, v in config.VOICES.items()],
            cfg["voice"], self._pick_voice)
        speed_menu = self._radio(
            "속도", list(config.SPEEDS.items()),
            cfg["speed"], self._pick_speed)
        lang_menu = self._radio(
            "언어", list(config.LANGUAGES.items()),
            cfg["language"], self._pick_lang)
        vol_menu = self._radio(
            "볼륨", [(v, f"{v}%") for v in VOL_STEPS], cur_vol, self._pick_vol)

        self.menu = [
            rumps.MenuItem("🎙  대화 시작", callback=self.start_chat),
            None,
            mode_menu,
            voice_menu,
            # 속도는 로컬 모드 전용 — Gemini Live는 말속도 파라미터를 받지 않음
            *([] if is_live else [speed_menu]),
            lang_menu, vol_menu,
            None,
            rumps.MenuItem("미리듣기", callback=self.preview),
            rumps.MenuItem("설정 창 열기…", callback=self.open_settings),
            None,
            rumps.MenuItem("종료", callback=rumps.quit_application),
        ]

    def _radio(self, title, options, current, on_pick):
        """라디오식 서브메뉴 — 하나 고르면 형제 체크 해제."""
        menu = rumps.MenuItem(title)
        items = {}
        for key, label in options:
            it = rumps.MenuItem(label, callback=self._cb(key, items, on_pick))
            it.state = 1 if key == current else 0
            menu.add(it)
            items[key] = it
        return menu

    def _cb(self, key, items, on_pick):
        def handler(_sender):
            for k, it in items.items():
                it.state = 1 if k == key else 0
            on_pick(key)
        return handler

    # ── pick 핸들러 ──
    def _pick_voice(self, key):
        config.set_one("voice", key)
        self.preview()

    def _pick_speed(self, key):
        config.set_one("speed", key)
        self.preview()

    def _pick_lang(self, key):
        config.set_one("language", key)
        rec = config.SAY_VOICE_BY_LANG.get(key)
        if rec:
            config.set_one("fallback_voice", rec)
        rumps.notification("음성비서", "언어 변경",
                           f"{config.LANGUAGES.get(key, key)} · 대화 재시작 후 적용")

    def _pick_mode(self, key):
        config.set_one("mode", key)
        rumps.notification("음성비서", "모드 변경",
                           f"{config.MODES.get(key, key)} · 대화 재시작 후 적용")

    def _pick_vol(self, vol):
        config.set_one("volume", vol)
        subprocess.run(["osascript", "-e", "set volume output muted false",
                        "-e", f"set volume output volume {vol}"])

    # ── 액션 ──
    def preview(self, _=None):
        cfg = config.load()
        text = SAMPLE.get(cfg["language"], SAMPLE["ko"])
        threading.Thread(target=lambda: tts.say(text), daemon=True).start()

    def start_chat(self, _):
        subprocess.Popen(["open", str(START_CMD)])

    def open_settings(self, _):
        subprocess.Popen([str(PYTHON), str(SETTINGS_GUI)])


if __name__ == "__main__":
    VoiceAssistantApp().run()
