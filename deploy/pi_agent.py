#!/usr/bin/python3
"""Root-owned, fixed-command Pi deployment helper. JSON header + optional tar on stdin."""
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.request

CONFIG = Path('/etc/pi0w-deploy.json')
STATE = Path('/var/lib/pi0w-deploy')
UNITS = {'switchbot-co2.service', 'switchbot-co2.timer', 'aircon-myroom.service', 'aircon-myroom.timer', 'room-panel.service'}
MAX_ARCHIVE = 20 * 1024 * 1024
MAX_SOURCE = 60 * 1024 * 1024

class DeployError(Exception):
    pass

def sync_directory(path):
    descriptor = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

def sync_tree(path):
    directories = []
    for root, _, files in os.walk(str(path), followlinks=False):
        directory = Path(root)
        directories.append(directory)
        for name in files:
            file = directory / name
            if file.is_file() and not file.is_symlink():
                with file.open('rb') as stream:
                    os.fsync(stream.fileno())
    for directory in reversed(directories):
        sync_directory(directory)


def write_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    os.replace(str(temporary), str(path))
    sync_directory(path.parent)

def run(args, timeout=300, cwd=None):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, cwd=cwd, universal_newlines=True)
    if result.returncode:
        # Third-party output can contain credentials or API responses. Never forward it.
        raise DeployError('command_failed:' + Path(args[0]).name)
    return result.stdout.strip()

def unit_state(unit):
    values = run(['systemctl', 'show', unit, '--property=LoadState,ActiveState,Result,ExecMainStatus,UnitFileState,MainPID'])
    return dict(line.split('=', 1) for line in values.splitlines() if '=' in line)

def load_config():
    info = CONFIG.stat()
    if info.st_uid != 0 or info.st_mode & 0o022:
        raise DeployError('unsafe_root_config')
    cfg = json.loads(CONFIG.read_text())
    apps = cfg.get('apps', {})
    if not apps or set(apps) - {'myroom-api', 'room-panel'}:
        raise DeployError('invalid_apps')
    for name, app in apps.items():
        expected = '/opt/myroom-pi' if name == 'myroom-api' else '/opt/room-panel'
        if app['path'] != expected or not app['services'] or set(app['services']) - UNITS or any(not u.endswith('.service') for u in app['services']):
            raise DeployError('invalid_app_config')
        allowed = {'switchbot-co2.service', 'aircon-myroom.service'} if name == 'myroom-api' else {'room-panel.service'}
        if set(app['services']) - allowed:
            raise DeployError('invalid_service_mapping')
    return cfg

def unpack(data, digest):
    if len(data) > MAX_ARCHIVE or not re.fullmatch('[0-9a-f]{64}', digest) or hashlib.sha256(data).hexdigest() != digest:
        raise DeployError('archive_checksum')
    files = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for entry in archive:
            path = Path(entry.name)
            if not entry.isfile() or path.is_absolute() or '..' in path.parts or path.as_posix() != entry.name or entry.name in files:
                raise DeployError('unsafe_archive_entry')
            if entry.name not in ('version.json', 'release-manifest.json'):
                if not path.parts or path.parts[0] not in ('myroom-api', 'room-panel'):
                    raise DeployError('unexpected_source')
                if any(p in ('venv', '.venv', '__pycache__', '.git') for p in path.parts):
                    raise DeployError('runtime_in_archive')
                if (path.name.startswith('.env') and path.name != '.env.example') or path.name == 'sensors.json' or path.suffix in ('.pem', '.key', '.db', '.sqlite', '.pyc'):
                    raise DeployError('local_config_in_archive')
            total += entry.size
            if total > MAX_SOURCE:
                raise DeployError('archive_too_large')
            files[entry.name] = archive.extractfile(entry).read()
    try:
        manifest = json.loads(files['release-manifest.json'].decode())
        version = json.loads(files['version.json'].decode())['version']
    except (KeyError, ValueError):
        raise DeployError('missing_manifest')
    if manifest.get('architecture') != 'source-only' or manifest.get('version') != version or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise DeployError('manifest_version')
    actual = {p: hashlib.sha256(data).hexdigest() for p, data in files.items() if p != 'release-manifest.json'}
    if actual != manifest.get('files') or not re.fullmatch('[0-9a-f]{40}', manifest.get('commit', '')):
        raise DeployError('source_checksum')
    return manifest, files

def replace_link(link, target):
    temporary = link.with_name(link.name + '.pi0w-next')
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    temporary.symlink_to(target, target_is_directory=True)
    os.replace(str(temporary), str(link))
    sync_directory(link.parent)

def timers(services):
    return [s.replace('.service', '.timer') for s in services if s != 'room-panel.service']

def stop(services):
    for unit in timers(services) + services:
        run(['systemctl', 'stop', unit])

def resume(states):
    for unit, state in states.items():
        # oneshot collectors are verified separately, not unnecessarily restarted here.
        if state['ActiveState'] in ('active', 'activating') and unit != 'switchbot-co2.service' and unit != 'aircon-myroom.service':
            run(['systemctl', 'start', unit])

def recover(state=STATE):
    journal = state / 'transaction.json'
    if not journal.exists():
        return
    transaction = json.loads(journal.read_text())
    errors = []
    for name, app in transaction['apps'].items():
        try:
            stop(app['services'])
            replace_link(Path(app['path']), app['old'])
            resume(app['states'])
        except Exception:
            errors.append(name)
    if errors:
        raise DeployError('rollback_failed:' + ','.join(errors))
    if 'restore_manifest' in transaction:
        write_json(state / 'current.json', transaction['restore_manifest'])
    if 'restore_previous' in transaction:
        previous = state / 'previous.json'
        if transaction['restore_previous'] is None:
            if previous.exists():
                previous.unlink()
        else:
            write_json(previous, transaction['restore_previous'])
    journal.unlink()

def recover_bootstrap(state=STATE):
    journal = state / 'bootstrap.json'
    if not journal.exists():
        return
    item = json.loads(journal.read_text())
    path, old = Path(item['path']), Path(item['old'])
    if old.exists():
        if path.is_symlink():
            path.unlink()
        if path.exists():
            raise DeployError('bootstrap_recovery_conflict')
        old.rename(path)
    resume(item['states'])
    journal.unlink()

def bootstrap(cfg, state=STATE):
    """Explicit one-time adoption; leaves existing service definitions/enabled state intact."""
    for name, app in cfg['apps'].items():
        path = Path(app['path'])
        if path.is_symlink():
            if not str(path.resolve()).startswith(str(state.resolve()) + '/'):
                raise DeployError('unexpected_existing_link')
            continue
        if not path.is_dir() or not (path / '.env').is_file() or not (path / 'venv/bin/python3').exists():
            raise DeployError('existing_install_required:' + name)
        states = {unit: unit_state(unit) for unit in timers(app['services']) + app['services']}
        if any(s.get('LoadState') != 'loaded' for s in states.values()):
            raise DeployError('existing_units_required')
        old = state / 'baseline' / name
        old.parent.mkdir(parents=True, exist_ok=True)
        old.parent.chmod(0o755)
        if old.exists():
            raise DeployError('baseline_exists')
        write_json(state / 'bootstrap.json', {'path': str(path), 'old': str(old), 'states': states})
        try:
            stop(app['services'])
            path.rename(old)
            sync_directory(old.parent)
            sync_directory(path.parent)
            path.symlink_to(old, target_is_directory=True)
            resume(states)
            (state / 'bootstrap.json').unlink()
        except BaseException:
            recover_bootstrap(state)
            raise


def app_hashes(manifest, name):
    return {p: h for p, h in manifest.get('files', {}).items() if p.startswith(name + '/') and not p.endswith(('.md', '.example', '/deploy.sh', '/install.sh'))}

def changed_services(name, app, changed):
    if name == 'room-panel':
        return app['services']
    air = {'aircon_to_myroom.py', 'aircloudhome_client.py', 'run-aircon-collector.sh'}
    ble = {'switchbot_to_myroom.py'}
    names = {Path(p).name for p in changed}
    result = []
    for unit in app['services']:
        if ('requirements.txt' in names or not names <= air | ble or
            (unit == 'aircon-myroom.service' and names & air) or
            (unit == 'switchbot-co2.service' and names & ble)):
            result.append(unit)
    return result

def validate_private_config(path, name, services):
    env_file = path / '.env'
    if not env_file.is_file():
        raise DeployError('private_config_missing:' + name)
    values = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line.startswith('export '):
            line = line[7:]
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('\"\'')
    required = set()
    if 'switchbot-co2.service' in services:
        required.add('MYROOM_API_URL')
        if not (path / 'sensors.json').is_file() and not values.get('SWITCHBOT_SENSORS_JSON') and not values.get('SWITCHBOT_MAC') and not values.get('SWITCHBOT_SENSORS_FILE'):
            raise DeployError('sensor_config_missing')
    if 'aircon-myroom.service' in services:
        required.update(('AIRCON_EMAIL', 'AIRCON_PASSWORD', 'MYROOM_AIRCON_API_URL'))
    if 'room-panel.service' in services:
        required.update(('MYROOM_API_URL', 'MYROOM_API_TOKEN'))
        if any(values.get(k, '').lower() in ('1', 'true', 'yes') for k in ('FAKE_SOURCES', 'MOCK_HARDWARE')):
            raise DeployError('production_mock_enabled')
    if any(not values.get(k) or values[k].startswith('#') or 'example.invalid' in values[k] or values[k] == 'your@email.com' for k in required):
        raise DeployError('required_private_setting_missing:' + name)


def health(name, app, services):
    path = Path(app['path'])
    # Validate every configured BLE target and its API POST; the legacy unit permits partial success.
    if 'switchbot-co2.service' in services:
        try:
            run([str(path / 'venv/bin/python3'), str(path / 'switchbot_to_myroom.py'), '--require-all'], timeout=240, cwd=str(path))
        except Exception:
            raise DeployError('sensor_verification_failed')
    for unit in services:
        run(['systemctl', 'reset-failed', unit])
        try:
            run(['systemctl', 'start', unit], timeout=300)
        except Exception:
            raise DeployError('service_start_failed:' + unit)
        result = unit_state(unit)
        if result.get('Result') != 'success' or result.get('ExecMainStatus') != '0':
            raise DeployError('service_health:' + unit)
        if unit == 'room-panel.service':
            # /healthz is only process liveness, not hardware success.
            for attempt in range(10):
                try:
                    with urllib.request.urlopen(app.get('health_url', 'http://127.0.0.1:8080/healthz'), timeout=5) as response:
                        if response.status == 200:
                            live = unit_state(unit)
                            if live.get('ActiveState') != 'active' or live.get('MainPID', '0') == '0':
                                raise DeployError('panel_service_inactive')
                            break
                except Exception:
                    if attempt == 9:
                        raise DeployError('panel_health')
                    time.sleep(1)


def _apply(cfg, manifest, files, state=STATE):
    for app in cfg['apps'].values():
        if not Path(app['path']).is_symlink():
            raise DeployError('bootstrap_required')
    current_path = state / 'current.json'
    current = json.loads(current_path.read_text()) if current_path.exists() else {'files': {}}
    same_source = current.get('commit') == manifest['commit'] and current.get('files') == manifest['files']
    if same_source and all(current.get('deployed_apps', {}).get(name) == app_hashes(manifest, name) and current.get('deployed_services', {}).get(name) == cfg['apps'][name]['services'] for name in cfg['apps']):
        return {'status': 'unchanged', 'version': manifest['version']}
    if current.get('version') and not same_source and tuple(map(int, manifest['version'].split('.'))) <= tuple(map(int, current['version'].split('.'))):
        raise DeployError('version_not_newer')
    pending = {}
    release = state / 'releases' / (manifest['version'] + '-' + manifest['commit'][:12])
    # A failed attempt may have prepared partial files. Use an isolated attempt dir.
    release = release.with_name(release.name + '-' + str(time.time_ns()))
    release.parent.mkdir(parents=True, exist_ok=True)
    release.parent.chmod(0o755)
    release.mkdir(mode=0o755)
    release.chmod(0o755)
    for name, app in cfg['apps'].items():
        new_hashes, old_hashes = app_hashes(manifest, name), current.get('deployed_apps', {}).get(name, {})
        if not new_hashes:
            raise DeployError('missing_app_source:' + name)
        changed = {p for p in set(new_hashes) | set(old_hashes) if new_hashes.get(p) != old_hashes.get(p)}
        if current.get('deployed_services', {}).get(name) != app['services']:
            changed.update(new_hashes)
        if not changed:
            continue
        source = Path(app['path']).resolve()
        if not str(source).startswith(str(state.resolve()) + '/'):
            raise DeployError('unexpected_live_path')
        stage = release / name
        stage.mkdir(mode=0o755)
        stage.chmod(0o755)
        # Keep private config/history/runtime in the existing baseline/release, never copy or delete it.
        managed = {Path(p).parts[1] for p in new_hashes} | {Path(p).parts[1] for p in old_hashes}
        for item in source.iterdir():
            if item.name not in managed and item.name != 'venv':
                (stage / item.name).symlink_to(item.resolve(), target_is_directory=item.is_dir())
        for relative in new_hashes:
            target = stage / Path(relative).relative_to(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            parent = target.parent
            while parent != stage:
                parent.chmod(0o755)
                parent = parent.parent
            target.write_bytes(files[relative])
            target.chmod(0o755 if target.suffix == '.sh' else 0o644)
            if target.suffix == '.py':
                compile(files[relative], relative, 'exec')
        services = changed_services(name, app, changed)
        validate_private_config(stage, name, services)
        requirement_changed = old_hashes.get(name + '/requirements.txt') != new_hashes.get(name + '/requirements.txt')
        if requirement_changed:
            # Only dependency files are public-readable; private config keeps 0600.
            previous_umask = os.umask(0o022)
            try:
                run(['python3', '-m', 'venv', str(stage / 'venv')], timeout=180)
                run(['nice', '-n', '15', str(stage / 'venv/bin/python3'), '-m', 'pip', 'install', '--only-binary=:all:', '--disable-pip-version-check', '--no-cache-dir', '--retries', '2', '--timeout', '30', '-r', str(stage / 'requirements.txt')], timeout=1200)
            except Exception:
                raise DeployError('dependency_update_failed:' + name)
            finally:
                os.umask(previous_umask)
        else:
            (stage / 'venv').symlink_to(source / 'venv', target_is_directory=True)
        sync_tree(stage)
        states = {unit: unit_state(unit) for unit in timers(services) + services}
        if any(s.get('LoadState') != 'loaded' for s in states.values()):
            raise DeployError('unit_missing')
        pending[name] = dict(app, services=services, states=states, old=str(source), new=str(stage))
    deployed_apps = dict(current.get('deployed_apps', {}))
    deployed_apps.update({name: app_hashes(manifest, name) for name in cfg['apps']})
    deployed_services = dict(current.get('deployed_services', {}))
    deployed_services.update({name: cfg['apps'][name]['services'] for name in cfg['apps']})
    if not pending:
        write_json(current_path, dict(manifest, deployed_services=deployed_services, deployed_apps=deployed_apps, last_success_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())))
        return {'status': 'deployed', 'version': manifest['version'], 'changed_apps': [], 'hardware_verification': 'not_run'}
    journal = state / 'transaction.json'
    prior = state / 'previous.json'
    write_json(journal, {'apps': pending, 'restore_manifest': current, 'restore_previous': json.loads(prior.read_text()) if prior.exists() else None})
    try:
        for name, app in pending.items():
            stop(app['services'])
            replace_link(Path(app['path']), app['new'])
        for name, app in pending.items():
            health(name, app, app['services'])
            resume(app['states'])
        previous = {'manifest': current, 'apps': {name: {'path': app['path'], 'old': app['old'], 'services': app['services'], 'states': app['states']} for name, app in pending.items()}}
        write_json(state / 'previous.json', previous)
        write_json(current_path, dict(manifest, deployed_services=deployed_services, deployed_apps=deployed_apps, last_success_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())))
        journal.unlink()
    except BaseException:
        recover(state)
        raise
    return {'status': 'deployed', 'version': manifest['version'], 'changed_apps': sorted(pending), 'hardware_verification': 'BLE_require_all' if any('switchbot-co2.service' in a['services'] for a in pending.values()) else 'not_run'}


def apply(cfg, manifest, files, state=STATE):
    releases = state / 'releases'
    before = set(releases.iterdir()) if releases.exists() else set()
    try:
        return _apply(cfg, manifest, files, state)
    except BaseException:
        # Preserve a failed rollback journal and its source trees for recovery.
        if not (state / 'transaction.json').exists() and releases.exists():
            active = {Path(app['path']).resolve().parent for app in cfg['apps'].values()}
            for candidate in set(releases.iterdir()) - before:
                if candidate not in active and candidate.is_dir() and not candidate.is_symlink():
                    shutil.rmtree(str(candidate))
        raise


def diagnostics(cfg):
    events = {}
    for app in cfg['apps'].values():
        for unit in app['services']:
            output = run(['journalctl', '-u', unit, '-n', '20', '--no-pager', '--output=json'])
            records = []
            for line in output.splitlines():
                try:
                    entry = json.loads(line)
                    # MESSAGE/API bodies can contain credentials; export only metadata.
                    records.append({key: entry[key] for key in ('__REALTIME_TIMESTAMP', 'PRIORITY') if isinstance(entry.get(key), str) and entry[key].isdigit()})
                except ValueError:
                    continue
            events[unit] = records
    return {'status': 'diagnostics', 'log_events': events, 'messages': 'redacted'}


def rollback(state=STATE):
    previous = json.loads((state / 'previous.json').read_text())
    if not previous['apps']:
        raise DeployError('no_previous_app')
    write_json(state / 'transaction.json', {'apps': previous['apps'], 'restore_manifest': previous['manifest']})
    recover(state)
    write_json(state / 'current.json', previous['manifest'])
    (state / 'previous.json').unlink()
    return {'status': 'rolled_back', 'version': previous['manifest'].get('version', 'baseline')}


def main():
    if os.geteuid() != 0:
        raise DeployError('root_required')
    os.umask(0o077)
    STATE.mkdir(mode=0o755, exist_ok=True)
    STATE.chmod(0o755)  # service users must traverse source paths; JSON state remains 0600.
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda *_: (_ for _ in ()).throw(InterruptedError()))
    with (STATE / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        recover_bootstrap()
        recover()
        cfg = load_config()
        header = sys.stdin.buffer.readline(4097)
        if len(header) > 4096:
            raise DeployError('invalid_header')
        request = json.loads(header)
        action = request.get('action')
        if action == 'bootstrap':
            bootstrap(cfg)
            result = {'status': 'bootstrapped'}
        elif action == 'apply':
            if platform.machine() != 'armv6l' or sys.version_info < (3, 7):
                raise DeployError('runtime_requires_armv6_python37')
            data = sys.stdin.buffer.read(MAX_ARCHIVE + 1)
            manifest, files = unpack(data, request.get('sha256', ''))
            manifest['archive_sha256'] = request['sha256']
            result = apply(cfg, manifest, files)
        elif action == 'rollback':
            result = rollback()
        elif action == 'diagnostics':
            result = diagnostics(cfg)
        elif action == 'status':
            current = json.loads((STATE / 'current.json').read_text()) if (STATE / 'current.json').exists() else {}
            result = {'status': 'ready', 'version': current.get('version'), 'commit': current.get('commit'), 'archive_sha256': current.get('archive_sha256'), 'needs_apply': any(current.get('deployed_apps', {}).get(n) != app_hashes(current, n) or current.get('deployed_services', {}).get(n) != cfg['apps'][n]['services'] for n in cfg['apps']), 'last_success_at': current.get('last_success_at'), 'machine': platform.machine(), 'python': platform.python_version(), 'services': {u: unit_state(u) for app in cfg['apps'].values() for u in timers(app['services']) + app['services']}}
        else:
            raise DeployError('invalid_action')
        print(json.dumps(result))

if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        reason = str(exc) if isinstance(exc, DeployError) else type(exc).__name__
        print(json.dumps({'status': 'failed', 'reason': reason}))
        sys.exit(1)

