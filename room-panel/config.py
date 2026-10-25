from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


def _bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw, 0)  # base=0 で "0x27" のような16進表記も許容


@dataclass(frozen=True)
class AppConfig:
    web_host: str
    web_port: int

    myroom_api_url: str
    myroom_api_token: str
    myroom_device_id: int
    myroom_stale_threshold_sec: int
    myroom_poll_interval_sec: int

    uptime_kuma_base_url: str
    uptime_kuma_slug: str
    uptime_kuma_poll_interval_sec: int

    system_stats_poll_interval_sec: int
    system_stats_disk_path: str

    vps_status_url: str
    vps_status_token: str
    vps_status_poll_interval_sec: int

    ai_quota_url: str
    ai_quota_token: str
    ai_quota_poll_interval_sec: int

    lcd_i2c_address: int
    lcd_i2c_port: int
    lcd_refresh_interval_sec: int
    lcd_scroll_interval_sec: float
    default_lcd_mode: str

    led1_pin: int
    led2_pin: int
    led3_pin: int
    led4_pin: int
    default_led1_source: str
    default_led2_source: str
    default_led3_source: str
    default_led4_source: str
    heartbeat_blink_interval_sec: float
    heartbeat_stall_threshold_sec: float
    co2_alert_threshold: int
    cpu_alert_threshold_percent: int

    mock_hardware: bool
    fake_sources: bool
    http_timeout: int

    debug: bool
    check_myroom: bool
    check_uptime_kuma: bool
    dump_raw_uptime_kuma: bool
    check_vps_status: bool
    check_ai_quota: bool


def load_config(argv: Optional[list] = None) -> AppConfig:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Room status LCD/LED panel")
    parser.add_argument("--debug", action="store_true", default=_bool_env("DEBUG"))
    parser.add_argument(
        "--check-myroom",
        action="store_true",
        help="MyRoom APIを1回だけ取得して結果を表示し終了する",
    )
    parser.add_argument(
        "--check-uptime-kuma",
        action="store_true",
        help="uptime-kuma APIを1回だけ取得して結果を表示し終了する",
    )
    parser.add_argument(
        "--dump-raw-uptime-kuma",
        action="store_true",
        help="uptime-kumaのstatus-page/heartbeat両エンドポイントの生JSONを表示し終了する",
    )
    parser.add_argument(
        "--check-vps-status",
        action="store_true",
        help="VPS状態APIを1回だけ取得して結果を表示し終了する",
    )
    parser.add_argument(
        "--check-ai-quota",
        action="store_true",
        help="AI利用枠APIを1回だけ取得して結果を表示し終了する",
    )
    args = parser.parse_args(argv)

    return AppConfig(
        web_host=os.getenv("WEB_HOST", "0.0.0.0"),
        web_port=_int_env("WEB_PORT", 8080),
        myroom_api_url=os.getenv("MYROOM_API_URL", ""),
        myroom_api_token=os.getenv("MYROOM_API_TOKEN", ""),
        myroom_device_id=_int_env("MYROOM_DEVICE_ID", 2),
        myroom_stale_threshold_sec=_int_env("MYROOM_STALE_THRESHOLD_SEC", 900),
        myroom_poll_interval_sec=_int_env("MYROOM_POLL_INTERVAL_SEC", 60),
        uptime_kuma_base_url=os.getenv("UPTIME_KUMA_BASE_URL", ""),
        uptime_kuma_slug=os.getenv("UPTIME_KUMA_SLUG", ""),
        uptime_kuma_poll_interval_sec=_int_env("UPTIME_KUMA_POLL_INTERVAL_SEC", 60),
        system_stats_poll_interval_sec=_int_env("SYSTEM_STATS_POLL_INTERVAL_SEC", 5),
        system_stats_disk_path=os.getenv("SYSTEM_STATS_DISK_PATH", "/"),
        vps_status_url=os.getenv("VPS_STATUS_URL", ""),
        vps_status_token=os.getenv("VPS_STATUS_TOKEN", ""),
        vps_status_poll_interval_sec=_int_env("VPS_STATUS_POLL_INTERVAL_SEC", 60),
        ai_quota_url=os.getenv("AI_QUOTA_URL", ""),
        ai_quota_token=os.getenv("AI_QUOTA_TOKEN", ""),
        # 提供元の制限が厳しくサーバー側も5分キャッシュのため、Pi Zero Wでは長めに取る
        ai_quota_poll_interval_sec=_int_env("AI_QUOTA_POLL_INTERVAL_SEC", 300),
        lcd_i2c_address=_int_env("LCD_I2C_ADDRESS", 0x27),
        lcd_i2c_port=_int_env("LCD_I2C_PORT", 1),
        lcd_refresh_interval_sec=_int_env("LCD_REFRESH_INTERVAL_SEC", 2),
        lcd_scroll_interval_sec=float(os.getenv("LCD_SCROLL_INTERVAL_SEC", "2.0")),
        default_lcd_mode=os.getenv("DEFAULT_LCD_MODE", "myroom"),
        led1_pin=_int_env("LED1_PIN", 17),
        led2_pin=_int_env("LED2_PIN", 27),
        led3_pin=_int_env("LED3_PIN", 22),
        led4_pin=_int_env("LED4_PIN", 23),
        default_led1_source=os.getenv("DEFAULT_LED1_SOURCE", "myroom_freshness"),
        default_led2_source=os.getenv("DEFAULT_LED2_SOURCE", "uptime_kuma_overall"),
        default_led3_source=os.getenv("DEFAULT_LED3_SOURCE", "heartbeat"),
        default_led4_source=os.getenv("DEFAULT_LED4_SOURCE", "always_off"),
        heartbeat_blink_interval_sec=float(os.getenv("HEARTBEAT_BLINK_INTERVAL_SEC", "1")),
        heartbeat_stall_threshold_sec=float(os.getenv("HEARTBEAT_STALL_THRESHOLD_SEC", "5")),
        co2_alert_threshold=_int_env("CO2_ALERT_THRESHOLD", 1000),
        cpu_alert_threshold_percent=_int_env("CPU_ALERT_THRESHOLD_PERCENT", 80),
        mock_hardware=_bool_env("MOCK_HARDWARE"),
        fake_sources=_bool_env("FAKE_SOURCES"),
        http_timeout=_int_env("HTTP_TIMEOUT", 10),
        debug=args.debug,
        check_myroom=args.check_myroom,
        check_uptime_kuma=args.check_uptime_kuma,
        dump_raw_uptime_kuma=args.dump_raw_uptime_kuma,
        check_vps_status=args.check_vps_status,
        check_ai_quota=args.check_ai_quota,
    )


