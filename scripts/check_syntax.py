#!/usr/bin/env python3
"""Syntax check only: does not claim ARMv6 or dependency compatibility."""
import ast
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for directory in ("myroom-api", "room-panel", "scripts", "tests", "deploy"):
    for path in sorted((root / directory).rglob("*.py")):
        if any(part in ("venv", ".venv", "__pycache__") for part in path.parts):
            continue
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        compile(source, str(path), "exec")
print("Python syntax OK (current interpreter; ARMv6 runtime unverified)")

