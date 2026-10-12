from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict

from led import LedStatus
from state import AppStateSnapshot


@dataclass(frozen=True)
class LedSource:
    id: str
    label: str  # Web UI表示名
    description: str  # Web UI詳細説明
    compute: Callable[[AppStateSnapshot], LedStatus]


def _myroom_freshness(threshold_sec: int) -> Callable[[AppStateSnapshot], LedStatus]:
    def compute(snapshot: AppStateSnapshot) -> LedStatus:
        if snapshot.myroom_last_success_at is None:
            return LedStatus.BLINK
        age = time.time() - snapshot.myroom_last_success_at
        return LedStatus.ON if age <= threshold_sec else LedStatus.OFF

    return compute


def _uptime_kuma_overall(snapshot: AppStateSnapshot) -> LedStatus:
    uptime = snapshot.uptime_snapshot
    if uptime is None:
        return LedStatus.BLINK
    if uptime.down_count > 0:
        return LedStatus.OFF
    if uptime.up_count == 0:
        return LedStatus.BLINK
    return LedStatus.ON


def _co2_alert(snapshot: AppStateSnapshot) -> LedStatus:
    reading = snapshot.myroom_reading
    if reading is None or reading.co2 is None:
        return LedStatus.BLINK
    return LedStatus.ON if reading.co2 >= snapshot.co2_alert_threshold else LedStatus.OFF


def _cpu_high_load(threshold_percent: int) -> Callable[[AppStateSnapshot], LedStatus]:
    def compute(snapshot: AppStateSnapshot) -> LedStatus:
        stats = snapshot.system_stats
        if stats is None or stats.cpu_percent is None:
            return LedStatus.BLINK
        return LedStatus.ON if stats.cpu_percent >= threshold_percent else LedStatus.OFF

    return compute


def _always_on(_: AppStateSnapshot) -> LedStatus:
    return LedStatus.ON


def _always_off(_: AppStateSnapshot) -> LedStatus:
    return LedStatus.OFF


def _heartbeat_placeholder(_: AppStateSnapshot) -> LedStatus:
    # heartbeatはworker.heartbeat_loopが物理LEDを直接トグルするため、
    # poll_loopはこのソースが割り当てられたLEDを更新しない(worker.py参照)。
    # レジストリ上の一覧・ラベル表示のためだけに存在する。
    return LedStatus.BLINK


HEARTBEAT_SOURCE_ID = "heartbeat"


def build_led_sources(
    myroom_stale_threshold_sec: int,
    cpu_alert_threshold_percent: int,
) -> Dict[str, LedSource]:
    return {
        "myroom_freshness": LedSource(
            id="myroom_freshness",
            label="MyRoomデータ取得正常性",
            description=(
                f"MyRoom API（温度・湿度・CO2・気圧などのセンサー値）から直近{myroom_stale_threshold_sec}秒以内に"
                "取得成功していればON、それより古ければOFF、一度も取得できていなければ点滅します。"
            ),
            compute=_myroom_freshness(myroom_stale_threshold_sec),
        ),
        "uptime_kuma_overall": LedSource(
            id="uptime_kuma_overall",
            label="uptime-kuma 全体UP/DOWN",
            description=(
                "uptime-kumaのステータスページ監視対象が全てUPならON、"
                "1つでもDOWNならOFF、まだ取得できていなければ点滅します。"
            ),
            compute=_uptime_kuma_overall,
        ),
        HEARTBEAT_SOURCE_ID: LedSource(
            id=HEARTBEAT_SOURCE_ID,
            label="ハートビート(生存確認)",
            description=(
                "外部データではなく、room-panel自体の生存確認用です。"
                "一定間隔で点滅し続け、アプリのポーリング処理がハングすると消灯したままになります。"
            ),
            compute=_heartbeat_placeholder,
        ),
        "co2_alert": LedSource(
            id="co2_alert",
            label="CO2警報",
            description=(
                "MyRoomのCO2濃度が設定した閾値以上ならON、未満ならOFF、"
                "データが取得できていなければ点滅します。換気のサインに使えます。"
                "閾値は下の一覧からWeb UIで変更できます。"
            ),
            compute=_co2_alert,
        ),
        "cpu_high_load": LedSource(
            id="cpu_high_load",
            label="CPU高負荷(ラズパイ)",
            description=(
                f"ラズパイ本体のCPU使用率が{cpu_alert_threshold_percent}%以上ならON、それ未満ならOFF、"
                "データが取得できていなければ点滅します。"
                "（閾値はCPU_ALERT_THRESHOLD_PERCENT環境変数で変更可能）"
            ),
            compute=_cpu_high_load(cpu_alert_threshold_percent),
        ),
        "always_on": LedSource(
            id="always_on",
            label="常時点灯",
            description="データ取得は行わず、常にONで固定します（配線・動作確認用）。",
            compute=_always_on,
        ),
        "always_off": LedSource(
            id="always_off",
            label="常時消灯",
            description="データ取得は行わず、常にOFFで固定します（未使用LEDの予備枠など）。",
            compute=_always_off,
        ),
    }

