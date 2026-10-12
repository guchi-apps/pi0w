import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "myroom-api"))
sys.path.insert(0, str(ROOT / "room-panel"))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.update(MOCK_HARDWARE="1", FAKE_SOURCES="1", PYTHON_DOTENV_DISABLED="1")

import switchbot_to_myroom as switchbot
import bump_version
import package_release
import config
from lcd import MockLcdDisplay, create_lcd
from led import LedStatus, create_led_controllers
from led_sources import build_led_sources
from state import StateStore
from web import create_app


class OfflineTests(unittest.TestCase):
    def setUp(self):
        # Test fixtures must never silently contact an API, even when .env exists.
        self.network = patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_ble_payload_and_invalid_packets(self):
        body = bytearray(16)
        body[8], body[9], body[10] = 5, 0x80 | 23, 52
        body[13], body[14] = 3, 0x20
        reading = switchbot.parse_switchbot_payload(bytes(body), "co2")
        self.assertEqual((reading.temperature, reading.humidity, reading.co2), (23.5, 52, 800))
        body[9] = 23
        self.assertEqual(switchbot.parse_switchbot_payload(bytes(body), "co2").temperature, -23.5)
        self.assertIsNone(switchbot.parse_switchbot_payload(b"", "co2"))
        body[13], body[14] = 0, 0
        self.assertIsNone(switchbot.parse_switchbot_payload(bytes(body), "co2"))

    def test_sensor_ids_and_duplicate_rejection(self):
        entries = [
            {"mac": "00:00:00:00:00:01", "device_id": 1, "type": "co2"},
            {"mac": "00:00:00:00:00:02", "device_id": 2, "type": "meter"},
        ]
        sensors = switchbot.parse_sensors_json_payload(entries)
        self.assertEqual([x.device_id for x in sensors], [1, 2])
        entries[1]["device_id"] = 1
        with self.assertRaises(ValueError):
            switchbot.parse_sensors_json_payload(entries)

    def test_api_dry_run_does_not_post(self):
        with patch.object(switchbot.requests, "post", side_effect=AssertionError("Must not post")):
            result = switchbot.post_to_myroom("https://example.invalid", 9,
                                            switchbot.SensorReading(23.5, 52, 800), 1, True)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["payload"]["co2"], 800)

    def test_lcd_and_gpio_mock(self):
        self.assertIsInstance(create_lcd(True, 0x27, 1, False), MockLcdDisplay)
        controllers = create_led_controllers({"led1": 17}, True, False)
        controllers["led1"].apply(LedStatus.ON)
        controllers["led1"].apply(LedStatus.OFF)
        self.assertEqual(LedStatus.BLINK.inverted(), LedStatus.BLINK)

    def test_panel_http_and_state_without_background_workers(self):
        # Disable dotenv explicitly on older python-dotenv too.
        with patch.object(config, "load_dotenv"), patch.object(sys, "argv", ["test"]):
            cfg = config.load_config()
        state = StateStore("myroom", {"led1": "off"}, 5.0, 0.3, 1000)
        sources = build_led_sources(cfg.myroom_stale_threshold_sec, cfg.cpu_alert_threshold_percent)
        app = create_app(cfg, state, sources, ["led1"])
        client = app.test_client()
        self.assertEqual(client.get("/healthz").status_code, 200)
        self.assertEqual(client.get("/").status_code, 200)
        client.post("/mode/system")
        client.post("/all_off/off")
        snapshot = client.get("/api/status").get_json()
        self.assertEqual(snapshot["current_mode"], "system")
        self.assertTrue(snapshot["all_off"])

    def test_version_bump_exact_and_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "version.json").write_text('{"version":"0.1.0"}')
            with patch.dict(os.environ, {"RELEASE_CHANGELOG": "change", "RELEASE_USAGE": "usage"}):
                bump_version.bump("0.2.0", root)
            self.assertEqual(json.loads((root / "version.json").read_text())["version"], "0.2.0")
            self.assertIn("usage", (root / ".github/release-notes.md").read_text())
            with self.assertRaises(ValueError):
                bump_version.bump("0.1.0", root)
            with self.assertRaises(ValueError):
                bump_version.bump("../invalid", root)

    def test_release_archive_excludes_config_and_records_pending(self):
        import tarfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "myroom-api").mkdir()
            (root / "version.json").write_text('{"version":"0.1.0"}')
            for name in ("collector.py", ".env", "sensors.json", ".env.example"):
                (root / "myroom-api" / name).write_text("fixture")
            subprocess.check_call(["git", "init", "-q"], cwd=str(root))
            subprocess.check_call(["git", "add", "."], cwd=str(root))
            subprocess.check_call(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                                   "commit", "-qm", "fixture"], cwd=str(root))
            archive = package_release.package(root)
            with tarfile.open(str(archive)) as tar:
                names = tar.getnames()
                self.assertNotIn("myroom-api/.env", names)
                self.assertNotIn("myroom-api/sensors.json", names)
                self.assertIn("myroom-api/collector.py", names)
                manifest = json.load(tar.extractfile("release-manifest.json"))
            self.assertEqual(manifest["deployment"], "pending")
            self.assertEqual(manifest["hardware_verification"], "not_run")
            self.assertEqual(manifest["version"], "0.1.0")


if __name__ == "__main__":
    unittest.main()

