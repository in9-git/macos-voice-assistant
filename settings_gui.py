"""voice assistant 설정 창 (tkinter) — 더블클릭 메뉴의 그래픽 버전.

목소리·속도·언어·폴백음성은 드롭다운, 볼륨은 슬라이더.
값은 고르는 즉시 config.json에 저장된다. 미리듣기·대화 시작 버튼 포함.
단독 실행도 되고(메뉴바 앱이 '설정 창 열기'로 띄운다).
"""
import re
import threading
import subprocess
import tkinter as tk
from tkinter import ttk
from pathlib import Path

import config
import tts

HERE = Path(__file__).resolve().parent
START_CMD = HERE / "start.command"

SAMPLE = {
    "ko": "안녕하세요, 음성비서입니다. 이 목소리 어떠세요?",
    "en": "Hi, this is VoiceAssistant. How does this voice sound?",
    "ja": "こんにちは、voice assistantです。この声はいかがですか。",
}


def _say_voices(lang):
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    except Exception:
        return ["Yuna"]
    pref = {"ko": "ko_", "en": "en_", "ja": "ja_"}.get(lang, "")
    names = [m.group(1).strip()
             for line in out.splitlines()
             if (m := re.match(r"^(.+?)\s+([a-z]{2}_[A-Z]{2})", line))
             and (not pref or m.group(2).startswith(pref))]
    return names or ["Yuna"]


class SettingsWindow:
    def __init__(self, root):
        self.root = root
        self.cfg = config.load()
        root.title("voice assistant 설정")
        root.resizable(False, False)
        frm = ttk.Frame(root, padding=22)
        frm.grid()

        # ── 헤더 (아이콘 + 이름) ──
        try:
            self.logo = tk.PhotoImage(file=str(HERE / "icon.png")).subsample(12, 12)
            ttk.Label(frm, image=self.logo).grid(row=0, column=0, padx=(0, 12))
        except Exception:
            self.logo = None
        ttk.Label(frm, text="Voice Assistant",
                  font=("Helvetica", 20, "bold")).grid(
            row=0, column=1, columnspan=2, sticky="w", pady=(0, 14))

        r = 1
        self.voice = self._combo(frm, r, "목소리",
                                 [f"{k} — {v}" for k, v in config.VOICES.items()],
                                 next((f"{k} — {v}" for k, v in config.VOICES.items()
                                       if k == self.cfg["voice"]), self.cfg["voice"]),
                                 self._on_voice); r += 1
        is_live = self.cfg.get("mode", "live") == "live"
        # 속도·폴백음성은 로컬 모드 전용 — Gemini Live는 말속도/say 폴백을 쓰지 않음
        self.speed = None
        if not is_live:
            self.speed = self._combo(frm, r, "속도",
                                     [f"{k} — {v}" for k, v in config.SPEEDS.items()],
                                     f"{self.cfg['speed']} — {config.SPEEDS.get(self.cfg['speed'], '')}",
                                     self._on_speed); r += 1
        self.lang = self._combo(frm, r, "언어",
                                [f"{k} — {v}" for k, v in config.LANGUAGES.items()],
                                f"{self.cfg['language']} — {config.LANGUAGES.get(self.cfg['language'], '')}",
                                self._on_lang); r += 1

        # 볼륨 슬라이더
        ttk.Label(frm, text="볼륨").grid(row=r, column=0, sticky="w", pady=7)
        self.vol = tk.IntVar(value=int(self.cfg["volume"]))
        self.vol_scale = ttk.Scale(frm, from_=0, to=100, variable=self.vol,
                                   length=200, command=self._on_vol_move)
        self.vol_scale.grid(row=r, column=1, sticky="w")
        self.vol_lbl = ttk.Label(frm, text=str(self.vol.get()), width=4)
        self.vol_lbl.grid(row=r, column=2, sticky="w")
        self.vol_scale.bind("<ButtonRelease-1>", self._on_vol_release)
        r += 1

        self.fb = None
        if not is_live:
            self.fb = self._combo(frm, r, "폴백 음성",
                                  _say_voices(self.cfg["language"]),
                                  self.cfg["fallback_voice"], self._on_fb); r += 1

        # 버튼들
        btns = ttk.Frame(frm)
        btns.grid(row=r, column=0, columnspan=3, pady=(18, 0))
        ttk.Button(btns, text="미리듣기", command=self._preview).grid(row=0, column=0, padx=5)
        ttk.Button(btns, text="대화 시작", command=self._start).grid(row=0, column=1, padx=5)
        ttk.Button(btns, text="닫기", command=root.destroy).grid(row=0, column=2, padx=5)
        r += 1

        self.status = ttk.Label(frm, text="", foreground="#3a8a3a")
        self.status.grid(row=r, column=0, columnspan=3, pady=(12, 0))

    def _combo(self, frm, row, label, values, current, handler):
        ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", pady=7)
        cb = ttk.Combobox(frm, state="readonly", width=26, values=values)
        cb.set(current)
        cb.grid(row=row, column=1, columnspan=2, sticky="w")
        cb.bind("<<ComboboxSelected>>", handler)
        return cb

    def _flash(self, msg):
        self.status.config(text=msg)
        self.root.after(1900, lambda: self.status.config(text=""))

    # ── 핸들러 ──
    def _on_voice(self, _):
        k = self.voice.get().split(" — ")[0]
        config.set_one("voice", k)
        self._flash(f"목소리 → {k} 저장")
        self._preview()

    def _on_speed(self, _):
        k = self.speed.get().split(" — ")[0]
        config.set_one("speed", k)
        self._flash("속도 저장")
        self._preview()

    def _on_lang(self, _):
        k = self.lang.get().split(" — ")[0]
        config.set_one("language", k)
        rec = config.SAY_VOICE_BY_LANG.get(k)
        if rec:
            config.set_one("fallback_voice", rec)
        if self.fb is not None:          # 폴백음성 위젯은 로컬 모드에만 존재
            self.fb.config(values=_say_voices(k))
            if rec:
                self.fb.set(rec)
        self._flash(f"언어 → {config.LANGUAGES.get(k, k)} (대화 재시작 후 적용)")

    def _on_fb(self, _):
        config.set_one("fallback_voice", self.fb.get())
        self._flash("폴백 음성 저장")

    def _on_vol_move(self, _):
        self.vol_lbl.config(text=str(self.vol.get()))

    def _on_vol_release(self, _):
        v = int(self.vol.get())
        config.set_one("volume", v)
        subprocess.run(["osascript", "-e", "set volume output muted false",
                        "-e", f"set volume output volume {v}"])
        self._flash(f"볼륨 {v} 적용+저장")

    def _preview(self):
        cfg = config.load()
        text = SAMPLE.get(cfg["language"], SAMPLE["ko"])
        threading.Thread(
            target=lambda: tts.say(text, voice=cfg["voice"], speed=cfg["speed"]),
            daemon=True).start()

    def _start(self):
        subprocess.Popen(["open", str(START_CMD)])
        self._flash("대화 창(터미널)을 띄웠어요")


def main():
    root = tk.Tk()
    SettingsWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
