"""Tray icon rendering: digital text icons and procedural battery icons.

Two renderers, both producing a fully transparent-background ``wx.Icon``:

* :meth:`IconRenderer.text_icon` -- PIL draws the percent digits onto an RGBA
  canvas.
* :meth:`IconRenderer.battery_icon` -- an SVG template is filled in with the
  requested color and charge level, then rasterized by ``wx.svg`` (NanoSVG,
  bundled with wxPython -- no extra dependency).

The transparency rule for both paths is the same: keep a real alpha channel all
the way to ``wx.Icon.CopyFromBitmap``. A 32-bit ``wx.Bitmap`` with alpha
survives the copy intact; what does *not* survive is drawing through a
``wx.MemoryDC``/``wx.Bitmap(w, h)`` pair, because that bitmap has no alpha
channel and the SVG's empty areas come out opaque black.
"""

from __future__ import annotations

from functools import lru_cache

import wx
import wx.svg
from PIL import Image, ImageDraw, ImageFont

from ..config import Config
from ..resources import icon_path

_CANVAS = 256

# Battery geometry, in the 256x256 viewBox below (matches the hand-drawn .ico
# assets this replaced): a 16px-thick rounded shell, a nub on the right, and a
# fill bar inset by 16px inside the shell's cavity.
_FILL_X = 40
_FILL_Y = 104
_FILL_W = 160
_FILL_H = 64

_BATTERY_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <rect x="226" y="108" width="22" height="56" rx="8" fill="{color}"/>
  <rect x="16" y="80" width="208" height="112" rx="20"
        fill="none" stroke="{color}" stroke-width="16"/>
  <rect x="{fill_x}" y="{fill_y}" width="{fill_w}" height="{fill_h}" rx="8" fill="{color}"/>
</svg>"""


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


@lru_cache(maxsize=32)
def _render_battery(level: int, color: tuple[int, int, int]) -> wx.Icon:
    """Rasterize the battery SVG at ``level`` percent in ``color``.

    Cached because the charging animation re-requests the same few frames every
    tick; the cache is keyed on the color too, so a settings change simply
    lands on new keys.
    """
    width = round(_FILL_W * max(0, min(100, level)) / 100)
    svg = _BATTERY_SVG.format(
        color="#%02X%02X%02X" % color,
        fill_x=_FILL_X,
        fill_y=_FILL_Y,
        # A zero-width rect still paints its rounded corners, so drop it.
        fill_w=width if width else 0,
        fill_h=_FILL_H if width else 0,
    )
    image = wx.svg.SVGimage.CreateFromBytes(svg.encode("utf-8"))
    bitmap = image.ConvertToScaledBitmap(wx.Size(_CANVAS, _CANVAS))
    icon = wx.Icon()
    icon.CopyFromBitmap(bitmap)  # 32-bit source -> alpha is preserved
    return icon


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

    def battery_icon(self, level: int, color: tuple[int, int, int] | None = None) -> wx.Icon:
        """Render a battery filled to ``level`` percent (0-100) as a tray icon.

        ``color`` overrides the configured foreground color (used for the green
        "fully charged" icon).
        """
        return _render_battery(level, tuple(color or self.config.foreground_color))

    @staticmethod
    def file_icon(name: str) -> wx.Icon:
        """Load a bundled ``.ico`` by file name."""
        return wx.Icon(icon_path(name))
