from __future__ import annotations

from typing import Any, Dict

import requests

from state import VpsStats


class VpsStatusError(Exception):
    pass


def fetch_status(url: str, token: str, timeout: int) -> VpsStats:
    try:
        response = requests.get(
            url, headers={"Authorization": f"Bearer {token}"}, timeout=timeout
        )
    except requests.RequestException as exc:
        raise VpsStatusError(f"request failed: {exc}") from exc
    if not response.ok:
        raise VpsStatusError(f"HTTP {response.status_code}: {response.text[:200]}")
    try:
        data: Dict[str, Any] = response.json()
    except ValueError as exc:
        raise VpsStatusError(f"JSONデコード失敗: {exc}") from exc

    return VpsStats(
        cpu_percent=data.get("cpu_percent"),
        mem_percent=data.get("mem_percent"),
        mem_used_mb=data.get("mem_used_mb"),
        mem_total_mb=data.get("mem_total_mb"),
        disk_percent=data.get("disk_percent"),
        disk_used_gb=data.get("disk_used_gb"),
        disk_total_gb=data.get("disk_total_gb"),
    )

