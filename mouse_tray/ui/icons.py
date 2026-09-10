"""Tray icon rendering: digital text icons and procedural battery icons.

Two renderers, both producing a fully transparent-background ``wx.Icon`` at the
native tray size (16px at 100% DPI, scaled up with the display):

* :meth:`IconRenderer.text_icon` -- PIL draws the percent digits (or a short
  status glyph) at 4x supersampling and shrinks the result with LANCZOS, so the
  tray gets a crisp ready-to-use bitmap instead of a big canvas Windows would
  mush down with a cheap filter. Short strings share the size fitted to the
  widest pair and the two three-char strings their own size, each centered by
  its measured ink box in whatever font is configured and scaled to the
  preferred percent of that fit (past it, wide strings overflow -- previewed
  live). A thin contrasting outline keeps the glyphs readable on any taskbar
  theme.
* :meth:`IconRenderer.battery_icon` -- an SVG template is filled in with the
  requested color and charge level, then rasterized by ``wx.svg`` (NanoSVG,
  bundled with wxPython -- no extra dependency) straight at the native size.

The transparency rule for both paths is the same: keep a real alpha channel all
the way to ``wx.Icon.CopyFromBitmap``. A 32-bit ``wx.Bitmap`` with alpha
survives the copy intact; what does *not* survive is drawing through a
``wx.MemoryDC``/``wx.Bitmap(w, h)`` pair, because that bitmap has no alpha
channel and the SVG's empty areas come out opaque black.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import wx
import wx.svg
from PIL import Image, ImageDraw, ImageFont

from ..config import TEXT_SIZE_DEFAULT, TEXT_SIZE_MAX, TEXT_SIZE_MIN, Config
from ..resources import icon_path

#: Tray edge in physical pixels when the DPI scale is unavailable.
_NATIVE_DEFAULT = 16

#: Text supersampling: glyphs are drawn this many times larger, then shrunk to
#: the native icon size with LANCZOS.
_TEXT_SS = 4

#: Scratch size for the first measurement (independent of the canvas).
_TEXT_REF_SIZE = 100

#: Margin around the text box, as a fraction of the canvas. Just enough to
#: absorb AA -- the old 12/256 left needlessly small digits, and this margin is
#: the main lever on digit size.
_TEXT_MARGIN_FRAC = 4 / 256

#: Strings the tray can show, split by the two shared em sizes: everything of
#: up to two chars is fitted to the widest pair (so the widest pair of an
#: exotic font still binds -- fitting all strings to the widest triple would
#: shrink the common one- and two-digit readouts), while the two three-char
#: strings get their own smaller size. One-digit percents need no entry -- any
#: pair's ink box contains each of its digits'.
_SIZE_REF_SHORT = (*(str(n) for n in range(10, 100)), "-", "?")
_SIZE_REF_LONG = ("100", "Zzz")

# Battery geometry, in the 256x256 viewBox below (matches the hand-drawn .ico
# assets this replaced): a 16px-thick rounded shell, a nub on the right, and a
# fill bar inset by 16px inside the shell's cavity -- the whole glyph centered
# on the canvas (shell middle at y=128).
_FILL_X = 40
_FILL_Y = 96
_FILL_W = 160
_FILL_H = 64

_BATTERY_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <rect x="226" y="100" width="22" height="56" rx="8" fill="{color}"/>
  <rect x="16" y="72" width="208" height="112" rx="20"
        fill="none" stroke="{color}" stroke-width="16"/>
  <rect x="{fill_x}" y="{fill_y}" width="{fill_w}" height="{fill_h}" rx="8" fill="{color}"/>
</svg>"""


def _pil_to_wx_bitmap(image: Image.Image) -> wx.Bitmap:
    width, height = image.size
    return wx.Bitmap.FromBufferRGBA(width, height, image.tobytes())


def _outline_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    """Black or white, whichever contrasts with a glyph ``color`` fill.

    The icon floats on whatever taskbar theme the user runs, so light digits get
    a dark outline and dark digits a light one -- either way the shape survives
    a same-colored background.
    """
    red, green, blue = color
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    return (0, 0, 0) if luminance > 0.5 else (255, 255, 255)


@dataclass(frozen=True)
class _TextSpec:
    """How to draw one text icon: geometry plus the requested size percent."""

    canvas: int  # supersampled edge; shrunk to native after drawing
    box: int  # usable square the ink (outline included) must fit
    cap: int  # largest em size the reference fit may return
    stroke: int  # outline width
    pct: int  # percent of the fitted size to actually draw
    native: int  # tray edge in physical pixels (the shrink target)


def _text_spec(size_px: int, pct: int = TEXT_SIZE_DEFAULT) -> _TextSpec:
    """Render spec for a native icon edge of ``size_px`` (both sanitized)."""
    native = max(8, int(size_px))
    pct = max(TEXT_SIZE_MIN, min(TEXT_SIZE_MAX, int(pct)))
    canvas = native * _TEXT_SS
    box = canvas - 2 * max(1, round(canvas * _TEXT_MARGIN_FRAC))
    # Outline ~0.5px at 100% DPI, growing with the icon; capped so it never
    # eats more than a quarter of the text box on tiny icons.
    stroke = min(max(2, round(box / 28)), max(1, box // 4))
    return _TextSpec(canvas, box, box, stroke, pct, native)


def tray_icon_size(window: wx.Window) -> int:
    """Native tray edge in physical pixels for ``window``'s display.

    Rendering at exactly this size is what keeps the icons crisp: the shell
    shows the bitmaps as-is instead of rescaling them. Falls back to 16 when
    the scale is unavailable or absurd; on a mixed-DPI desk the icon may be
    rescaled on a non-primary monitor, degrading to roughly the old quality.
    """
    try:
        scale = float(window.GetDPIScaleFactor())
    except Exception:  # unknown DPI (BLE deliberately unselected: keep it broad)
        return _NATIVE_DEFAULT
    if not 0.5 <= scale <= 4.0:
        return _NATIVE_DEFAULT
    return round(_NATIVE_DEFAULT * scale)


@lru_cache(maxsize=8)
def _reference_size(font_path: str, spec: _TextSpec, candidates: tuple[str, ...]) -> int:
    """Em size at which every candidate fits the spec box, scaled to percent.

    The estimate comes from scratch-size ratios; the loop then verifies each
    candidate at the real size *with* the outline and steps down until all fit.
    Called once per tier (see :data:`_SIZE_REF_SHORT` / :data:`_SIZE_REF_LONG`),
    and the result is scaled to ``pct`` of that fit -- ``TEXT_SIZE_DEFAULT``
    renders the fit itself, lower values shrink, higher values grow past it
    (wide strings then overflow, by explicit user choice).
    """
    scratch = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    ref_font = ImageFont.truetype(font_path, _TEXT_REF_SIZE)
    estimates = []
    for text in candidates:
        left, top, right, bottom = scratch.textbbox((0, 0), text, font=ref_font)
        width, height = right - left, bottom - top
        if width > 0 and height > 0:
            estimates.append(round(_TEXT_REF_SIZE * min(spec.box / width, spec.box / height)))
    size = max(8, min(spec.cap, min(estimates, default=spec.cap)))
    font = ImageFont.truetype(font_path, size)
    while size > 8 and _overflows(scratch, font, spec, candidates):
        size -= 4
        font = ImageFont.truetype(font_path, size)
    return max(8, round(size * spec.pct / TEXT_SIZE_DEFAULT))


def _overflows(
    draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, spec: _TextSpec, candidates: tuple[str, ...]
) -> bool:
    """Whether any candidate string exceeds the spec box as drawn."""
    for text in candidates:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=spec.stroke)
        if max(right - left, bottom - top) > spec.box:
            return True
    return False


def _fit_text(
    draw: ImageDraw.ImageDraw, text: str, font_path: str, spec: _TextSpec
) -> tuple[ImageFont.FreeTypeFont, tuple[int, int]]:
    """The tier's em size in ``font_path``, plus the origin centering ``text``.

    Short strings share the size fitted to the widest pair and long ones the
    size fitted to ``"100"``/``"Zzz"``, scaled to the requested percent (see
    :func:`_reference_size`); past the fit wide strings overflow, which is the
    user's explicit choice and previews live, so nothing here shrinks it back.
    The origin comes from this string's own ink box -- the real extent in this
    font, outline included -- measured with the default ``la`` anchor that
    ``draw.text`` shares, so the box maps straight to where the ink lands.
    """
    # "100"/"Zzz" are the only 3-char strings; anything longer takes the long
    # tier as well (no other string exists today).
    candidates = _SIZE_REF_LONG if len(text) >= 3 else _SIZE_REF_SHORT
    size = _reference_size(font_path, spec, candidates)
    font = ImageFont.truetype(font_path, size)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=spec.stroke)
    if right - left <= 0 or bottom - top <= 0:  # whitespace only, e.g. the startup placeholder
        return font, (0, 0)
    x = round((spec.canvas - (right - left)) / 2 - left)
    y = round((spec.canvas - (bottom - top)) / 2 - top)
    return font, (x, y)


@lru_cache(maxsize=64)
def _render_text(
    text: str,
    color: tuple[int, int, int],
    font_path: str,
    background: tuple[int, int, int, int],
    spec: _TextSpec,
) -> wx.Icon:
    """Draw ``text`` centered at the native tray size on a transparent canvas.

    Glyphs are drawn supersampled and shrunk with LANCZOS, and carry a thin
    contrasting outline so they stay readable on any taskbar theme. Cached like
    :func:`_render_battery`: the poll loop re-requests the same few strings
    ("Zzz", "-", a steady percent) tick after tick, and a font, color, size or
    icon-size change simply lands on new keys (the spec carries the last two).
    """
    image = Image.new("RGBA", (spec.canvas, spec.canvas), background)
    draw = ImageDraw.Draw(image)
    font, position = _fit_text(draw, text, font_path, spec)
    draw.text(
        position, text, font=font, fill=color,
        stroke_width=spec.stroke, stroke_fill=_outline_color(color),
    )
    icon = wx.Icon()
    icon.CopyFromBitmap(_pil_to_wx_bitmap(image.resize((spec.native, spec.native), Image.LANCZOS)))
    return icon


@lru_cache(maxsize=32)
def _render_battery(level: int, color: tuple[int, int, int], size_px: int) -> wx.Icon:
    """Rasterize the battery SVG at ``level`` percent in ``color``.

    Rasterized straight at the native tray size -- vectors scale perfectly, so
    this path needs no supersampling step. Cached because the charging animation
    re-requests the same few frames every tick; the cache is keyed on the color
    (and size) too, so a settings change simply lands on new keys.
    """
    width = round(_FILL_W * max(0, min(100, level)) / 100)
    svg = _BATTERY_SVG.format(
        color="#{:02X}{:02X}{:02X}".format(*color),
        fill_x=_FILL_X,
        fill_y=_FILL_Y,
        # A zero-width rect still paints its rounded corners, so drop it.
        fill_w=width if width else 0,
        fill_h=_FILL_H if width else 0,
    )
    image = wx.svg.SVGimage.CreateFromBytes(svg.encode("utf-8"))
    bitmap = image.ConvertToScaledBitmap(wx.Size(size_px, size_px))
    icon = wx.Icon()
    icon.CopyFromBitmap(bitmap)  # 32-bit source -> alpha is preserved
    return icon


class IconRenderer:
    """Builds tray icons from the configured colors/font, at the native size."""

    def __init__(self, config: Config, icon_size: int = _NATIVE_DEFAULT):
        self.config = config
        self.icon_size = min(64, max(8, int(icon_size)))
        #: Live settings preview: when set, text renders in this font instead
        #: of the configured one (poll ticks keep repainting through it).
        self.preview_font: str | None = None
        #: Live settings preview for the text size (percent); see preview_font.
        self.preview_text_size: int | None = None

    def text_icon(self, text: str, color: tuple[int, int, int] | None = None) -> wx.Icon:
        """Render ``text`` (e.g. a battery percent or "Zzz") as a tray icon.

        Short strings share the size fitted to the widest pair and the two
        three-char strings their own size, each centered by its own ink box in
        the configured font (or the live settings preview font/size) and scaled
        to the size percent -- past the fit, wide strings overflow by explicit
        user choice. A contrasting outline keeps it readable on any taskbar
        theme. ``color`` overrides the configured foreground color when given
        (used for the charge-level coloring of the battery percent).
        """
        fill = tuple(color or self.config.foreground_color)
        font = self.preview_font or self.config.font
        pct = self.preview_text_size if self.preview_text_size is not None else self.config.text_size
        spec = _text_spec(self.icon_size, pct)
        return _render_text(text, fill, font, self.config.background_color, spec)

    def battery_icon(self, level: int, color: tuple[int, int, int] | None = None) -> wx.Icon:
        """Render a battery filled to ``level`` percent (0-100) as a tray icon.

        ``color`` overrides the configured foreground color (used for the green
        "fully charged" icon).
        """
        return _render_battery(level, tuple(color or self.config.foreground_color), self.icon_size)

    @staticmethod
    def file_icon(name: str) -> wx.Icon:
        """Load a bundled ``.ico`` by file name."""
        return wx.Icon(icon_path(name))
