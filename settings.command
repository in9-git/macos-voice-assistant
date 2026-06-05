#!/bin/bash
# 음성비서 음성 설정 — Finder에서 더블클릭하면 메뉴가 열린다.
cd "$(dirname "$0")"
exec .venv/bin/python settings.py
