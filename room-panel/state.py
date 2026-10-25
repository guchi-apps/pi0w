from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from system_stats import SystemStats


@dataclass(frozen=True)
class MyRoomReading:
    device_id: int
    datetime_str: Optional[str] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    co2: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UptimeKumaSnapshot:
    up_count: int
    down_count: int
    pending_count: int
    down_monitor_names: list = field(default_factory=list)


@dataclass(frozen=True)
class VpsStats:
    cpu_percent: Optional[float] = None
    mem_percent: Optional[float] = None
    mem_used_mb: Optional[float] = None
    mem_total_mb: Optional[float] = None
    disk_percent: Optional[float] = None
    disk_used_gb: Optional[float] = None
    disk_total_gb: Optional[float] = None


@dataclass(frozen=True)
class AiQuota:
    # 残り割合(0-100の整数)。取得できなかった枠はNone(0%とは区別する)。
    claude_5h_remaining: Optional[int] = None
    claude_week_remaining: Optional[int] = None
    codex_week_remaining: Optional[int] = None
    # リセット時刻(epoch秒)。不明ならNone。
    claude_5h_resets_at: Optional[float] = None
    claude_week_resets_at: Optional[float] = None
    codex_week_resets_at: Optional[float] = None


@dataclass(frozen=True)
class AppStateSnapshot:
    current_mode: str
    led_assignment: Dict[str, str]
    led_invert: Dict[str, bool]
    lcd_page_interval_sec: float
    lcd_scroll_interval_sec: float
    co2_alert_threshold: int
    all_off: bool

    myroom_reading: Optional[MyRoomReading]
    myroom_last_success_at: Optional[float]
    myroom_last_error: Optional[str]

    uptime_snapshot: Optional[UptimeKumaSnapshot]
    uptime_last_success_at: Optional[float]
    uptime_last_error: Optional[str]

    system_stats: Optional[SystemStats]
    system_stats_last_success_at: Optional[float]
    system_stats_last_error: Optional[str]

    vps_stats: Optional[VpsStats]
    vps_stats_last_success_at: Optional[float]
    vps_stats_last_error: Optional[str]

    ai_quota: Optional[AiQuota]
    ai_quota_last_success_at: Optional[float]
    ai_quota_last_error: Optional[str]

    last_tick_at: Optional[float]


class StateStore:
    """AppStateへのスレッドセーフなアクセスを提供する。

    Flaskルートはsnapshot()経由の読み取りのみ行い、外部I/Oはpoll_loop/heartbeat_loopに一任する。
    """

    def __init__(
        self,
        default_mode: str,
        default_led_assignment: Dict[str, str],
        default_lcd_page_interval_sec: float,
        default_lcd_scroll_interval_sec: float,
        default_co2_alert_threshold: int,
    ) -> None:
        self._lock = threading.Lock()
        self._current_mode = default_mode
        self._led_assignment = dict(default_led_assignment)
        self._led_invert: Dict[str, bool] = {}
        self._lcd_page_interval_sec = default_lcd_page_interval_sec
        self._lcd_scroll_interval_sec = default_lcd_scroll_interval_sec
        self._co2_alert_threshold = default_co2_alert_threshold
        self._all_off = False
        self._myroom_reading: Optional[MyRoomReading] = None
        self._myroom_last_success_at: Optional[float] = None
        self._myroom_last_error: Optional[str] = None
        self._uptime_snapshot: Optional[UptimeKumaSnapshot] = None
        self._uptime_last_success_at: Optional[float] = None
        self._uptime_last_error: Optional[str] = None
        self._system_stats: Optional[SystemStats] = None
        self._system_stats_last_success_at: Optional[float] = None
        self._system_stats_last_error: Optional[str] = None
        self._vps_stats: Optional[VpsStats] = None
        self._vps_stats_last_success_at: Optional[float] = None
        self._vps_stats_last_error: Optional[str] = None
        self._ai_quota: Optional[AiQuota] = None
        self._ai_quota_last_success_at: Optional[float] = None
        self._ai_quota_last_error: Optional[str] = None
        self._last_tick_at: Optional[float] = None

    def snapshot(self) -> AppStateSnapshot:
        with self._lock:
            return AppStateSnapshot(
                current_mode=self._current_mode,
                led_assignment=dict(self._led_assignment),
                led_invert=dict(self._led_invert),
                lcd_page_interval_sec=self._lcd_page_interval_sec,
                lcd_scroll_interval_sec=self._lcd_scroll_interval_sec,
                co2_alert_threshold=self._co2_alert_threshold,
                all_off=self._all_off,
                myroom_reading=self._myroom_reading,
                myroom_last_success_at=self._myroom_last_success_at,
                myroom_last_error=self._myroom_last_error,
                uptime_snapshot=self._uptime_snapshot,
                uptime_last_success_at=self._uptime_last_success_at,
                uptime_last_error=self._uptime_last_error,
                system_stats=self._system_stats,
                system_stats_last_success_at=self._system_stats_last_success_at,
                system_stats_last_error=self._system_stats_last_error,
                vps_stats=self._vps_stats,
                vps_stats_last_success_at=self._vps_stats_last_success_at,
                vps_stats_last_error=self._vps_stats_last_error,
                ai_quota=self._ai_quota,
                ai_quota_last_success_at=self._ai_quota_last_success_at,
                ai_quota_last_error=self._ai_quota_last_error,
                last_tick_at=self._last_tick_at,
            )

    def set_mode(self, mode_id: str) -> None:
        with self._lock:
            self._current_mode = mode_id

    def set_lcd_page_interval_sec(self, seconds: float) -> None:
        with self._lock:
            self._lcd_page_interval_sec = seconds

    def set_lcd_scroll_interval_sec(self, seconds: float) -> None:
        with self._lock:
            self._lcd_scroll_interval_sec = seconds

    def set_co2_alert_threshold(self, ppm: int) -> None:
        with self._lock:
            self._co2_alert_threshold = ppm

    def set_led_source(self, led_key: str, source_id: str) -> None:
        with self._lock:
            self._led_assignment[led_key] = source_id

    def set_led_invert(self, source_id: str, invert: bool) -> None:
        with self._lock:
            self._led_invert[source_id] = invert

    def set_all_off(self, value: bool) -> None:
        with self._lock:
            self._all_off = value

    def update_myroom_success(self, reading: MyRoomReading) -> None:
        with self._lock:
            self._myroom_reading = reading
            self._myroom_last_success_at = time.time()
            self._myroom_last_error = None

    def update_myroom_error(self, error: str) -> None:
        with self._lock:
            self._myroom_last_error = error

    def update_uptime_success(self, snapshot: UptimeKumaSnapshot) -> None:
        with self._lock:
            self._uptime_snapshot = snapshot
            self._uptime_last_success_at = time.time()
            self._uptime_last_error = None

    def update_uptime_error(self, error: str) -> None:
        with self._lock:
            self._uptime_last_error = error

    def update_system_stats_success(self, stats: SystemStats) -> None:
        with self._lock:
            self._system_stats = stats
            self._system_stats_last_success_at = time.time()
            self._system_stats_last_error = None

    def update_system_stats_error(self, error: str) -> None:
        with self._lock:
            self._system_stats_last_error = error

    def update_vps_stats_success(self, stats: VpsStats) -> None:
        with self._lock:
            self._vps_stats = stats
            self._vps_stats_last_success_at = time.time()
            self._vps_stats_last_error = None

    def update_vps_stats_error(self, error: str) -> None:
        with self._lock:
            self._vps_stats_last_error = error

    def update_ai_quota_success(self, quota: AiQuota) -> None:
        with self._lock:
            self._ai_quota = quota
            self._ai_quota_last_success_at = time.time()
            self._ai_quota_last_error = None

    def update_ai_quota_error(self, error: str) -> None:
        with self._lock:
            self._ai_quota_last_error = error

    def mark_tick(self) -> None:
        with self._lock:
            self._last_tick_at = time.monotonic()

