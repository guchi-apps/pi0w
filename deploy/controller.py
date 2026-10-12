#!/usr/bin/env python3
"""SubPC release poller; never deploys a branch HEAD or a draft release."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

class DeployError(Exception):
    pass

def run(args, timeout=120, data=None):
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise DeployError('command_failed:' + Path(args[0]).name)
    return result.stdout

def api(repo, suffix):
    return json.loads(run(['gh', 'api', 'repos/' + repo + '/' + suffix]).decode())

def version(tag):
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag):
        raise DeployError('invalid_release_tag')
    return tuple(map(int, tag[1:].split('.')))

def select_release(repo):
    release = api(repo, 'releases/latest')
    version(release.get('tag_name', ''))
    if release.get('draft') or release.get('prerelease') or not release.get('published_at'):
        raise DeployError('formal_release_required')
    return release

def tag_commit(repo, tag):
    obj = api(repo, 'git/ref/tags/' + tag)['object']
    for attempt in range(5):
        if obj['type'] == 'commit':
            return obj['sha']
        if obj['type'] != 'tag' or not re.fullmatch('[0-9a-f]{40}', obj['sha']):
            raise DeployError('invalid_tag_object')
        obj = api(repo, 'git/tags/' + obj['sha'])['object']
    raise DeployError('nested_tag_limit')

def validate_download(repo, release, directory):
    tag = release['tag_name']
    name = 'pi0w-' + tag + '.tar.gz'
    assets = {item['name']: item for item in release.get('assets', [])}
    if len(assets) != len(release.get('assets', [])) or not {name, 'SHA256SUMS', 'release-manifest.json'} <= set(assets):
        raise DeployError('release_assets_incomplete')
    for file in (name, 'SHA256SUMS', 'release-manifest.json'):
        if assets[file].get('size', 0) > 20 * 1024 * 1024:
            raise DeployError('release_asset_too_large')
        run(['gh', 'release', 'download', tag, '--repo', repo, '--dir', str(directory), '--pattern', file], timeout=300)
    archive = (directory / name).read_bytes()
    digest = hashlib.sha256(archive).hexdigest()
    checksums = (directory / 'SHA256SUMS').read_text().splitlines()
    matching = [line.split() for line in checksums if len(line.split()) == 2 and line.split()[1].lstrip('*') == name]
    if len(matching) != 1 or matching[0][0] != digest:
        raise DeployError('archive_checksum')
    if assets[name].get('digest') and assets[name]['digest'] != 'sha256:' + digest:
        raise DeployError('github_asset_checksum')
    # Shared validation runs identically on the subPC and Pi.
    from pi_agent import unpack
    manifest, _ = unpack(archive, digest)
    if manifest != json.loads((directory / 'release-manifest.json').read_text()) or manifest['version'] != tag[1:]:
        raise DeployError('release_manifest_mismatch')
    sha = tag_commit(repo, tag)
    if manifest['commit'] != sha:
        raise DeployError('tag_source_mismatch')
    relation = api(repo, 'compare/' + sha + '...main')
    if relation.get('status') not in ('ahead', 'identical'):
        raise DeployError('release_not_in_main')
    return archive, digest, manifest

def load_config(path):
    info = path.stat()
    if info.st_mode & 0o077:
        raise DeployError('config_requires_mode_0600')
    cfg = json.loads(path.read_text())
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', cfg.get('repository', '')):
        raise DeployError('invalid_repository')
    for field in ('host', 'user'):
        value = cfg.get(field, '')
        if not re.fullmatch('[A-Za-z0-9_.-]+', value) or value.startswith('-'):
            raise DeployError('invalid_ssh_' + field)
    for field in ('identity_file', 'known_hosts'):
        value = Path(cfg[field]).expanduser().resolve()
        if not value.is_file():
            raise DeployError('missing_' + field)
        if field == 'identity_file' and value.stat().st_mode & 0o077:
            raise DeployError('unsafe_identity_permissions')
        cfg[field] = str(value)
    port = cfg.get('port', 22)
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise DeployError('invalid_ssh_port')
    cfg['port'] = port
    return cfg

def remote(cfg, action, archive=b'', digest=''):
    data = (json.dumps({'action': action, 'sha256': digest}) + '\n').encode() + archive
    args = ['ssh', '-F', '/dev/null', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3', '-o', 'UserKnownHostsFile=' + cfg['known_hosts'], '-i', cfg['identity_file'], '-p', str(cfg['port']), cfg['user'] + '@' + cfg['host'], 'sudo -n /usr/local/sbin/pi0w-deploy']
    # Parse the helper result even on nonzero exit; propagate only its controlled reason.
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2700)
    try:
        response = json.loads(result.stdout.decode())
    except (ValueError, UnicodeError):
        raise DeployError('ssh_or_helper_failed')
    if result.returncode or response.get('status') == 'failed':
        reason = response.get('reason', 'remote_failure')
        if not re.fullmatch('[A-Za-z0-9_:,.-]{1,120}', reason):
            reason = 'remote_failure'
        raise DeployError(reason)
    return response

def save(path, state):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    temporary.chmod(0o600)
    os.replace(str(temporary), str(path))

def poll(cfg, state, state_dir):
    release = select_release(cfg['repository'])
    tag = release['tag_name']
    # Do not trust local receipt after a manual rollback or interrupted remote operation.
    live = remote(cfg, 'status')
    if live.get('version') and version(tag) < version('v' + live['version']):
        raise DeployError('automatic_downgrade_refused')
    asset_identity = hashlib.sha256(json.dumps([{k: item.get(k) for k in ('id', 'name', 'size', 'updated_at', 'digest')} for item in release.get('assets', [])], sort_keys=True).encode()).hexdigest()
    if (state.get('release_id') == release['id'] and state.get('version') == tag[1:]
            and state.get('asset_identity') == asset_identity and live.get('version') == tag[1:]
            and live.get('commit') == state.get('commit') and live.get('archive_sha256') == state.get('archive_sha256')
            and live.get('archive_sha256') and not live.get('needs_apply', True)):
        if tag_commit(cfg['repository'], tag) != state['commit']:
            raise DeployError('published_tag_mutated')
        return {'status': 'unchanged', 'version': tag[1:]}
    with tempfile.TemporaryDirectory(prefix='pi0w-release-') as tmp:
        archive, digest, manifest = validate_download(cfg['repository'], release, Path(tmp))
        if state.get('version') == manifest['version'] and state.get('archive_sha256') not in (None, digest):
            raise DeployError('published_release_mutated')
        result = remote(cfg, 'apply', archive, digest)
    if result.get('status') not in ('deployed', 'unchanged'):
        raise DeployError('unexpected_apply_result')
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state.update(status=result['status'], version=manifest['version'], commit=manifest['commit'], release_id=release['id'], asset_identity=asset_identity, archive_sha256=digest, last_success_at=now, failure_reason=None, remote=result)
    save(state_dir / 'state.json', state)
    marker = state_dir / 'initialized'
    marker.write_text(manifest['version'] + '\n')
    marker.chmod(0o600)
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path.home() / '.config/pi0w-deploy/config.json')
    parser.add_argument('--state-dir', type=Path, default=Path.home() / '.local/state/pi0w-deploy')
    parser.add_argument('action', choices=('poll', 'status', 'rollback', 'bootstrap', 'resume', 'diagnostics'))
    args = parser.parse_args()
    os.umask(0o077)
    args.state_dir.mkdir(parents=True, exist_ok=True)
    args.state_dir.chmod(0o700)
    with (args.state_dir / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = args.state_dir / 'state.json'
        state = json.loads(path.read_text()) if path.exists() else {}
        try:
            cfg = load_config(args.config)
            if args.action == 'resume':
                state.update(automatic_poll_paused=False)
                save(path, state)
                response = {'status': 'resumed'}
            elif args.action == 'poll':
                if state.get('automatic_poll_paused'):
                    raise DeployError('automatic_poll_paused_after_rollback')
                response = poll(cfg, state, args.state_dir)
            else:
                response = remote(cfg, args.action)
                if args.action == 'rollback':
                    state.update(status='rolled_back', automatic_poll_paused=True)
                    save(path, state)
            print(json.dumps(response))
        except Exception as exc:
            reason = str(exc) if isinstance(exc, DeployError) else type(exc).__name__
            state.update(status='failed', failure_reason=reason, last_attempt_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
            save(path, state)
            print(json.dumps({'status': 'failed', 'reason': reason}))
            return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())

