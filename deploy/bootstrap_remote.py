#!/usr/bin/env python3
"""One-time interactive admin SSH installation; never uses the restricted deployment key."""
import argparse
from pathlib import Path
import re
import shlex
import subprocess
import sys
from controller import DeployError, load_config, remote

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admin-identity', type=Path, help='Existing administrator SSH key (optional; otherwise normal SSH agent/password)')
    args = parser.parse_args()
    cfg = load_config(Path.home() / '.config/pi0w-deploy/config.json')
    common = ['-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=' + cfg['known_hosts'],'-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3']
    if args.admin_identity:
        key = args.admin_identity.expanduser().resolve()
        if not key.is_file():
            raise DeployError('admin_key_missing')
        common += ['-o','IdentitiesOnly=yes','-i',str(key)]
    target = cfg['user'] + '@' + cfg['host']
    ssh = ['ssh'] + common + ['-p',str(cfg['port']),target]
    # Inherit stdin/TTY for existing admin login and sudo prompts; no password is captured.
    result = subprocess.run(ssh + ['mktemp -d /tmp/pi0w-bootstrap-XXXXXXXX'], stdout=subprocess.PIPE, timeout=120)
    if result.returncode:
        raise DeployError('admin_ssh_failed')
    directory = result.stdout.decode().strip()
    if not re.fullmatch(r'/tmp/pi0w-bootstrap-[A-Za-z0-9]{8}', directory):
        raise DeployError('unexpected_remote_directory')
    try:
        # Old Pi OpenSSH supports legacy SCP; use -O so the protocol remains compatible.
        files = [str(ROOT / 'deploy' / f) for f in ('pi_agent.py','install-agent.sh','pi-config.example.json')]
        files.append(cfg['identity_file'] + '.pub')
        copied = subprocess.run(['scp','-O'] + common + ['-P',str(cfg['port'])] + files + [target + ':' + directory + '/'], timeout=180)
        if copied.returncode:
            raise DeployError('bootstrap_transfer_failed')
        command = 'cd ' + shlex.quote(directory) + ' && sudo bash install-agent.sh ' + shlex.quote(cfg['user']) + ' ' + shlex.quote(Path(cfg['identity_file']).name + '.pub')
        installed = subprocess.run(ssh[:-1] + ['-t',target,command], timeout=300)
        if installed.returncode:
            raise DeployError('helper_install_failed')
        # Bootstrap adopts only existing configured services; incomplete installs are refused.
        print(remote(cfg,'bootstrap'))
        print(remote(cfg,'status'))
        print('Bootstrap complete. Review the first published release before enabling the timer.')
    finally:
        subprocess.run(ssh + ['rm -rf -- ' + shlex.quote(directory)], timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc) if isinstance(exc, DeployError) else type(exc).__name__)
        sys.exit(1)

