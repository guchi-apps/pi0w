from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Optional, Tuple

# CPU使用率は前回サンプルとの差分から算出するため、直近の/proc/stat値をモジュール内に保持する。
# poll_loopの単一スレッドからのみ呼ばれる想定(state.pyの他ポーラーと同様)で、排他制御は行わない。
_prev_total_jiffies: Optional[int] = None
_prev_idle_jiffies: Optional[int] = None


@dataclass(frozen=True)
class SystemStats:
    cpu_percent: Optional[float] = None
    cpu_temp_c: Optional[float] = None
    mem_percent: Optional[float] = None
    mem_used_mb: Optional[float] = None
    mem_total_mb: Optional[float] = None
    disk_percent: Optional[float] = None
    disk_used_gb: Optional[float] = None
    disk_total_gb: Optional[float] = None


def _read_cpu_percent() -> Optional[float]:
    global _prev_total_jiffies, _prev_idle_jiffies
    with open("/proc/stat") as f:
        line = f.readline()
    fields = [int(x) for x in line.split()[1:]]  # "cpu  user nice system idle iowait ..."
    idle = fields[3] + fields[4]
    total = sum(fields)

    percent = None
    if _prev_total_jiffies is not None:
        total_delta = total - _prev_total_jiffies
        idle_delta = idle - _prev_idle_jiffies
        if total_delta > 0:
            percent = max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100))
    _prev_total_jiffies, _prev_idle_jiffies = total, idle
    return percent


def _read_cpu_temp() -> Optional[float]:
    # Raspberry Pi OSでは/sys/class/thermal/thermal_zone0/tempにミリ度単位のCPU温度が入る。
    # このファイルが無い環境(WSL開発機など)ではNoneを返す。
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            millidegrees = int(f.read().strip())
        return millidegrees / 1000
    except (OSError, ValueError):
        return None


def _read_mem() -> Tuple[Optional[float], Optional[float], Optional[float]]:
    meminfo = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, _, rest = line.partition(":")
            meminfo[key] = int(rest.strip().split()[0])  # kB単位

    total_kb = meminfo.get("MemTotal")
    available_kb = meminfo.get("MemAvailable")
    if not total_kb or available_kb is None:
        return None, None, None
    used_kb = total_kb - available_kb
    return used_kb / total_kb * 100, used_kb / 1024, total_kb / 1024


def _read_disk(path: str = "/") -> Tuple[Optional[float], Optional[float], Optional[float]]:
    usage = shutil.disk_usage(path)
    if not usage.total:
        return None, None, None
    return usage.used / usage.total * 100, usage.used / (1024 ** 3), usage.total / (1024 ** 3)


def read_system_stats(disk_path: str = "/") -> SystemStats:
    cpu_percent = _read_cpu_percent()
    cpu_temp_c = _read_cpu_temp()
    mem_percent, mem_used_mb, mem_total_mb = _read_mem()
    disk_percent, disk_used_gb, disk_total_gb = _read_disk(disk_path)
    return SystemStats(
        cpu_percent=cpu_percent,
        cpu_temp_c=cpu_temp_c,
        mem_percent=mem_percent,
        mem_used_mb=mem_used_mb,
        mem_total_mb=mem_total_mb,
        disk_percent=disk_percent,
        disk_used_gb=disk_used_gb,
        disk_total_gb=disk_total_gb,
    )

