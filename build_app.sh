#!/bin/bash
# 음성비서.app 빌드 (py2app, 풀 모드) → rename → deep 서명 → 데스크탑 배치.
#
# 풀 모드(=alias 아님): 파이썬 프레임워크를 번들 안에 복사 → 외부 심볼릭 링크 없음
#   → ad-hoc 코드 서명이 깨끗이 됨 → 더블클릭(LaunchServices)으로도 안 죽고 실행됨.
# 내부명은 ASCII 'VoiceAssistant'로 빌드/서명 후 '음성비서.app'으로 rename(서명 안 깨짐).
set -e
cd "$(dirname "$0")"
PY=".venv/bin/python"

echo "▶ 이전 빌드 정리…"
rm -rf build dist

echo "▶ py2app 풀 빌드(수 분 소요 가능)…"
"$PY" setup.py py2app >/tmp/voiceassistant_build.log 2>&1 || { echo "❌ 빌드 실패:"; tail -30 /tmp/voiceassistant_build.log; exit 1; }

echo "▶ 한글 이름으로 rename…"
rm -rf "음성비서.app"
mv "dist/VoiceAssistant.app" "음성비서.app"

echo "▶ deep ad-hoc 서명…"
codesign --force --deep -s - "음성비서.app" 2>&1 | tail -1 || true
if codesign --verify --deep "음성비서.app" 2>/dev/null; then echo "  ✅ 서명 유효"; else echo "  ⚠ 서명 경고(로컬 실행엔 보통 무관)"; fi

echo "▶ 데스크탑 배치(서명 후 복사 → 봉인 보존)…"
rm -rf "$HOME/Desktop/음성비서.app"
cp -R "음성비서.app" "$HOME/Desktop/음성비서.app"

echo "✅ 빌드 완료: 음성비서.app + ~/Desktop/음성비서.app"
