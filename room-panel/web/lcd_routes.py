from __future__ import annotations

from typing import Dict, List

from flask import Blueprint, redirect, url_for

import display_modes
from lcd import SCROLL_GAP, WIDTH as LCD_WIDTH
from state import AppStateSnapshot, StateStore

# (表示秒数, ラベル) : 実機LCD側もWeb側もこの一覧の値からのみ選べる(任意の値はURL経由でも受け付けない)。
SCROLL_INTERVAL_PRESETS = [(4.0, "遅い"), (2.0, "標準"), (1.0, "速い")]
PAGE_INTERVAL_PRESETS = [(4.0, "遅い"), (2.0, "標準"), (1.0, "速い")]


def render_mode_previews(snapshot: AppStateSnapshot) -> Dict[str, List]:
    return {
        mode_id: _render_mode_preview(mode, snapshot)
        for mode_id, mode in display_modes.MODES.items()
    }


def _render_mode_preview(mode: display_modes.LcdMode, snapshot: AppStateSnapshot) -> List:
    try:
        return mode.render(snapshot) or [("", "")]
    except Exception as exc:
        return [("(preview error)", str(exc)[:16])]


def build_blueprint(state: StateStore) -> Blueprint:
    bp = Blueprint("lcd", __name__)

    @bp.route("/mode/<mode_id>", methods=["POST"])
    def set_mode(mode_id: str):
        if mode_id in display_modes.MODES:
            state.set_mode(mode_id)
        return redirect(url_for("index"))

    @bp.route("/lcd_scroll_interval/<float:seconds>", methods=["POST"])
    def set_lcd_scroll_interval(seconds: float):
        allowed = {value for value, _ in SCROLL_INTERVAL_PRESETS}
        if seconds in allowed:
            state.set_lcd_scroll_interval_sec(seconds)
        return redirect(url_for("index"))

    @bp.route("/lcd_page_interval/<float:seconds>", methods=["POST"])
    def set_lcd_page_interval(seconds: float):
        allowed = {value for value, _ in PAGE_INTERVAL_PRESETS}
        if seconds in allowed:
            state.set_lcd_page_interval_sec(seconds)
        return redirect(url_for("index"))

    return bp

