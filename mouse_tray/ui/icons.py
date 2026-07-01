"""Tray icon rendering: digital text icons and bundled ``.ico`` assets."""

from __future__ import annotations

import wx
from PIL import Image, ImageDraw, ImageFont

from ..config import Config
from ..resources import icon_path

# Bundled animation/state icons.
ICON_BATTERY_0 = "battery_0.ico"
ICON_BATTERY_50 = "battery_50.ico"
ICON_BATTERY_100 = "battery_100.ico"
ICON_BATTERY_100_GREEN = "battery_100_green.ico"

_CANVAS = 256


def _pil_to_wx_bitmap(image: Image.Image) -> wx.Bitmap:
    width, height = image.size
    return wx.Bitmap.FromBufferRGBA(width, height, image.tobytes())


def _text_layout(text: str) -> tuple[tuple[int, int], int]:
    """Return (position, font size) tuned per digit count for a 256px canvas."""
    if len(text) >= 3:
        return (0, 58), 150
    if len(text) == 2:
        return (8, 32), 220
    return (70, 32), 220  # single char


class IconRenderer:
    """Builds tray icons from the configured colors/font."""

    def __init__(self, config: Config):
        self.config = config

    def text_icon(self, text: str, color: tuple[int, int, int] | None = None) -> wx.Icon:
        """Render ``text`` (e.g. a battery percent or "Zzz") as a tray icon.

        ``color`` overrides the configured foreground color when given (used for
        the charge-level coloring of the battery percent).
        """
        image = Image.new("RGBA", (_CANVAS, _CANVAS), self.config.background_color)
        draw = ImageDraw.Draw(image)
        position, size = _text_layout(text)
        font = ImageFont.truetype(self.config.font, size)
        draw.text(position, text, font=font, fill=color or self.config.foreground_color)
        icon = wx.Icon()
        icon.CopyFromBitmap(_pil_to_wx_bitmap(image))
        return icon

    @staticmethod
    def file_icon(name: str) -> wx.Icon:
        """Load a bundled ``.ico`` by file name."""
        return wx.Icon(icon_path(name))
