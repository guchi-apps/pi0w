from __future__ import annotations

import sys
from enum import Enum
from typing import Dict, Optional


class LedStatus(str, Enum):
    ON = "on"
    OFF = "off"
    BLINK = "blink"  # UNKNOWN(判定不能/取得失敗)を示す低速点滅

    def inverted(self) -> "LedStatus":
        """ON/OFFを反転させる。BLINK(判定不能)は反転せずそのまま返す。"""
        if self is LedStatus.ON:
            return LedStatus.OFF
        if self is LedStatus.OFF:
            return LedStatus.ON
        return self


class LedController:
    """1個の物理LEDを抽象化する。gpiozeroのLEDオブジェクト(実物 or Mock)をラップする。"""

    def __init__(self, name: str, gpio_led) -> None:
        self._name = name
        self._led = gpio_led
        self._status: Optional[LedStatus] = None

    def apply(self, status: LedStatus) -> None:
        if status == self._status:
            return
        self._status = status
        if status == LedStatus.ON:
            self._led.off()  # blinkを止めてから
            self._led.on()
        elif status == LedStatus.OFF:
            self._led.off()
        else:  # BLINK
            self._led.blink(on_time=0.5, off_time=0.5, background=True)

    def toggle(self) -> None:
        """heartbeat専用: blinkではなく能動的にON/OFFを反転させる。"""
        self._status = None  # blink状態のキャッシュを無効化
        self._led.toggle()

    def off(self) -> None:
        self._status = LedStatus.OFF
        self._led.off()


def create_led_controllers(
    pins: Dict[str, int], mock_hardware: bool, debug: bool
) -> Dict[str, LedController]:
    """led1/led2/led3 の LedController を生成する。

    ハードウェア初期化に失敗した場合は gpiozero 標準の MockFactory へ
    プロセス全体でフォールバックする(自前Mock実装は書かない)。
    """
    from gpiozero import LED

    if mock_hardware:
        _force_mock_factory(debug)
    else:
        try:
            # 実ピンでの初期化を試み、失敗すればMockFactoryへ切り替える
            probe = LED(list(pins.values())[0])
            probe.close()
        except Exception as exc:
            print(f"[led] ハードウェア初期化に失敗、モックにフォールバック: {exc}", file=sys.stderr)
            _force_mock_factory(debug)

    controllers = {}
    for name, pin in pins.items():
        controllers[name] = LedController(name, LED(pin))
    return controllers


def _force_mock_factory(debug: bool) -> None:
    from gpiozero import Device
    from gpiozero.pins.mock import MockFactory

    Device.pin_factory = MockFactory()
    if debug:
        print("[led] MockFactory を使用します（GPIOハードウェアなし）", file=sys.stderr)

