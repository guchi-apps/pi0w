import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'deploy'))
import pi_agent as agent
import controller


def release(version='0.1.0', contents=None, commit='a' * 40):
    files = contents or {'myroom-api/switchbot_to_myroom.py': b'print("fixture")\n', 'myroom-api/requirements.txt': b'requests==2.31.0\n'}
    files = dict(files, **{'version.json': json.dumps({'version':version}).encode()})
    manifest = {'version':version, 'commit':commit, 'architecture':'source-only', 'files':{p:hashlib.sha256(v).hexdigest() for p,v in files.items()}}
    return manifest, files


def archive(manifest, files, extra=None):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as tar:
        for name, data in dict(files, **{'release-manifest.json':json.dumps(manifest).encode()}).items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            tar.addfile(entry, io.BytesIO(data))
        if extra:
            tar.addfile(extra, io.BytesIO(b'x' * extra.size))
    return stream.getvalue()


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / 'state'
        self.state.mkdir()
        self.baseline = self.state / 'baseline/myroom-api'
        self.baseline.mkdir(parents=True)
        (self.baseline / '.env').write_text('MYROOM_API_URL=https://example.invalid/api\n')
        (self.baseline / '.env').chmod(0o600)
        (self.baseline / 'sensors.json').write_text('[{"device_id":1}]')
        (self.baseline / 'history.db').write_bytes(b'unchanged history')
        (self.baseline / 'venv').mkdir()
        (self.baseline / 'venv/marker').write_text('baseline deps')
        self.live = self.root / 'live'
        self.live.symlink_to(self.baseline)
        self.cfg = {'apps':{'myroom-api':{'path':str(self.live), 'services':['switchbot-co2.service']}}}
        self.commands = []
        self.command_patch = patch.object(agent, 'run', side_effect=self.command)
        self.command_patch.start()
        self.addCleanup(self.command_patch.stop)
        self.states = patch.object(agent, 'unit_state', return_value={'LoadState':'loaded','ActiveState':'active','Result':'success','ExecMainStatus':'0'})
        self.states.start()
        self.addCleanup(self.states.stop)
        # Config values and actual health probes are separately verified below; no real service/network.
        self.config_patch = patch.object(agent, 'validate_private_config')
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.health_patch = patch.object(agent, 'health')
        self.health_mock = self.health_patch.start()
        self.addCleanup(self.health_patch.stop)

    def command(self, args, timeout=300, cwd=None):
        self.commands.append(args)
        if args[:3] == ['python3','-m','venv']:
            Path(args[3]).mkdir()
            (Path(args[3]) / 'marker').write_text('new deps')
        return ''

    def test_archive_rejects_corruption_traversal_links_duplicates_and_private_config(self):
        manifest, files = release()
        data = archive(manifest, files)
        self.assertEqual(agent.unpack(data, hashlib.sha256(data).hexdigest())[0], manifest)
        with self.assertRaises(agent.DeployError):
            agent.unpack(data, '0' * 64)
        for name, kind in (('../escape', tarfile.REGTYPE), ('myroom-api/link', tarfile.SYMTYPE), ('myroom-api/.env', tarfile.REGTYPE), ('version.json',tarfile.REGTYPE)):
            extra = tarfile.TarInfo(name)
            extra.type = kind
            extra.linkname = '/etc/passwd' if kind == tarfile.SYMTYPE else ''
            extra.size = 0 if kind == tarfile.SYMTYPE else 1
            bad = archive(manifest, files, extra)
            with self.subTest(name=name), self.assertRaises(agent.DeployError):
                agent.unpack(bad, hashlib.sha256(bad).hexdigest())

    def test_success_noop_and_manual_rollback_preserve_private_files_and_dependencies(self):
        manifest, files = release()
        self.assertEqual(agent.apply(self.cfg, manifest, files, self.state)['status'], 'deployed')
        new = self.live.resolve()
        self.assertNotEqual(new, self.baseline)
        self.assertEqual((self.live / '.env').resolve(), self.baseline / '.env')
        self.assertEqual((self.live / 'history.db').read_bytes(), b'unchanged history')
        self.assertEqual((self.baseline / 'venv/marker').read_text(), 'baseline deps')
        self.assertEqual(new.stat().st_mode & 0o777, 0o755)
        self.commands.clear()
        self.assertEqual(agent.apply(self.cfg, manifest, files, self.state)['status'], 'unchanged')
        self.assertEqual(self.commands, [])
        agent.rollback(self.state)
        self.assertEqual(self.live.resolve(), self.baseline)
        self.assertEqual((self.live / 'venv/marker').read_text(), 'baseline deps')


    def test_dependency_permissions_and_private_umask_restore(self):
        previous = os.umask(0o077)
        try:
            agent.apply(self.cfg, *release(), self.state)
            self.assertEqual((self.live / 'venv').stat().st_mode & 0o777, 0o755)
            self.assertEqual((self.live / 'venv/marker').stat().st_mode & 0o777, 0o644)
            self.assertEqual((self.live / '.env').stat().st_mode & 0o777, 0o600)
            current = os.umask(0o077)
            self.assertEqual(current, 0o077)
        finally:
            os.umask(previous)

    def test_dependency_failure_restores_private_umask(self):
        previous = os.umask(0o077)
        try:
            with patch.object(agent, 'run', side_effect=agent.DeployError('fixture')):
                with self.assertRaises(agent.DeployError):
                    agent.apply(self.cfg, *release(), self.state)
            current = os.umask(0o077)
            self.assertEqual(current, 0o077)
            self.assertEqual(self.live.resolve(), self.baseline)
        finally:
            os.umask(previous)

    def test_dependency_failure_does_not_stop_services_or_change_live(self):
        def fail(args, timeout=300, cwd=None):
            self.command(args, timeout)
            if args[0] == 'nice':
                raise agent.DeployError('dependency_failure')
            return ''
        with patch.object(agent,'run',side_effect=fail):
            with self.assertRaises(agent.DeployError):
                agent.apply(self.cfg, *release(), self.state)
        self.assertEqual(self.live.resolve(), self.baseline)
        self.assertFalse(any(args[0] == 'systemctl' for args in self.commands))
        self.assertFalse((self.state / 'current.json').exists())

    def test_failed_health_rolls_back_source_deps_and_receipt_then_retry_succeeds(self):
        first, files = release()
        agent.apply(self.cfg, first, files, self.state)
        old = self.live.resolve()
        old_receipt = (self.state / 'current.json').read_text()
        changed = dict(files)
        changed.pop('version.json')
        changed['myroom-api/requirements.txt'] = b'requests==2.30.0\n'
        second, files2 = release('0.2.0', changed, 'b' * 40)
        self.health_mock.side_effect = agent.DeployError('service_health')
        with self.assertRaises(agent.DeployError):
            agent.apply(self.cfg, second, files2, self.state)
        self.assertEqual(self.live.resolve(), old)
        self.assertEqual(json.loads((self.state / 'current.json').read_text()), json.loads(old_receipt))
        self.assertFalse((self.state / 'transaction.json').exists())
        self.health_mock.side_effect = None
        self.assertEqual(agent.apply(self.cfg, second, files2, self.state)['version'], '0.2.0')

    def test_interrupted_commit_recovers_both_live_path_and_manifest(self):
        manifest, files = release()
        agent.apply(self.cfg, manifest, files, self.state)
        current = json.loads((self.state / 'current.json').read_text())
        app = self.cfg['apps']['myroom-api']
        agent.write_json(self.state / 'transaction.json', {'apps':{'myroom-api':dict(app, old=str(self.baseline), states={})},'restore_manifest':{}})
        agent.recover(self.state)
        self.assertEqual(self.live.resolve(), self.baseline)
        self.assertEqual(json.loads((self.state / 'current.json').read_text()), {})

    def test_unchanged_dependencies_are_reused_and_only_changed_collector_restarts(self):
        first, files = release()
        agent.apply(self.cfg, first, files, self.state)
        self.commands.clear()
        changed = dict(files)
        changed.pop('version.json')
        changed['myroom-api/switchbot_to_myroom.py'] = b'print("changed")\n'
        second, files2 = release('0.2.0', changed, 'b' * 40)
        agent.apply(self.cfg, second, files2, self.state)
        self.assertFalse(any(args[0] in ('nice','python3') for args in self.commands))
        self.assertFalse(any('aircon-myroom.service' in args for args in self.commands))
        self.assertTrue((self.live / 'venv').is_symlink())

    def test_bootstrap_and_interrupted_bootstrap_restore_existing_install(self):
        self.live.unlink()
        self.baseline.rename(self.live)
        (self.live / 'venv/bin').mkdir()
        (self.live / 'venv/bin/python3').write_text('fixture')
        agent.bootstrap(self.cfg, self.state)
        self.assertTrue(self.live.is_symlink())
        self.assertEqual((self.live / 'sensors.json').read_text(), '[{"device_id":1}]')
        agent.write_json(self.state / 'bootstrap.json', {'path':str(self.live),'old':str(self.baseline),'states':{}})
        agent.recover_bootstrap(self.state)
        self.assertFalse(self.live.is_symlink())
        self.assertTrue((self.live / 'sensors.json').is_file())

    def test_private_config_must_have_real_targets_and_credentials(self):
        self.config_patch.stop()
        with self.assertRaises(agent.DeployError):
            agent.validate_private_config(self.baseline, 'myroom-api', ['switchbot-co2.service'])
        (self.baseline / '.env').write_text('MYROOM_API_URL=https://service.example/api\n')
        agent.validate_private_config(self.baseline, 'myroom-api', ['switchbot-co2.service'])
        with self.assertRaises(agent.DeployError):
            agent.validate_private_config(self.baseline, 'myroom-api', ['aircon-myroom.service'])
        self.config_patch.start()

    def test_health_checks_all_ble_targets_and_rejects_failed_service(self):
        self.health_patch.stop()
        app = self.cfg['apps']['myroom-api']
        agent.health('myroom-api', app, app['services'])
        probes = [args for args in self.commands if '--require-all' in args]
        self.assertEqual(len(probes), 1)
        self.assertNotIn('--dry-run', probes[0])
        with patch.object(agent, 'run', return_value='') as run:
            agent.health('myroom-api', app, app['services'])
            self.assertEqual(run.call_args_list[0][1]['cwd'], str(self.live))
        with patch.object(agent, 'unit_state', return_value={'Result':'exit-code','ExecMainStatus':'1'}), self.assertRaises(agent.DeployError):
            agent.health('myroom-api', app, app['services'])
        self.health_patch.start()



class RoomPanelTests(unittest.TestCase):
    """room-panelをmyroom-apiと並べて配布対象にした場合の挙動（実機は未確認）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / 'state'
        self.state.mkdir()
        self.cfg = {'apps': {}}
        self.baselines = {}
        for name, service in (('myroom-api', 'switchbot-co2.service'), ('room-panel', 'room-panel.service')):
            baseline = self.state / 'baseline' / name
            baseline.mkdir(parents=True)
            (baseline / '.env').write_text('PRIVATE=1\n')
            (baseline / 'venv').mkdir()
            (baseline / 'venv/marker').write_text('baseline deps')
            live = self.root / name
            live.symlink_to(baseline)
            self.baselines[name] = baseline
            self.cfg['apps'][name] = {'path': str(live), 'services': [service]}
        self.commands = []
        for target, kwargs in (
            ('run', {'side_effect': self.command}),
            ('unit_state', {'return_value': {'LoadState': 'loaded', 'ActiveState': 'active', 'Result': 'success', 'ExecMainStatus': '0'}}),
            ('validate_private_config', {}),
        ):
            patcher = patch.object(agent, target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(agent, 'health')
        self.health_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def command(self, args, timeout=300, cwd=None):
        self.commands.append(args)
        return ''

    def contents(self, panel=b'print("panel")\n'):
        return {
            'myroom-api/switchbot_to_myroom.py': b'print("api")\n',
            'myroom-api/requirements.txt': b'requests==2.31.0\n',
            'room-panel/app.py': panel,
            'room-panel/requirements.txt': b'flask==2.2.5\n',
        }

    def test_panel_is_deployed_with_private_config_and_dependencies_preserved(self):
        manifest, files = release(contents=self.contents())
        agent.apply(self.cfg, manifest, files, self.state)
        live = Path(self.cfg['apps']['room-panel']['path'])
        self.assertEqual((live / 'app.py').read_bytes(), b'print("panel")\n')
        self.assertEqual((live / '.env').resolve(), self.baselines['room-panel'] / '.env')

    def test_panel_only_change_restarts_only_panel(self):
        first, files = release(contents=self.contents())
        agent.apply(self.cfg, first, files, self.state)
        self.commands.clear()
        changed = self.contents(b'print("panel 2")\n')
        second, files2 = release('0.2.0', changed, 'b' * 40)
        result = agent.apply(self.cfg, second, files2, self.state)
        self.assertEqual(result['changed_apps'], ['room-panel'])
        flat = [unit for args in self.commands for unit in args]
        self.assertIn('room-panel.service', flat)
        self.assertNotIn('switchbot-co2.service', flat)
        self.assertFalse(any(args[0] in ('nice', 'python3') for args in self.commands))
        self.assertTrue((Path(self.cfg['apps']['room-panel']['path']) / 'venv').is_symlink())

    def test_failed_panel_health_rolls_back_to_previous_panel(self):
        first, files = release(contents=self.contents())
        agent.apply(self.cfg, first, files, self.state)
        live = Path(self.cfg['apps']['room-panel']['path'])
        old = live.resolve()
        second, files2 = release('0.2.0', self.contents(b'print("broken")\n'), 'b' * 40)
        self.health_mock.side_effect = agent.DeployError('panel_health')
        with self.assertRaises(agent.DeployError):
            agent.apply(self.cfg, second, files2, self.state)
        self.assertEqual(live.resolve(), old)
        self.assertEqual((live / 'app.py').read_bytes(), b'print("panel")\n')

    def test_panel_archive_rejects_private_config(self):
        manifest, files = release(contents=self.contents())
        extra = tarfile.TarInfo('room-panel/.env')
        extra.size = 1
        bad = archive(manifest, files, extra)
        with self.assertRaises(agent.DeployError):
            agent.unpack(bad, hashlib.sha256(bad).hexdigest())


class ControllerTests(unittest.TestCase):
    def test_draft_prerelease_or_non_semver_is_never_selected(self):
        for release_info in ({'tag_name':'v0.1.0','draft':True,'published_at':'now'}, {'tag_name':'v0.1.0','prerelease':True,'published_at':'now'}, {'tag_name':'develop','published_at':'now'}, {'tag_name':'v0.1.0'}):
            with patch.object(controller,'api',return_value=release_info), self.assertRaises(controller.DeployError):
                controller.select_release('example/pi')

    def test_download_checks_digest_manifest_tag_and_main_ancestry(self):
        manifest, files = release()
        data = archive(manifest, files)
        digest = hashlib.sha256(data).hexdigest()
        info = {'id':1,'tag_name':'v0.1.0','assets':[{'name':name,'size':100,'digest':'sha256:'+digest if name.endswith('.tar.gz') else None} for name in ('pi0w-v0.1.0.tar.gz','SHA256SUMS','release-manifest.json')]}
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / 'pi0w-v0.1.0.tar.gz').write_bytes(data)
            (dest / 'SHA256SUMS').write_text(digest + '  pi0w-v0.1.0.tar.gz\n')
            (dest / 'release-manifest.json').write_text(json.dumps(manifest))
            with patch.object(controller,'run',return_value=b''), patch.object(controller,'tag_commit',return_value='a'*40), patch.object(controller,'api',return_value={'status':'ahead'}):
                self.assertEqual(controller.validate_download('example/pi', info, dest)[1], digest)
            with patch.object(controller,'run',return_value=b''), patch.object(controller,'tag_commit',return_value='b'*40), self.assertRaises(controller.DeployError):
                controller.validate_download('example/pi', info, dest)
            with patch.object(controller,'run',return_value=b''), patch.object(controller,'tag_commit',return_value='a'*40), patch.object(controller,'api',return_value={'status':'diverged'}), self.assertRaises(controller.DeployError):
                controller.validate_download('example/pi', info, dest)

    def test_failed_remote_apply_is_retried_and_does_not_advance_receipt(self):
        manifest, files = release()
        state = {'version':'0.0.1','last_success_at':'original'}
        release_info = {'id':2,'tag_name':'v0.1.0'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(controller,'select_release',return_value=release_info), patch.object(controller,'validate_download',return_value=(b'fixture','a'*64,manifest)):
            with patch.object(controller,'remote',side_effect=[{'version':'0.0.1'}, controller.DeployError('offline')]), self.assertRaises(controller.DeployError):
                controller.poll({'repository':'example/pi'}, state, Path(tmp))
            self.assertFalse((Path(tmp) / 'initialized').exists())
            self.assertEqual(state['last_success_at'], 'original')
            self.assertEqual(state['version'],'0.0.1')
            with patch.object(controller,'remote',side_effect=[{'version':'0.0.1'},{'status':'deployed'}]):
                controller.poll({'repository':'example/pi'}, state, Path(tmp))
            self.assertEqual(state['version'],'0.1.0')
            self.assertEqual((Path(tmp) / 'initialized').read_text().strip(),'0.1.0')

    def test_cached_verified_release_does_not_download_or_transfer_again(self):
        release_info = {'id':2,'tag_name':'v0.1.0','assets':[]}
        identity = hashlib.sha256(json.dumps([], sort_keys=True).encode()).hexdigest()
        state = {'version':'0.1.0','commit':'a'*40,'archive_sha256':'b'*64,'release_id':2,'asset_identity':identity}
        live = dict(state, needs_apply=False)
        with tempfile.TemporaryDirectory() as tmp, patch.object(controller,'select_release',return_value=release_info), patch.object(controller,'remote',return_value=live) as remote, patch.object(controller,'validate_download') as download, patch.object(controller,'tag_commit',return_value='a'*40):
            self.assertEqual(controller.poll({'repository':'example/pi'}, state, Path(tmp))['status'],'unchanged')
            download.assert_not_called()
            remote.assert_called_once_with({'repository':'example/pi'},'status')

    def test_poll_records_time_result_and_clears_stale_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'state.json').write_text(json.dumps({'status':'failed','failure_reason':'ssh_or_helper_failed','version':'0.1.0','last_success_at':'original'}))
            argv = ['controller','--state-dir',tmp,'poll']
            with patch.object(sys,'argv',argv), patch.object(controller,'load_config',return_value={}), patch.object(controller,'poll',return_value={'status':'unchanged','version':'0.1.0'}):
                self.assertEqual(controller.main(),0)
            state = json.loads((Path(tmp) / 'state.json').read_text())
            self.assertEqual((state['status'],state['failure_reason'],state['last_poll_result'],state['last_poll_version']),('unchanged',None,'unchanged','0.1.0'))
            self.assertEqual(state['last_success_at'],'original')
            self.assertIn('last_poll_at',state)
            with patch.object(sys,'argv',argv), patch.object(controller,'load_config',return_value={}), patch.object(controller,'poll',side_effect=controller.DeployError('offline')):
                self.assertEqual(controller.main(),1)
            state = json.loads((Path(tmp) / 'state.json').read_text())
            self.assertEqual(state['last_poll_result'],'failed:offline')

    def test_manual_rollback_pauses_future_polls(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sys,'argv',['controller','--state-dir',tmp,'rollback']), patch.object(controller,'load_config',return_value={}), patch.object(controller,'remote',return_value={'status':'rolled_back'}):
            self.assertEqual(controller.main(),0)
            state = json.loads((Path(tmp) / 'state.json').read_text())
            self.assertTrue(state['automatic_poll_paused'])
            with patch.object(sys,'argv',['controller','--state-dir',tmp,'poll']), patch.object(controller,'poll') as poll:
                self.assertEqual(controller.main(),1)
                poll.assert_not_called()


    def test_ssh_uses_fixed_helper_and_strict_host_key_checking(self):
        cfg = {'host':'pi.example','user':'pi-user','known_hosts':'/tmp/known','identity_file':'/tmp/key','port':22}
        with patch.object(controller.subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'{"status":"ready"}',b'')) as invoke:
            controller.remote(cfg,'status')
            args = invoke.call_args[0][0]
            self.assertIn('StrictHostKeyChecking=yes', args)
            self.assertIn('BatchMode=yes', args)
            self.assertEqual(args[-1], 'sudo -n /usr/local/sbin/pi0w-deploy')
            self.assertEqual(invoke.call_args[1]['timeout'],2700)

if __name__ == '__main__':
    unittest.main()

