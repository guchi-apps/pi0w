from __future__ import annotations

from typing import Dict, List

from flask import Blueprint, redirect, request, url_for

from led_sources import HEARTBEAT_SOURCE_ID, LedSource
from state import StateStore

# co2_alertソースの閾値としてWeb UIから受け付ける範囲(ppm)。この範囲外の入力は無視する。
CO2_ALERT_THRESHOLD_MIN = 300
CO2_ALERT_THRESHOLD_MAX = 10000


def build_blueprint(
    state: StateStore, led_sources: Dict[str, LedSource], led_keys: List[str]
) -> Blueprint:
    bp = Blueprint("led", __name__)

    @bp.route("/led/<led_key>/<source_id>", methods=["POST"])
    def set_led(led_key: str, source_id: str):
        if led_key in led_keys and source_id in led_sources:
            state.set_led_source(led_key, source_id)
        return redirect(url_for("index"))

    @bp.route("/led_invert/<source_id>", methods=["POST"])
    def set_led_invert(source_id: str):
        # heartbeatは物理LEDを直接トグルする特殊経路のため、反転設定の対象外とする(worker.py参照)。
        if source_id in led_sources and source_id != HEARTBEAT_SOURCE_ID:
            current = state.snapshot().led_invert.get(source_id, False)
            state.set_led_invert(source_id, not current)
        return redirect(url_for("index"))

    @bp.route("/co2_alert_threshold", methods=["POST"])
    def set_co2_alert_threshold():
        ppm = request.form.get("ppm", type=int)
        if ppm is not None and CO2_ALERT_THRESHOLD_MIN <= ppm <= CO2_ALERT_THRESHOLD_MAX:
            state.set_co2_alert_threshold(ppm)
        return redirect(url_for("index"))

    return bp

