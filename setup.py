"""py2app 빌드 설정 — 음성비서 메뉴바 앱(.app) 생성.

핵심: 손으로 만든 .app(bash→venv python 트램펄린)은 macOS가 'Python'으로 인식해
메뉴바 등록을 안 해줬다. py2app은 정식 C 스텁 런처를 넣어 번들 자신이
앱 신원(com.example.voiceassistant)을 갖게 하므로 더블클릭으로도 메뉴바 아이콘이 뜬다.

빌드:  .venv/bin/python setup.py py2app -A   (alias 모드: 이 맥 전용, 빠름)
       보통은 build_app.sh 가 빌드+rename+서명+데스크탑 배치까지 한 번에 처리.
"""
from setuptools import setup

APP = ["menubar.py"]
OPTIONS = {
    "argv_emulation": False,          # 메뉴바 앱은 반드시 False (True면 멈춤/충돌)
    "iconfile": "icon.icns",
    "packages": ["rumps"],
    "includes": ["config", "tts"],
    "plist": {
        "CFBundleName": "VoiceAssistant",          # 번들/실행파일 내부명은 ASCII (서명 안정성)
        "CFBundleDisplayName": "음성비서",   # Finder/시스템 표시명은 한글
        "CFBundleIdentifier": "com.example.voiceassistant",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1.0",
        "LSUIElement": True,          # Dock 아이콘 없이 메뉴바 전용
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "10.13",
    },
}

setup(
    name="VoiceAssistant",                     # 빌드 산출물명(아스키) → 이후 '음성비서.app'로 rename
    app=APP,
    options={"py2app": OPTIONS},
)
