#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export PYTHONDONTWRITEBYTECODE=1 MOCK_HARDWARE=1 FAKE_SOURCES=1
# Compile without importing modules or invoking hardware/API entry points.
python3 scripts/check_syntax.py
while IFS= read -r -d '' file; do bash -n "$file"; done < <(find myroom-api room-panel scripts deploy -name '*.sh' -print0)
python3 -m unittest discover -s tests -v

