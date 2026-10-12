from __future__ import annotations

from typing import Any, Dict, Tuple

import requests

from state import UptimeKumaSnapshot


class UptimeKumaError(Exception):
    pass


def _get_json(url: str, timeout: int) -> Dict[str, Any]:
    try:
        response = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        raise UptimeKumaError(f"request failed: {exc}") from exc
    if not response.ok:
        raise UptimeKumaError(f"HTTP {response.status_code}: {response.text[:200]}")
    try:
        return response.json()
    except ValueError as exc:
        raise UptimeKumaError(f"JSONデコード失敗: {exc}") from exc


def fetch_raw(base_url: str, slug: str, timeout: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """status-page と status-page/heartbeat の生JSONを両方返す（--dump-raw-uptime-kuma用）。"""
    status_page = _get_json(f"{base_url.rstrip('/')}/api/status-page/{slug}", timeout)
    heartbeat = _get_json(f"{base_url.rstrip('/')}/api/status-page/heartbeat/{slug}", timeout)
    return status_page, heartbeat


def fetch_status(base_url: str, slug: str, timeout: int) -> UptimeKumaSnapshot:
    """status-page(監視対象名) + heartbeat(直近状態) をマージしてUP/DOWN集計する。

    heartbeatList の各monitor末尾要素の status: 1=UP, 0=DOWN, 2=PENDING, 3=MAINTENANCE
    エンドポイントの正確な形状はuptime-kumaのバージョンに依存するため、
    実機確認は --dump-raw-uptime-kuma で行うこと。
    """
    status_page, heartbeat = fetch_raw(base_url, slug, timeout)

    monitor_names: Dict[str, str] = {}
    for group in status_page.get("publicGroupList", []):
        for monitor in group.get("monitorList", []):
            monitor_id = str(monitor.get("id"))
            monitor_names[monitor_id] = monitor.get("name", monitor_id)

    heartbeat_list = heartbeat.get("heartbeatList", {})

    up_count = 0
    down_count = 0
    pending_count = 0
    down_monitor_names = []

    for monitor_id, beats in heartbeat_list.items():
        if not beats:
            pending_count += 1
            continue
        last_status = beats[-1].get("status")
        name = monitor_names.get(str(monitor_id), str(monitor_id))
        if last_status == 1:
            up_count += 1
        elif last_status == 0:
            down_count += 1
            down_monitor_names.append(name)
        else:
            pending_count += 1

    return UptimeKumaSnapshot(
        up_count=up_count,
        down_count=down_count,
        pending_count=pending_count,
        down_monitor_names=down_monitor_names,
    )

