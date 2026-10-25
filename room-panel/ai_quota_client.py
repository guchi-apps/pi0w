from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import requests

from state import AiQuota

# ops-dashboardの GET /api/ai-usage (Bearer OPS_API_TOKEN) が返す
# {"providers": [{"id": "claude"|"chatgpt", "status": "ok"|..., "windows": [...]}]} を読む。
# 枠の長さ(windowSeconds)で5時間枠・週間枠を判別し、取れない場合は表示名で判別する。

_FIVE_HOURS_SEC = 5 * 3600
_WEEK_SEC = 7 * 24 * 3600


class AiQuotaError(Exception):
    pass


def _parse_iso(value: Any) -> Optional[float]:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Python 3.7のfromisoformatは小数部が3桁か6桁でないと失敗するため6桁へ揃える
    text = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], text, count=1)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _find_window(provider: Dict[str, Any], seconds: int, label_hint: str) -> Optional[Dict[str, Any]]:
    windows = [w for w in provider.get("windows") or [] if isinstance(w, dict)]
    # Opus別枠などの補足つき(note)の枠は本体の枠と取り違えないよう後回しにする
    windows.sort(key=lambda w: 1 if w.get("note") else 0)
    for window in windows:
        if window.get("windowSeconds") == seconds:
            return window
    for window in windows:
        if window.get("windowSeconds") is None and label_hint in str(window.get("label", "")):
            return window
    return None


def _remaining(window: Optional[Dict[str, Any]]) -> Tuple[Optional[int], Optional[float]]:
    if window is None:
        return None, None
    used = window.get("usedPercent")
    if isinstance(used, bool) or not isinstance(used, (int, float)):
        return None, None
    remaining = int(round(100 - max(0.0, min(100.0, float(used)))))
    return remaining, _parse_iso(window.get("resetsAt"))


def _provider(data: Dict[str, Any], provider_id: str) -> Optional[Dict[str, Any]]:
    for provider in data.get("providers") or []:
        if isinstance(provider, dict) and provider.get("id") == provider_id:
            # 取得失敗・未設定の提供元は値を読まない(古い/空の値を残りと誤読させない)
            return provider if provider.get("status") == "ok" else None
    return None


def parse_usage(data: Any) -> AiQuota:
    if not isinstance(data, dict) or not isinstance(data.get("providers"), list):
        raise AiQuotaError("想定外のレスポンス形式")

    claude = _provider(data, "claude")
    chatgpt = _provider(data, "chatgpt")
    c5, c5_reset = _remaining(_find_window(claude, _FIVE_HOURS_SEC, "5時間") if claude else None)
    cw, cw_reset = _remaining(_find_window(claude, _WEEK_SEC, "週間") if claude else None)
    xw, xw_reset = _remaining(_find_window(chatgpt, _WEEK_SEC, "週間") if chatgpt else None)
    return AiQuota(
        claude_5h_remaining=c5,
        claude_week_remaining=cw,
        codex_week_remaining=xw,
        claude_5h_resets_at=c5_reset,
        claude_week_resets_at=cw_reset,
        codex_week_resets_at=xw_reset,
    )


def fetch_quota(url: str, token: str, timeout: int) -> AiQuota:
    try:
        response = requests.get(
            url, headers={"Authorization": f"Bearer {token}"}, timeout=timeout
        )
    except requests.RequestException as exc:
        raise AiQuotaError(f"request failed: {exc}") from exc
    if not response.ok:
        raise AiQuotaError(f"HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        raise AiQuotaError(f"JSONデコード失敗: {exc}") from exc
    return parse_usage(data)
