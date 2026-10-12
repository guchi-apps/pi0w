"""センサーごとの取得状況ファイル（StatusHub へ送る。guchi-apps/status-hub#581）のテスト。

BLE と MyRoom には触れない（スキャンと送信を差し替える）。実行:
  python3 -m unittest discover -s tests   # scripts/verify.sh・CI と同じ
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "myroom-api"))

import requests

import switchbot_to_myroom as collector

LIVING = {"mac": "AA:AA:AA:AA:AA:AA", "device_id": 2, "name": "リビング", "type": "co2"}
OUTDOOR = {"mac": "BB:BB:BB:BB:BB:BB", "device_id": 4, "name": "屋外", "type": "meter"}
READING = collector.SensorReading(temperature=21.5, humidity=40, co2=600)


class SensorStatusTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        root = Path(self.dir.name)
        self.status = root / "state" / "sensor-status.tsv"
        sensors = root / "sensors.json"
        sensors.write_text(json.dumps([LIVING, OUTDOOR]), encoding="utf-8")
        env = {
            # 送信先の既定値は持たない（公開準備）ので明示する。送信自体は差し替えてあり、外へは出ない
            "MYROOM_API_URL": "https://myroom.example.invalid/api/sensor",
            "SWITCHBOT_SENSORS_FILE": str(sensors),
            "SENSOR_STATUS_FILE": str(self.status),
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        # load_dotenv が手元の .env を読まないようにする
        dotenv = mock.patch.object(collector, "load_dotenv", lambda: None)
        dotenv.start()
        self.addCleanup(dotenv.stop)

    def run_main(self, readings, post=None, now=1_800_000_000, argv=()):
        scan = mock.patch.object(
            collector,
            "scan_switchbot_co2_btmon_multi",
            side_effect=readings if isinstance(readings, Exception) else None,
            return_value=readings,
        )
        poster = mock.patch.object(collector, "post_to_myroom", side_effect=post or (lambda **_: {"ok": True}))
        clock = mock.patch.object(collector.time, "time", return_value=now)
        with scan, poster, clock, mock.patch.object(sys, "argv", ["collector", *argv]):
            return collector.main()

    def rows(self):
        return [line.split("\t") for line in self.status.read_text(encoding="utf-8").splitlines()]

    def test_partial_success_keeps_exit_code_but_records_each_sensor(self):
        code = self.run_main({"aa:aa:aa:aa:aa:aa": READING})
        self.assertEqual(code, 0)
        self.assertEqual(
            self.rows(),
            [
                ["リビング", "1800000000", "1800000000", "success"],
                ["屋外", "1800000000", "0", "not_found"],
            ],
        )

    def test_failure_keeps_previous_success_time(self):
        self.run_main({"aa:aa:aa:aa:aa:aa": READING, "bb:bb:bb:bb:bb:bb": READING}, now=1_800_000_000)
        self.run_main({"aa:aa:aa:aa:aa:aa": READING}, now=1_800_000_300)
        self.assertEqual(
            self.rows(),
            [
                ["リビング", "1800000300", "1800000300", "success"],
                ["屋外", "1800000300", "1800000000", "not_found"],
            ],
        )

    def test_scan_failure_records_all_as_not_found(self):
        self.run_main({"aa:aa:aa:aa:aa:aa": READING}, now=1_800_000_000)
        code = self.run_main(RuntimeError("not found"), now=1_800_000_300)
        self.assertEqual(code, 1)
        self.assertEqual(
            self.rows(),
            [
                ["リビング", "1800000300", "1800000000", "not_found"],
                ["屋外", "1800000300", "0", "not_found"],
            ],
        )

    def test_connection_error_marks_unsent_readings_as_post_failed(self):
        def post(**_):
            raise requests.ConnectionError("down")

        code = self.run_main({"aa:aa:aa:aa:aa:aa": READING}, post=post)
        self.assertEqual(code, 1)
        self.assertEqual([row[3] for row in self.rows()], ["post_failed", "not_found"])

    def test_dry_run_does_not_record_success(self):
        self.run_main({"aa:aa:aa:aa:aa:aa": READING}, argv=["--dry-run"])
        self.assertFalse(self.status.exists())

    def test_unwritable_status_file_does_not_change_result(self):
        blocker = Path(self.dir.name) / "file"
        blocker.write_text("", encoding="utf-8")
        with mock.patch.dict(os.environ, {"SENSOR_STATUS_FILE": str(blocker / "sensor-status.tsv")}):
            code = self.run_main({"aa:aa:aa:aa:aa:aa": READING})
        self.assertEqual(code, 0)

    def test_names_with_tabs_do_not_shift_columns(self):
        sensor = collector.SensorTarget(mac="cc:cc:cc:cc:cc:cc", device_id=9, name="a\tb\nc")
        collector.write_sensor_status(self.status, [sensor], {"cc:cc:cc:cc:cc:cc": "success"}, 1)
        self.assertEqual(self.rows(), [["a b c", "1", "1", "success"]])


if __name__ == "__main__":
    unittest.main()

