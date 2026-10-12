from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Dict, List, Optional

from flask import Flask, jsonify, render_template, send_from_directory

import display_modes
from config import AppConfig
from led_sources import LedSource
from state import StateStore
from web import lcd_routes, led_routes, power_routes


def _fmt_ts(ts: Optional[float]) -> str:
    if ts is None:
        return "未取得"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def create_app(
    config: AppConfig,
    state: StateStore,
    led_sources: Dict[str, LedSource],
    led_keys: List[str],
) -> Flask:
    app = Flask(__name__)
    # テンプレート編集を再起動なしで反映する(GPIO/I2Cを再初期化するuse_reloaderとは無関係で常時有効化して問題ない)。
    # jinja_envはcached_propertyのため、初回アクセスより前に設定する必要がある。
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.filters["fmt_ts"] = _fmt_ts

    app.register_blueprint(lcd_routes.build_blueprint(state))
    app.register_blueprint(led_routes.build_blueprint(state, led_sources, led_keys))
    app.register_blueprint(power_routes.build_blueprint(state))

    @app.route("/")
    def index():
        snapshot = state.snapshot()
        return render_template(
            "index.html",
            snapshot=snapshot,
            modes=display_modes.MODES,
            mode_previews=lcd_routes.render_mode_previews(snapshot),
            led_sources=led_sources,
            led_keys=led_keys,
            lcd_width=lcd_routes.LCD_WIDTH,
            lcd_scroll_gap=lcd_routes.SCROLL_GAP,
            scroll_presets=lcd_routes.SCROLL_INTERVAL_PRESETS,
            page_presets=lcd_routes.PAGE_INTERVAL_PRESETS,
            co2_threshold_min=led_routes.CO2_ALERT_THRESHOLD_MIN,
            co2_threshold_max=led_routes.CO2_ALERT_THRESHOLD_MAX,
        )

    @app.route("/api/status")
    def api_status():
        snapshot = state.snapshot()
        return jsonify(dataclasses.asdict(snapshot))

    @app.route("/healthz")
    def healthz():
        return "ok", 200

    @app.route("/sw.js")
    def service_worker():
        # /static/配下だとスコープがstatic以下に限定されるため、ルート直下で配信してPWA全体を制御対象にする。
        response = send_from_directory(app.static_folder, "sw.js")
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Service-Worker-Allowed"] = "/"
        return response

    return app

