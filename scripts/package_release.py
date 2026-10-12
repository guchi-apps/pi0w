#!/usr/bin/env python3
"""Prepare source-only release assets; never packages local configuration/venvs."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]

def allowed(path):
    p = Path(path)
    if not p.parts or p.parts[0] not in ("myroom-api", "room-panel"):
        return path == "version.json"
    if any(part in ("venv", ".venv", "__pycache__", ".git") for part in p.parts):
        return False
    if p.name.startswith(".env") and p.name != ".env.example":
        return False
    if p.name in ("sensors.json", "dev.sh") or p.suffix in (".pyc", ".key", ".pem", ".sqlite", ".db"):
        return False
    return True

def package(root=ROOT):
    version = json.loads((root / "version.json").read_text())["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Invalid release version")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(root), universal_newlines=True).strip()
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=str(root)).decode().split("\0")
    files = sorted(path for path in tracked if path and allowed(path))
    if "version.json" not in files or not any(p.startswith("myroom-api/") for p in files):
        raise ValueError("Incomplete source checkout")
    output = root / "dist"
    output.mkdir(exist_ok=True)
    manifest = {
        "version": version, "commit": revision, "architecture": "source-only",
        "deployment": "pending", "hardware_verification": "not_run",
        "deployment_issue": 25,
        "files": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files},
    }
    manifest_path = output / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    archive = output / ("pi0w-v" + version + ".tar.gz")
    with tarfile.open(str(archive), "w:gz") as tar:
        for path in files:
            if (root / path).is_symlink():
                raise ValueError("Symlink is not a release source: " + path)
            tar.add(str(root / path), arcname=path, recursive=False)
        tar.add(str(manifest_path), arcname="release-manifest.json")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "SHA256SUMS").write_text(digest + "  " + archive.name + "\n")
    return archive

if __name__ == "__main__":
    print(package())

