#!/usr/bin/env bash
# Web UI(LCD/LED操作画面)のデザイン調整用: モックデータでローカル起動する。
# 実ハードウェア(GPIO/I2C)・実MyRoom/uptime-kuma通信は一切行わない。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [[ ! -d venv ]]; then
  python3 -m venv venv
  venv/bin/pip install -r requirements.txt
fi

MOCK_HARDWARE=1 FAKE_SOURCES=1 venv/bin/python3 app.py --debug

