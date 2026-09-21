"""Settings dialog: edit the user-tunable config (poll rate, font, color, debug).

The dialog only knows how to read/write a :class:`Config`; persisting the result
and refreshing the running tray is the caller's job (see ``app._open_settings``).

The font picker lists monospaced faces by default (the indicator wants
fixed-width digits) and previews each one in its own face; the "Show all fonts"
checkbox widens it to every installed face. Face names are resolved back to a
``.ttf``/``.otf`` file so PIL can load them. Every font, text-size or outline
change is also offered to the caller for a live tray repaint, without waiting
for OK.
"""

from __future__ import annotations

import os
import winreg
from collections.abc import Callable

import wx
import wx.adv
from PIL import ImageFont

from ..build_info import version_string
from ..config import LOW_THRESHOLD, MID_THRESHOLD, TEXT_SIZE_MAX, TEXT_SIZE_MIN, Config
from ..logging_setup import open_log
from ..resources import icon_path


def open_settings(
    parent: wx.Window,
    config: Config,
    *,
    on_font_preview: Callable[[str | None], None] | None = None,
    on_size_preview: Callable[[int], None] | None = None,
    on_outline_preview: Callable[[bool], None] | None = None,
) -> bool:
    """Show the modal settings dialog, centered on screen.

    On OK the edited values are written back onto ``config`` in place and
    ``True`` is returned; on Cancel nothing changes and ``False`` is returned.
    ``on_font_preview`` fires with the picked font file every time the font
    selection changes (``None`` when it clears), ``on_size_preview`` with the
    slider value and ``on_outline_preview`` with the checkbox state, so the
    caller can repaint the tray live; the caller must drop the previews when
    this returns.
    """
    dialog = _SettingsDialog(parent, config, on_font_preview, on_size_preview, on_outline_preview)
    try:
        if dialog.ShowModal() != wx.ID_OK:
            return False
        dialog.apply_to(config)
        return True
    finally:
        dialog.Destroy()


def _font_files() -> dict[str, str]:
    """Map a lowercased font face name to its absolute font file (Windows).

    Built from the per-machine and per-user font registry keys. The regular
    weight of a family wins because its value name (e.g. ``"Consolas
    (TrueType)"``) strips to the bare face name, while ``"Consolas Bold"`` does
    not collide with it.
    """
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    result: dict[str, str] = {}
    roots = (
        (winreg.HKEY_LOCAL_MACHINE, R"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
        (winreg.HKEY_CURRENT_USER, R"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
    )
    for hive, path in roots:
        try:
            key = winreg.OpenKey(hive, path)
        except OSError:
            continue
        with key:
            index = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                if not value:
                    continue
                face = name.split(" (")[0].strip().lower()
                file = value if os.path.isabs(value) else os.path.join(fonts_dir, value)
                result.setdefault(face, file)
    return result


def _collect_faces() -> tuple[list[str], set[str], dict[str, str], dict[str, str]]:
    """Every installed face plus the lookups the picker and previews need.

    Returns the sorted face list, the lowercased monospaced faces, and the
    face-to-file / file-to-face maps (built from :func:`_font_files`).
    """
    file_map = _font_files()
    all_faces = sorted(
        face
        for face in wx.FontEnumerator.GetFacenames()
        if not face.startswith("@") and face.lower() in file_map
    )
    mono_faces = {
        face.lower()
        for face in wx.FontEnumerator.GetFacenames(fixedWidthOnly=True)
        if not face.startswith("@")
    }
    face_to_path = {face: file_map[face.lower()] for face in all_faces}
    path_to_face = {
        os.path.basename(path).lower(): face for face, path in face_to_path.items()
    }
    return all_faces, mono_faces, face_to_path, path_to_face


def _rgb(picker: wx.ColourPickerCtrl) -> tuple[int, int, int]:
    colour = picker.GetColour()
    return (colour.Red(), colour.Green(), colour.Blue())


class _FontPicker(wx.adv.OwnerDrawnComboBox):
    """Read-only combo that previews each face in its own font."""

    def __init__(self, parent: wx.Window, faces: list[str]):
        super().__init__(parent, choices=faces, style=wx.CB_READONLY)
        self._faces = faces

    def set_faces(self, faces: list[str]) -> None:
        """Replace the list of faces, keeping the owner-drawn preview working."""
        self._faces = faces
        self.Set(faces)

    def OnDrawItem(  # noqa: N802 (wx override)
        self, dc: wx.DC, rect: wx.Rect, item: int, flags: int
    ) -> None:
        if item == wx.NOT_FOUND:
            return
        face = self._faces[item]
        dc.SetFont(
            wx.Font(11, wx.FONTFAMILY_MODERN, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName=face)
        )
        # The closed control also arrives with the SELECTED flag; it paints its
        # own light field background, so the text must stay dark there --
        # highlight white would turn white-on-white.
        selected = bool(flags & wx.adv.ODCB_PAINTING_SELECTED)
        in_control = bool(flags & wx.adv.ODCB_PAINTING_CONTROL)
        colour = (
            wx.SYS_COLOUR_HIGHLIGHTTEXT if selected and not in_control else wx.SYS_COLOUR_WINDOWTEXT
        )
        dc.SetTextForeground(wx.SystemSettings.GetColour(colour))
        dc.DrawText(face, rect.x + 4, rect.y + (rect.height - dc.GetCharHeight()) // 2)

    def OnMeasureItem(self, item: int) -> int:  # noqa: N802 (wx override)
        return 24


class _SettingsDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        config: Config,
        on_font_preview: Callable[[str | None], None] | None,
        on_size_preview: Callable[[int], None] | None,
        on_outline_preview: Callable[[bool], None] | None,
    ):
        super().__init__(parent, title=f"{config.display_name} {version_string()} settings")
        self.SetIcon(wx.Icon(icon_path("app.ico")))
        self._on_font_preview = on_font_preview
        self._on_size_preview = on_size_preview
        self._on_outline_preview = on_outline_preview

        self._all_faces, self._mono_faces, self._face_to_path, self._path_to_face = _collect_faces()

        grid = wx.FlexGridSizer(rows=9, cols=2, vgap=8, hgap=8)
        grid.AddGrowableCol(1, 1)

        grid.Add(wx.StaticText(self, label="Poll interval (s):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self._poll = wx.SpinCtrl(self, min=1, max=3600, initial=int(config.poll_rate))
        grid.Add(self._poll, 0, wx.EXPAND)

        self._build_font_section(grid)

        self._build_size_row(grid, config.text_size)

        self._text_outline = self._add_checkbox(
            grid,
            "Text outline:",
            config.text_outline,
            "Draw a contrasting outline around the tray digits.\n"
            "Keeps them readable on a same-colored taskbar.",
        )
        self._text_outline.Bind(wx.EVT_CHECKBOX, self._on_outline)

        self._build_color_row(grid, config)

        self._dynamic_color = self._add_checkbox(
            grid,
            "Color by charge level:",
            config.dynamic_color,
            "Color the battery percent by charge: the font color\n"
            f"above {MID_THRESHOLD}%, then the two colors picked next to it\n"
            f"at ≤ {MID_THRESHOLD}% and ≤ {LOW_THRESHOLD}%.",
        )
        self._dynamic_color.Bind(wx.EVT_CHECKBOX, self._on_dynamic_color)
        self._battery_icon = self._add_checkbox(
            grid,
            "Show battery icon:",
            config.battery_icon,
            "Draw a battery filled to the charge level instead of\n"
            "the percent digits. The exact number moves to the\n"
            "tray tooltip.",
        )
        self._debug = self._add_checkbox(grid, "Debug logging:", config.debug)

        reset = wx.Button(self, label="Reset to defaults")
        reset.Bind(wx.EVT_BUTTON, self._on_reset)
        show_log = wx.Button(self, label="Open log")
        show_log.SetToolTip("Open app.log -- attach it when reporting a problem.")
        show_log.Bind(wx.EVT_BUTTON, lambda _evt: open_log(config.app_name))
        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)

        bottom = wx.BoxSizer(wx.HORIZONTAL)
        bottom.Add(reset, 0)
        bottom.Add(show_log, 0, wx.LEFT, 8)
        bottom.AddStretchSpacer()
        bottom.Add(buttons, 0)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(grid, 0, wx.EXPAND | wx.ALL, 12)
        outer.Add(bottom, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.SetSizerAndFit(outer)
        self.SetMinSize(self.GetSize())
        self.CentreOnScreen()

        self._restore_font_selection(config)
        # Hide after fitting: the dialog keeps the width of the shown state, so
        # toggling the checkbox never resizes the window under the cursor.
        self._update_bands()
        # Validate the chosen font before the OK button closes the dialog.
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    # --- helpers ------------------------------------------------------------

    def _add_checkbox(
        self, grid: wx.FlexGridSizer, label: str, value: bool, tip: str | None = None
    ) -> wx.CheckBox:
        """Append a labelled checkbox row; the tooltip covers both cells."""
        text = wx.StaticText(self, label=label)
        box = wx.CheckBox(self)
        box.SetValue(value)
        if tip:
            text.SetToolTip(tip)
            box.SetToolTip(tip)
        grid.Add(text, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(box, 0, wx.ALIGN_CENTER_VERTICAL)
        return box

    def _build_font_section(self, grid: wx.FlexGridSizer) -> None:
        """Append the font picker row and the "Show all fonts" checkbox."""
        self._font_label = wx.StaticText(self, label="Font (monospaced):")
        grid.Add(self._font_label, 0, wx.ALIGN_CENTER_VERTICAL)
        self._font = _FontPicker(self, list(self._all_faces))
        self._font.Bind(wx.EVT_COMBOBOX, self._on_font_selected)
        grid.Add(self._font, 1, wx.EXPAND)

        self._all_fonts = self._add_checkbox(
            grid,
            "Show all fonts:",
            False,
            "List every installed font, not just monospaced ones.\n"
            "The digits are measured in the chosen face, so any font fits.",
        )
        self._all_fonts.Bind(wx.EVT_CHECKBOX, self._on_all_fonts)

    def _build_size_row(self, grid: wx.FlexGridSizer, text_size: int) -> None:
        """Append the text-size slider row with its live percent label."""
        grid.Add(wx.StaticText(self, label="Text size:"), 0, wx.ALIGN_CENTER_VERTICAL)
        size_value = min(TEXT_SIZE_MAX, max(TEXT_SIZE_MIN, text_size))
        self._size = wx.Slider(
            self, minValue=TEXT_SIZE_MIN, maxValue=TEXT_SIZE_MAX, value=size_value,
            style=wx.SL_HORIZONTAL,
        )
        self._size.SetToolTip(
            "Scale the tray digits.\n100% fills the icon; lower values shrink."
        )
        self._size_label = wx.StaticText(self, label=f"{size_value}%")
        # Reserve the widest value's width so the row never jumps; measured in
        # the label's own font, so it survives DPI scaling (a fixed 40px clipped
        # the "%" at 150%).
        widest = self._size_label.GetTextExtent(f"{TEXT_SIZE_MAX}%").width
        self._size_label.SetMinSize((widest, -1))
        self._size.Bind(wx.EVT_SLIDER, self._on_size_changed)
        size_row = wx.BoxSizer(wx.HORIZONTAL)
        size_row.Add(self._size, 1, wx.ALIGN_CENTER_VERTICAL)
        size_row.Add(self._size_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        grid.Add(size_row, 1, wx.EXPAND)

    def _build_color_row(self, grid: wx.FlexGridSizer, config: Config) -> None:
        """Append the font color picker with its low-band pickers."""
        grid.Add(wx.StaticText(self, label="Font color:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self._color = wx.ColourPickerCtrl(self, colour=wx.Colour(*config.foreground_color))
        self._mid_color = wx.ColourPickerCtrl(self, colour=wx.Colour(*config.mid_color))
        self._low_color = wx.ColourPickerCtrl(self, colour=wx.Colour(*config.low_color))
        # The low-band pickers sit next to the font color -- it is the color of
        # the top band -- and only show up while "Color by charge level" is on.
        colors = wx.BoxSizer(wx.HORIZONTAL)
        colors.Add(self._color, 0, wx.ALIGN_CENTER_VERTICAL)
        self._band_widgets: list[wx.Window] = []
        for threshold, picker in ((MID_THRESHOLD, self._mid_color), (LOW_THRESHOLD, self._low_color)):
            text = wx.StaticText(self, label=f"≤ {threshold}%:")
            colors.Add(text, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)
            colors.Add(picker, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
            self._band_widgets += [text, picker]
        grid.Add(colors, 1, wx.EXPAND)

    def _restore_font_selection(self, config: Config) -> None:
        """Show the saved font, widening the list for a proportional face."""
        # Start widened if the saved font is a proportional face, so it shows.
        current_face = self._path_to_face.get(os.path.basename(config.font).lower())
        self._all_fonts.SetValue(
            bool(current_face) and current_face.lower() not in self._mono_faces
        )
        self._populate_faces()
        self._select_font(config.font)

    def _select_font(self, font: str) -> None:
        face = self._path_to_face.get(os.path.basename(font).lower())
        if face:
            self._font.SetStringSelection(face)

    def _populate_faces(self) -> None:
        """Fill the picker with all faces or just the monospaced ones."""
        show_all = self._all_fonts.GetValue()
        faces = (
            list(self._all_faces)
            if show_all
            else [face for face in self._all_faces if face.lower() in self._mono_faces]
        )
        keep = self._font.GetStringSelection()
        self._font.set_faces(faces)
        if keep in faces:
            self._font.SetStringSelection(keep)
        self._font_label.SetLabel("Font:" if show_all else "Font (monospaced):")

    def _update_bands(self) -> None:
        """Show the low-band pickers only while "Color by charge level" is on."""
        show = self._dynamic_color.GetValue()
        for widget in self._band_widgets:
            widget.Show(show)
        self.Layout()

    # --- events -------------------------------------------------------------

    def _on_font_selected(self, evt: wx.CommandEvent) -> None:
        self._emit_font_preview()
        evt.Skip()

    def _emit_font_preview(self) -> None:
        """Offer the current font pick to the live tray preview, if any."""
        if self._on_font_preview is None:
            return
        face = self._font.GetStringSelection()
        path = self._face_to_path.get(face) if face else None
        if path is not None:
            try:
                ImageFont.truetype(path, 16)
            except OSError:
                path = None  # uninstalled mid-dialog; fall back to the current font
        self._on_font_preview(path)

    def _on_all_fonts(self, evt: wx.CommandEvent) -> None:
        self._populate_faces()
        self._emit_font_preview()  # the selection may have cleared
        evt.Skip()

    def _on_size_changed(self, evt: wx.CommandEvent) -> None:
        self._size_label.SetLabel(f"{self._size.GetValue()}%")
        self._emit_size_preview()
        evt.Skip()

    def _emit_size_preview(self) -> None:
        """Offer the current size pick to the live tray preview, if any."""
        if self._on_size_preview is not None:
            self._on_size_preview(self._size.GetValue())

    def _on_outline(self, evt: wx.CommandEvent) -> None:
        self._emit_outline_preview()
        evt.Skip()

    def _emit_outline_preview(self) -> None:
        """Offer the current outline pick to the live tray preview, if any."""
        if self._on_outline_preview is not None:
            self._on_outline_preview(self._text_outline.GetValue())

    def _on_dynamic_color(self, evt: wx.CommandEvent) -> None:
        self._update_bands()
        evt.Skip()

    def _on_reset(self, _evt: wx.CommandEvent) -> None:
        defaults = Config()
        self._poll.SetValue(defaults.poll_rate)
        self._all_fonts.SetValue(False)
        self._populate_faces()
        self._select_font(defaults.font)
        self._emit_font_preview()
        self._size.SetValue(defaults.text_size)
        self._size_label.SetLabel(f"{defaults.text_size}%")
        self._emit_size_preview()
        self._text_outline.SetValue(defaults.text_outline)
        self._emit_outline_preview()
        self._color.SetColour(wx.Colour(*defaults.foreground_color))
        self._mid_color.SetColour(wx.Colour(*defaults.mid_color))
        self._low_color.SetColour(wx.Colour(*defaults.low_color))
        self._dynamic_color.SetValue(defaults.dynamic_color)
        self._update_bands()
        self._battery_icon.SetValue(defaults.battery_icon)
        self._debug.SetValue(defaults.debug)

    def _on_ok(self, evt: wx.CommandEvent) -> None:
        face = self._font.GetStringSelection()
        if face:
            try:
                ImageFont.truetype(self._face_to_path[face], 16)
            except OSError:
                wx.MessageBox(
                    f"Could not load font {face!r}.\nPlease choose another.",
                    "Invalid font",
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
                return  # keep the dialog open so the user can fix it
        evt.Skip()  # let the standard OK handler close the dialog

    # --- result -------------------------------------------------------------

    def apply_to(self, config: Config) -> None:
        config.poll_rate = self._poll.GetValue()
        face = self._font.GetStringSelection()
        if face:
            config.font = self._face_to_path[face]
        config.text_size = self._size.GetValue()
        config.text_outline = self._text_outline.GetValue()
        config.foreground_color = _rgb(self._color)
        config.mid_color = _rgb(self._mid_color)
        config.low_color = _rgb(self._low_color)
        config.dynamic_color = self._dynamic_color.GetValue()
        config.battery_icon = self._battery_icon.GetValue()
        config.debug = self._debug.GetValue()
