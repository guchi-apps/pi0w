from __future__ import annotations

import itertools
import time

from state import AiQuota, MyRoomReading, UptimeKumaSnapshot, VpsStats

# FAKE_SOURCES=1 のとき、myroom/uptime-kuma/VPS状態APIへの実通信を行わず、
# OK/NG/UNKNOWNの全パターンを一定周期で巡回するダミーデータを返す。
# 非Pi環境でのオフライン開発・Web UI確認用。

_myroom_cycle = itertools.cycle(["fresh", "stale", "error"])
_uptime_cycle = itertools.cycle(["all_up", "one_down", "error"])
_vps_cycle = itertools.cycle(["normal", "high_load", "error"])
_ai_quota_cycle = itertools.cycle(["normal", "low", "partial", "error"])


def fake_ai_quota() -> AiQuota:
    state = next(_ai_quota_cycle)
    if state == "error":
        raise RuntimeError("[fake] simulated ai quota fetch error")
    now = time.time()
    if state == "normal":
        return AiQuota(75, 57, 97, now + 2 * 3600 + 43 * 60, now + 14 * 3600, now + 5 * 86400)
    if state == "low":
        return AiQuota(12, 8, 30, now + 40 * 60, now + 20 * 3600, now + 2 * 86400)
    # 一部の提供元だけ取得できなかったケース(Codex側が取得不可)
    return AiQuota(75, 57, None, now + 2 * 3600, now + 14 * 3600, None)


def fake_myroom_reading(device_id: int) -> MyRoomReading:
    state = next(_myroom_cycle)
    if state == "error":
        raise RuntimeError("[fake] simulated myroom fetch error")
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    if state == "fresh":
        return MyRoomReading(
            device_id=device_id,
            datetime_str=now,
            temperature=24.5,
            humidity=55,
            pressure=1013,
            co2=650,
            raw={"fake": "fresh"},
        )
    # "stale" も正常応答として返す(freshness判定はstate.py側のタイムスタンプで行うため、
    # ここでは単に別の値を返すだけで十分)
    return MyRoomReading(
        device_id=device_id,
        datetime_str=now,
        temperature=19.0,
        humidity=40,
        pressure=1005,
        co2=900,
        raw={"fake": "stale"},
    )


def fake_uptime_snapshot() -> UptimeKumaSnapshot:
    state = next(_uptime_cycle)
    if state == "error":
        raise RuntimeError("[fake] simulated uptime-kuma fetch error")
    if state == "all_up":
        return UptimeKumaSnapshot(up_count=3, down_count=0, pending_count=0, down_monitor_names=[])
    return UptimeKumaSnapshot(
        up_count=2, down_count=1, pending_count=0, down_monitor_names=["myroom-backend"]
    )


def fake_vps_stats() -> VpsStats:
    state = next(_vps_cycle)
    if state == "error":
        raise RuntimeError("[fake] simulated vps status fetch error")
    if state == "normal":
        return VpsStats(
            cpu_percent=15.0,
            mem_percent=45.0,
            mem_used_mb=900.0,
            mem_total_mb=2000.0,
            disk_percent=30.0,
            disk_used_gb=12.0,
            disk_total_gb=40.0,
        )
    return VpsStats(
        cpu_percent=92.0,
        mem_percent=88.0,
        mem_used_mb=1760.0,
        mem_total_mb=2000.0,
        disk_percent=30.0,
        disk_used_gb=12.0,
        disk_total_gb=40.0,
    )

