from __future__ import annotations

import requests

from state import MyRoomReading


class MyRoomError(Exception):
    pass


def fetch_latest(base_url: str, token: str, device_id: int, timeout: int) -> MyRoomReading:
    """MyRoom /api/latest から最新センサー値を取得する。

    レスポンスのフィールド名はPOST側(switchbot_to_myroom.py)に合わせて
    datetime/temperature/humidity/pressure/co2 を想定するが、未確認のため
    .get() ベースで欠損に強く実装する。実機確認は --check-myroom で行う。
    """
    if not base_url:
        raise MyRoomError("MYROOM_API_URLを設定してください")
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(
            base_url,
            params={"device": device_id},
            headers=headers,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise MyRoomError(f"request failed: {exc}") from exc

    if response.status_code == 401:
        raise MyRoomError("認証エラー(401)。MYROOM_API_TOKENを確認してください")
    if not response.ok:
        raise MyRoomError(f"HTTP {response.status_code}: {response.text[:200]}")

    try:
        data = response.json()
    except ValueError as exc:
        raise MyRoomError(f"JSONデコード失敗: {exc}") from exc

    return MyRoomReading(
        device_id=device_id,
        datetime_str=data.get("datetime"),
        temperature=data.get("temperature"),
        humidity=data.get("humidity"),
        pressure=data.get("pressure"),
        co2=data.get("co2"),
        raw=data,
    )


