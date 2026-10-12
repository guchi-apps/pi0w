import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'myroom-api'))
sys.path.insert(0, str(ROOT / 'room-panel'))
import prepare_public_snapshot as snapshot
import switchbot_to_myroom as switchbot
import aircon_to_myroom as aircon
from myroom_client import fetch_latest, MyRoomError

class PublicationTests(unittest.TestCase):
    def test_public_export_retargets_deployment_and_removes_private_reference(self):
        legacy = 'pi0w_' + '260719'
        private_vps = 'm-' + 'guchi/vps'
        text = 'repository=guchi-apps/' + legacy + '\nWorkingDirectory=%h/apps/' + legacy + '\n[' + private_vps + '](https://github.com/' + private_vps + ')'
        exported = snapshot.public_text(text, 'example/public-pi')
        self.assertIn('repository=example/public-pi', exported)
        self.assertIn('WorkingDirectory=%h/apps/public-pi', exported)
        snapshot.audit_text(exported, 'fixture')
        for private in ('https://myroom.' + 'gucchii' + '.com/api/sensor', '192.168.' + '2.149', 'github_' + 'pat_' + 'a' * 30):
            with self.assertRaises(ValueError):
                snapshot.audit_text(private, 'fixture')

    def test_missing_target_fails_before_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(switchbot, 'load_dotenv'), patch.object(sys, 'argv', ['collector']):
            with self.assertRaises(SystemExit) as result:
                switchbot.load_config()
            self.assertEqual(result.exception.code, 2)
        with patch.dict(os.environ, {'AIRCON_EMAIL':'fixture', 'AIRCON_PASSWORD':'fixture'}, clear=True), patch.object(aircon, 'load_dotenv'), patch.object(sys, 'argv', ['collector']):
            with self.assertRaises(SystemExit) as result:
                aircon.load_config()
            self.assertEqual(result.exception.code, 2)
        with patch('myroom_client.requests.get') as get:
            with self.assertRaises(MyRoomError):
                fetch_latest('', '', 1, 10)
            get.assert_not_called()

    def test_png_metadata_removed_pixels_preserved(self):
        def chunk(kind, payload):
            return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)
        image = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1,1,8,2,0,0,0))
        pixels = chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00'))
        end = chunk(b'IEND', b'')
        clean = image + pixels + end
        self.assertEqual(snapshot.clean_png(image + chunk(b'tEXt', b'private metadata') + pixels + end), clean)
        with self.assertRaises(ValueError):
            snapshot.clean_png(clean[:-3])

    def test_snapshot_has_one_commit_no_remote_or_agent_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            source.mkdir()
            (source / 'README.md').write_text('portable')
            (source / 'docs').mkdir()
            (source / 'docs/issuedeck.md').write_text('private operations')
            (source / '.github/workflows').mkdir(parents=True)
            for name in ('ci.yml','agent.yml'):
                (source / '.github/workflows' / name).write_text('fixture')
            subprocess.check_call(['git','init','-q'], cwd=str(source))
            subprocess.check_call(['git','add','.'], cwd=str(source))
            subprocess.check_call(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','first'], cwd=str(source))
            subprocess.check_call(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','--allow-empty','-qm','second'], cwd=str(source))
            destination = snapshot.prepare(source, Path(tmp) / 'public')
            self.assertEqual(subprocess.check_output(['git','rev-list','--count','HEAD'],cwd=str(destination)).strip(),b'1')
            self.assertEqual(subprocess.check_output(['git','remote'],cwd=str(destination)).strip(),b'')
            self.assertFalse((destination / 'docs/issuedeck.md').exists())
            self.assertFalse((destination / '.github/workflows/agent.yml').exists())
            self.assertTrue((destination / '.github/workflows/ci.yml').exists())
            with self.assertRaises(ValueError):
                snapshot.prepare(source, destination)
            (source / 'untracked.env').write_text('local secret')
            with self.assertRaises(ValueError):
                snapshot.prepare(source, Path(tmp) / 'dirty')

if __name__ == '__main__':
    unittest.main()

