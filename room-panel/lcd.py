from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from typing import Optional

WIDTH = 16
# スクロール時、末尾から先頭へループする際に挟む空白文字数(区切りが分かるように)
SCROLL_GAP = 4


def scroll_window(text: str, offset: int) -> str:
    """textがWIDTHに収まらない場合、offset文字目からWIDTH文字分を切り出す(末尾は先頭にループ)。"""
    if len(text) <= WIDTH:
        return text.ljust(WIDTH)
    looped = text + " " * SCROLL_GAP
    doubled = looped + looped
    offset %= len(looped)
    return doubled[offset : offset + WIDTH]


class _LineScroller:
    """1行分のスクロール位置を保持する。renderされた文字列が変わったら先頭へ戻す。"""

    def __init__(self) -> None:
        self._text: Optional[str] = None
        self._offset = 0

    def next(self, text: str) -> str:
        if text != self._text:
            self._text = text
            self._offset = 0
        window = scroll_window(text, self._offset)
        if len(text) > WIDTH:
            self._offset += 1
        return window


class LcdDisplay(ABC):
    @abstractmethod
    def write_lines(self, line1: str, line2: str) -> None:
        ...

    @abstractmethod
    def clear(self) -> None:
        ...


class MockLcdDisplay(LcdDisplay):
    """実LCDの代わりに標準出力へ描画内容を出す（--debug時のみ表示）。"""

    def __init__(self, debug: bool = False) -> None:
        self._debug = debug
        self._scrollers = (_LineScroller(), _LineScroller())
        self._last: tuple = (None, None)

    def write_lines(self, line1: str, line2: str) -> None:
        rendered1 = self._scrollers[0].next(line1)
        rendered2 = self._scrollers[1].next(line2)
        if (rendered1, rendered2) == self._last:
            return
        self._last = (rendered1, rendered2)
        if self._debug:
            print(f"[LCD] {rendered1!r} / {rendered2!r}", file=sys.stderr)

    def clear(self) -> None:
        self._last = (None, None)


class RplcdDisplay(LcdDisplay):
    """RPLCD + smbus2 経由でI2C接続(PCF8574バックパック)の16x2キャラクターLCDへ描画する。

    基板上に青いトリマー(可変抵抗)がはんだ付けされている一般的なI2C 1602 LCDを想定。
    コントラスト調整は基板上のトリマーで完結するため外付け配線は不要。
    I2Cアドレスは基板により 0x27 か 0x3F が多い（`i2cdetect -y 1` で確認）。
    """

    def __init__(self, i2c_address: int, i2c_port: int) -> None:
        # importをここに置き、非Pi環境でもモジュール自体はロードできるようにする
        from RPLCD.i2c import CharLCD

        self._lcd = CharLCD(
            i2c_expander="PCF8574",
            address=i2c_address,
            port=i2c_port,
            cols=WIDTH,
            rows=2,
            auto_linebreaks=False,
        )
        self._scrollers = (_LineScroller(), _LineScroller())
        self._last: tuple = (None, None)

    def write_lines(self, line1: str, line2: str) -> None:
        rendered1 = self._scrollers[0].next(line1)
        rendered2 = self._scrollers[1].next(line2)
        if (rendered1, rendered2) == self._last:
            return
        try:
            self._lcd.cursor_pos = (0, 0)
            self._lcd.write_string(rendered1)
            self._lcd.cursor_pos = (1, 0)
            self._lcd.write_string(rendered2)
            self._last = (rendered1, rendered2)
        except OSError:
            # I2Cグリッチ: このフレームはスキップし、次tickで再試行させる
            self._last = (None, None)

    def clear(self) -> None:
        self._lcd.clear()
        self._last = (None, None)


def create_lcd(i2c_address: int, i2c_port: int, mock_hardware: bool, debug: bool) -> LcdDisplay:
    if mock_hardware:
        return MockLcdDisplay(debug=debug)
    try:
        return RplcdDisplay(i2c_address, i2c_port)
    except Exception as exc:  # ImportError, OSError(I2Cオープン失敗) 等
        print(f"[lcd] ハードウェア初期化に失敗、モックにフォールバック: {exc}", file=sys.stderr)
        return MockLcdDisplay(debug=debug)

