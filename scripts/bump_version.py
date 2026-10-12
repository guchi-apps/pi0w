#!/usr/bin/env python3
"""Write the exact version selected by the shared release workflow."""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def bump(version, root=ROOT):
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError("Expected X.Y.Z semantic version")
    path = root / "version.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    current = tuple(int(x) for x in data["version"].split("."))
    if tuple(int(x) for x in version.split(".")) <= current:
        raise ValueError("Release version must increase")
    data["version"] = version
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    notes = root / ".github" / "release-notes.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("# v" + version + "\n\n" + os.getenv("RELEASE_CHANGELOG", "") +
                     "\n\n" + os.getenv("RELEASE_USAGE", "") +
                     "\n\n実機配布・検証は #25 の記録を確認してください。\n", encoding="utf-8")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 scripts/bump_version.py X.Y.Z")
    bump(sys.argv[1])

