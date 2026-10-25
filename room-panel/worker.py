from __future__ import annotations

import sys
import threading
import time
from typing import Dict, List

import ai_quota_client
import display_modes
import fake_sources
import myroom_client
import system_stats
import uptime_kuma_client
import vps_client
from config import AppConfig
from lcd import LcdDisplay
from led import LedController, LedStatus
from led_sources import HEARTBEAT_SOURCE_ID, LedSource
from state import AppStateSnapshot, StateStore


def poll_loop(
    config: AppConfig,
    state: StateStore,
    lcd: LcdDisplay,
    leds: Dict[str, LedController],
    led_sources: Dict[str, LedSource],
    stop_event: threading.Event,
) -> None:
    next_myroom_poll = 0.0
    next_uptime_poll = 0.0
    next_system_stats_poll = 0.0
    next_vps_status_poll = 0.0
    next_ai_quota_poll = 0.0
    next_lcd_refresh = 0.0
    next_lcd_scroll = 0.0
    page_index = -1
    pages: List = [("", "")]
    was_all_off = False

    while not stop_event.is_set():
        now = time.monotonic()
        try:
            if now >= next_myroom_poll:
                _poll_myroom(config, state)
                next_myroom_poll = now + config.myroom_poll_interval_sec

            if now >= next_uptime_poll:
                _poll_uptime_kuma(config, state)
                next_uptime_poll = now + config.uptime_kuma_poll_interval_sec

            if now >= next_system_stats_poll:
                _poll_system_stats(config, state)
                next_system_stats_poll = now + config.system_stats_poll_interval_sec

            if now >= next_vps_status_poll:
                _poll_vps_status(config, state)
                next_vps_status_poll = now + config.vps_status_poll_interval_sec

            if now >= next_ai_quota_poll:
                _poll_ai_quota(config, state)
                next_ai_quota_poll = now + config.ai_quota_poll_interval_sec

            snapshot = state.snapshot()

            if snapshot.all_off:
                # 全OFF中はLCD/LEDへの出力を止める。切り替わった瞬間だけ消灯操作を行う(毎tick叩かない)。
                if not was_all_off:
                    lcd.clear()
                    for led in leds.values():
                        led.off()
                    was_all_off = True
            else:
                was_all_off = False

                # ページ(表示内容)の切り替え間隔とスクロール(横スライド)の速度は別物として扱う。
                # どちらもWeb UIから変更可能なstate側の値。
                if now >= next_lcd_refresh:
                    mode = display_modes.MODES.get(snapshot.current_mode, display_modes.MODES[display_modes.DEFAULT_MODE_ID])
                    pages = mode.render(snapshot) or [("", "")]
                    page_index = (page_index + 1) % len(pages)
                    next_lcd_refresh = now + snapshot.lcd_page_interval_sec

                if now >= next_lcd_scroll:
                    line1, line2 = pages[page_index]
                    lcd.write_lines(line1, line2)
                    next_lcd_scroll = now + snapshot.lcd_scroll_interval_sec

                _apply_led_sources(snapshot, leds, led_sources)

            state.mark_tick()
        except Exception as exc:  # このtickの異常でスレッド自体は落とさない
            print(f"[poll_loop] error: {exc}", file=sys.stderr)

        stop_event.wait(1.0)


def heartbeat_loop(
    config: AppConfig,
    state: StateStore,
    leds: Dict[str, LedController],
    stop_event: threading.Event,
) -> None:
    while not stop_event.is_set():
        try:
            snapshot = state.snapshot()
            alive = (
                snapshot.last_tick_at is not None
                and (time.monotonic() - snapshot.last_tick_at) < config.heartbeat_stall_threshold_sec
            )
            for led_key, source_id in snapshot.led_assignment.items():
                if source_id != HEARTBEAT_SOURCE_ID:
                    continue
                led = leds.get(led_key)
                if led is None:
                    continue
                if alive and not snapshot.all_off:
                    led.toggle()
                else:
                    led.off()
        except Exception as exc:
            print(f"[heartbeat_loop] error: {exc}", file=sys.stderr)

        stop_event.wait(config.heartbeat_blink_interval_sec)


def start_workers(
    config: AppConfig,
    state: StateStore,
    lcd: LcdDisplay,
    leds: Dict[str, LedController],
    led_sources: Dict[str, LedSource],
) -> tuple:
    stop_event = threading.Event()
    poll_thread = threading.Thread(
        target=poll_loop,
        args=(config, state, lcd, leds, led_sources, stop_event),
        name="poll_loop",
        daemon=True,
    )
    heartbeat_thread = threading.Thread(
        target=heartbeat_loop,
        args=(config, state, leds, stop_event),
        name="heartbeat_loop",
        daemon=True,
    )
    poll_thread.start()
    heartbeat_thread.start()
    return stop_event, (poll_thread, heartbeat_thread)


def _poll_myroom(config: AppConfig, state: StateStore) -> None:
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
        state.update_myroom_success(reading)
    except Exception as exc:
        state.update_myroom_error(str(exc))
        if config.debug:
            print(f"[poll_myroom] {exc}", file=sys.stderr)


def _poll_uptime_kuma(config: AppConfig, state: StateStore) -> None:
    if not config.fake_sources and not (config.uptime_kuma_base_url and config.uptime_kuma_slug):
        return  # 未設定時はスキップ(エラー扱いにしない)
    try:
        if config.fake_sources:
            snapshot = fake_sources.fake_uptime_snapshot()
        else:
            snapshot = uptime_kuma_client.fetch_status(
                config.uptime_kuma_base_url, config.uptime_kuma_slug, config.http_timeout
            )
        state.update_uptime_success(snapshot)
    except Exception as exc:
        state.update_uptime_error(str(exc))
        if config.debug:
            print(f"[poll_uptime_kuma] {exc}", file=sys.stderr)


def _poll_system_stats(config: AppConfig, state: StateStore) -> None:
    try:
        stats = system_stats.read_system_stats(config.system_stats_disk_path)
        state.update_system_stats_success(stats)
    except Exception as exc:
        state.update_system_stats_error(str(exc))
        if config.debug:
            print(f"[poll_system_stats] {exc}", file=sys.stderr)


def _poll_vps_status(config: AppConfig, state: StateStore) -> None:
    if not config.fake_sources and not (config.vps_status_url and config.vps_status_token):
        return  # 未設定時はスキップ(エラー扱いにしない)
    try:
        if config.fake_sources:
            stats = fake_sources.fake_vps_stats()
        else:
            stats = vps_client.fetch_status(
                config.vps_status_url, config.vps_status_token, config.http_timeout
            )
        state.update_vps_stats_success(stats)
    except Exception as exc:
        state.update_vps_stats_error(str(exc))
        if config.debug:
            print(f"[poll_vps_status] {exc}", file=sys.stderr)


def _poll_ai_quota(config: AppConfig, state: StateStore) -> None:
    if not config.fake_sources and not (config.ai_quota_url and config.ai_quota_token):
        return  # 未設定時はスキップ(エラー扱いにしない)
    try:
        if config.fake_sources:
            quota = fake_sources.fake_ai_quota()
        else:
            quota = ai_quota_client.fetch_quota(
                config.ai_quota_url, config.ai_quota_token, config.http_timeout
            )
        state.update_ai_quota_success(quota)
    except Exception as exc:
        state.update_ai_quota_error(str(exc))
        if config.debug:
            print(f"[poll_ai_quota] {exc}", file=sys.stderr)


def _apply_led_sources(
    snapshot: AppStateSnapshot, leds: Dict[str, LedController], led_sources: Dict[str, LedSource]
) -> None:
    for led_key, source_id in snapshot.led_assignment.items():
        if source_id == HEARTBEAT_SOURCE_ID:
            continue  # heartbeat_loopが担当
        led = leds.get(led_key)
        source = led_sources.get(source_id)
        if led is None or source is None:
            continue
        status: LedStatus = source.compute(snapshot)
        if snapshot.led_invert.get(source_id, False):
            status = status.inverted()
        led.apply(status)

