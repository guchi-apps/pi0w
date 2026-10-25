from __future__ import annotations

import json
import sys

import ai_quota_client
import config as config_module
import fake_sources
import myroom_client
import uptime_kuma_client
import vps_client
import worker
from lcd import create_lcd
from led import create_led_controllers
from led_sources import build_led_sources
from state import StateStore
from web import create_app


def _run_check_myroom(config: config_module.AppConfig) -> int:
    try:
        if config.fake_sources:
            reading = fake_sources.fake_myroom_reading(config.myroom_device_id)
        else:
            reading = myroom_client.fetch_latest(
                config.myroom_api_url,
                config.myroom_api_token,
                config.myroom_device_id,
                config.http_timeout,
            )
    except Exception as exc:
        print(f"MyRoom取得エラー: {exc}", file=sys.stderr)
        return 1
    print(f"temperature={reading.temperature} humidity={reading.humidity} "
          f"co2={reading.co2} pressure={reading.pressure} datetime={reading.datetime_str}")
    print(f"raw={reading.raw}")
    return 0


def _run_check_uptime_kuma(config: config_module.AppConfig) -> int:
    try:
        if config.fake_sources:
            snapshot = fake_sources.fake_uptime_snapshot()
        else:
            snapshot = uptime_kuma_client.fetch_status(
                config.uptime_kuma_base_url, config.uptime_kuma_slug, config.http_timeout
            )
    except Exception as exc:
        print(f"uptime-kuma取得エラー: {exc}", file=sys.stderr)
        return 1
    print(f"up={snapshot.up_count} down={snapshot.down_count} pending={snapshot.pending_count} "
          f"down_monitors={snapshot.down_monitor_names}")
    return 0


def _run_dump_raw_uptime_kuma(config: config_module.AppConfig) -> int:
    try:
        status_page, heartbeat = uptime_kuma_client.fetch_raw(
            config.uptime_kuma_base_url, config.uptime_kuma_slug, config.http_timeout
        )
    except Exception as exc:
        print(f"uptime-kuma取得エラー: {exc}", file=sys.stderr)
        return 1
    print("=== status-page ===")
    print(json.dumps(status_page, ensure_ascii=False, indent=2))
    print("=== status-page/heartbeat ===")
    print(json.dumps(heartbeat, ensure_ascii=False, indent=2))
    return 0


def _run_check_vps_status(config: config_module.AppConfig) -> int:
    try:
        if config.fake_sources:
            stats = fake_sources.fake_vps_stats()
        else:
            stats = vps_client.fetch_status(
                config.vps_status_url, config.vps_status_token, config.http_timeout
            )
    except Exception as exc:
        print(f"VPS状態取得エラー: {exc}", file=sys.stderr)
        return 1
    print(f"cpu={stats.cpu_percent} mem={stats.mem_percent} "
          f"mem_used_mb={stats.mem_used_mb} mem_total_mb={stats.mem_total_mb} "
          f"disk={stats.disk_percent} disk_used_gb={stats.disk_used_gb} disk_total_gb={stats.disk_total_gb}")
    return 0


def _run_check_ai_quota(config: config_module.AppConfig) -> int:
    try:
        if config.fake_sources:
            quota = fake_sources.fake_ai_quota()
        else:
            quota = ai_quota_client.fetch_quota(
                config.ai_quota_url, config.ai_quota_token, config.http_timeout
            )
    except Exception as exc:
        print(f"AI利用枠取得エラー: {exc}", file=sys.stderr)
        return 1
    print(f"claude_5h={quota.claude_5h_remaining} claude_week={quota.claude_week_remaining} "
          f"codex_week={quota.codex_week_remaining}")
    return 0


def main() -> int:
    config = config_module.load_config()

    if config.check_myroom:
        return _run_check_myroom(config)
    if config.check_uptime_kuma:
        return _run_check_uptime_kuma(config)
    if config.dump_raw_uptime_kuma:
        return _run_dump_raw_uptime_kuma(config)
    if config.check_vps_status:
        return _run_check_vps_status(config)
    if config.check_ai_quota:
        return _run_check_ai_quota(config)

    led_pins = {
        "led1": config.led1_pin,
        "led2": config.led2_pin,
        "led3": config.led3_pin,
        "led4": config.led4_pin,
    }
    default_led_assignment = {
        "led1": config.default_led1_source,
        "led2": config.default_led2_source,
        "led3": config.default_led3_source,
        "led4": config.default_led4_source,
    }

    state = StateStore(
        default_mode=config.default_lcd_mode,
        default_led_assignment=default_led_assignment,
        default_lcd_page_interval_sec=config.lcd_refresh_interval_sec,
        default_lcd_scroll_interval_sec=config.lcd_scroll_interval_sec,
        default_co2_alert_threshold=config.co2_alert_threshold,
    )
    led_sources = build_led_sources(
        config.myroom_stale_threshold_sec,
        config.cpu_alert_threshold_percent,
    )
    lcd = create_lcd(
        config.lcd_i2c_address, config.lcd_i2c_port, config.mock_hardware, config.debug
    )
    leds = create_led_controllers(led_pins, config.mock_hardware, config.debug)

    worker.start_workers(config, state, lcd, leds, led_sources)

    app = create_app(config, state, led_sources, list(led_pins.keys()))
    app.run(host=config.web_host, port=config.web_port, threaded=True, use_reloader=False, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

