from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

from state import AppStateSnapshot

# HD44780系I2C LCDはUTF-8の日本語を表示できない(ASCII+一部カタカナROMのみ)ため、
# LCDへ渡す文字列は必ずASCII/半角英数のみで組み立てる。度記号(°)もROM依存のため "C" 表記に倒す。

LcdPage = Tuple[str, str]


@dataclass(frozen=True)
class LcdMode:
    id: str
    label: str  # Web UI表示名(日本語可、LCDには出さない)
    render: Callable[[AppStateSnapshot], List[LcdPage]]


def _render_myroom(snapshot: AppStateSnapshot) -> List[LcdPage]:
    reading = snapshot.myroom_reading
    if reading is None:
        return [("MyRoom", "NO DATA YET")]

    parts = []
    if reading.temperature is not None:
        parts.append(f"T:{reading.temperature}C")
    if reading.humidity is not None:
        parts.append(f"H:{reading.humidity}%")
    line1 = " ".join(parts) if parts else "NO DATA"

    parts2 = []
    if reading.co2 is not None:
        parts2.append(f"CO2:{reading.co2}")
    if reading.pressure is not None:
        parts2.append(f"{int(reading.pressure)}hPa")
    line2 = " ".join(parts2) if parts2 else (snapshot.myroom_last_error or "")

    return [(line1, line2)]


def _render_uptime_kuma(snapshot: AppStateSnapshot) -> List[LcdPage]:
    uptime = snapshot.uptime_snapshot
    if uptime is None:
        return [("Uptime-Kuma", snapshot.uptime_last_error or "NO DATA YET")]

    line1 = f"UP:{uptime.up_count} DOWN:{uptime.down_count}"
    if uptime.down_monitor_names:
        line2 = uptime.down_monitor_names[0]
    elif uptime.pending_count:
        line2 = f"PENDING:{uptime.pending_count}"
    else:
        line2 = "ALL OK"
    return [(line1, line2)]


def _render_system(snapshot: AppStateSnapshot) -> List[LcdPage]:
    stats = snapshot.system_stats
    if stats is None:
        return [("System", snapshot.system_stats_last_error or "NO DATA YET")]

    cpu_str = f"{stats.cpu_percent:.0f}%" if stats.cpu_percent is not None else "--"
    mem_str = f"{stats.mem_percent:.0f}%" if stats.mem_percent is not None else "--"
    line1 = f"CPU:{cpu_str} MEM:{mem_str}"

    if stats.disk_total_gb is not None:
        disk_line = f"DISK:{stats.disk_percent:.0f}% {stats.disk_used_gb:.1f}/{stats.disk_total_gb:.0f}G"
    else:
        disk_line = snapshot.system_stats_last_error or ""

    temp_str = f"{stats.cpu_temp_c:.1f}C" if stats.cpu_temp_c is not None else "N/A"
    temp_line = f"TEMP:{temp_str}"

    # DISK情報とCPU温度は1画面(2行)に収まらないため、ページを分けて自動で交互表示する。
    return [(line1, disk_line), (line1, temp_line)]


def _render_vps(snapshot: AppStateSnapshot) -> List[LcdPage]:
    stats = snapshot.vps_stats
    if stats is None:
        return [("VPS", snapshot.vps_stats_last_error or "NO DATA YET")]

    cpu_str = f"{stats.cpu_percent:.0f}%" if stats.cpu_percent is not None else "--"
    mem_str = f"{stats.mem_percent:.0f}%" if stats.mem_percent is not None else "--"
    line1 = f"CPU:{cpu_str} MEM:{mem_str}"

    if stats.disk_total_gb is not None:
        line2 = f"DISK:{stats.disk_percent:.0f}% {stats.disk_used_gb:.1f}/{stats.disk_total_gb:.0f}G"
    else:
        line2 = snapshot.vps_stats_last_error or ""

    return [(line1, line2)]


_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _render_clock(snapshot: AppStateSnapshot) -> List[LcdPage]:
    now = time.localtime()
    # %aはロケール依存で日本語("月"等)を返す環境があり非ASCIIになるため、固定の英語表記を使う。
    weekday = _WEEKDAYS[now.tm_wday]
    line1 = time.strftime("%Y-%m-%d", now) + f"({weekday})"
    line2 = time.strftime("%H:%M:%S", now)
    return [(line1, line2)]


MODES: Dict[str, LcdMode] = {
    "myroom": LcdMode(id="myroom", label="MyRoom 温度・湿度など", render=_render_myroom),
    "uptime_kuma": LcdMode(
        id="uptime_kuma", label="uptime-kuma 監視状況", render=_render_uptime_kuma
    ),
    "system": LcdMode(
        id="system", label="システム状態(CPU/メモリ/ディスク)", render=_render_system
    ),
    "vps": LcdMode(id="vps", label="VPSの状態(CPU/メモリ/ディスク)", render=_render_vps),
    "clock": LcdMode(id="clock", label="時計", render=_render_clock),
}

DEFAULT_MODE_ID = "myroom"

