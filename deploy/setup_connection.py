#!/usr/bin/env python3
"""Interactive SubPC setup; requires a Pi host-key fingerprint checked on its console."""
import json
import os
from pathlib import Path
import re
import tempfile
from controller import DeployError, load_config, run


def main():
    os.umask(0o077)
    directory = Path.home() / '.config/pi0w-deploy'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    config = directory / 'config.json'
    if config.exists():
        raise DeployError('config_exists:inspect_existing_config_instead_of_overwriting')
    host = input('Pi host/IP: ').strip()
    user = input('Pi SSH login user: ').strip()
    port = int(input('SSH port [22]: ').strip() or '22')
    expected = input('Verified Pi Ed25519 host-key fingerprint (SHA256:...): ').strip()
    if any(not re.fullmatch('[A-Za-z0-9_.-]+', value) or value.startswith('-') for value in (host, user)) or not 1 <= port <= 65535:
        raise DeployError('invalid_ssh_address')
    if not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}', expected):
        raise DeployError('invalid_fingerprint')
    key = Path.home() / '.ssh/pi0w-deploy'
    known = Path.home() / '.ssh/pi0w-deploy-known-hosts'
    key.parent.mkdir(mode=0o700, exist_ok=True)
    if known.exists():
        raise DeployError('known_hosts_exists:inspect_before_replacing')
    scan = run(['ssh-keyscan', '-T', '5', '-p', str(port), '-t', 'ed25519', host], timeout=15)
    with tempfile.TemporaryDirectory() as tmp:
        temporary = Path(tmp) / 'known_hosts'
        temporary.write_bytes(scan)
        lines = run(['ssh-keygen', '-lf', str(temporary)], timeout=10).decode().splitlines()
        if not lines or any(len(line.split()) < 2 or line.split()[1] != expected for line in lines):
            raise DeployError('host_key_fingerprint_mismatch')
    if not key.exists():
        run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key), '-C', 'pi0w-deploy'], timeout=30)
    if not key.with_suffix('.pub').is_file():
        raise DeployError('deployment_public_key_missing')
    run(['gh','api','repos/' + 'guchi-apps/pi0w'], timeout=30)
    known.write_bytes(scan)
    known.chmod(0o600)
    cfg = {'repository':'guchi-apps/pi0w','host':host,'user':user,'port':port,'identity_file':str(key),'known_hosts':str(known)}
    config.write_text(json.dumps(cfg, indent=2) + '\n')
    config.chmod(0o600)
    load_config(config)
    print('Private SSH configuration created. No app has been deployed.')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc) if isinstance(exc, DeployError) else type(exc).__name__)
        raise SystemExit(1)

