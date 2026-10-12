from __future__ import annotations

from flask import Blueprint, redirect, url_for

from state import StateStore


def build_blueprint(state: StateStore) -> Blueprint:
    bp = Blueprint("power", __name__)

    @bp.route("/all_off/<value>", methods=["POST"])
    def set_all_off(value: str):
        if value in ("on", "off"):
            state.set_all_off(value == "off")
        return redirect(url_for("index"))

    return bp


