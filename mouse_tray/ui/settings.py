"""Settings dialog: edit the user-tunable config (poll rate, font, color, debug).

The dialog only knows how to read/write a :class:`Config`; persisting the result
and refreshing the running tray is the caller's job (see ``app._open_settings``).

The font picker lists only monospaced faces (the indicator needs fixed-width
digits) and previews each one in its own face. Face names are resolved back to a
``.ttf``/``.otf`` file so PIL can load them.
"""

from __future__ import annotations

import os
import winreg

import wx
import wx.adv
from PIL import ImageFont

from ..build_info import version_string
from ..config import LOW_THRESHOLD, MID_THRESHOLD, Config
from ..resources import icon_path


def open_settings(parent: wx.Window, config: Config) -> bool:
    """Show the modal settings dialog, centered on screen.

    On OK the edited values are written back onto ``config`` in place and
    ``True`` is returned; on Cancel nothing changes and ``False`` is returned.
    """
    dialog = _SettingsDialog(parent, config)
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


def _rgb(picker: wx.ColourPickerCtrl) -> tuple[int, int, int]:
    colour = picker.GetColour()
    return (colour.Red(), colour.Green(), colour.Blue())


class _FontPicker(wx.adv.OwnerDrawnComboBox):
    """Read-only combo that previews each (monospaced) face in its own font."""

    def __init__(self, parent: wx.Window, faces: list[str]):
        super().__init__(parent, choices=faces, style=wx.CB_READONLY)
        self._faces = faces

    def OnDrawItem(  # noqa: N802 (wx override)
        self, dc: wx.DC, rect: wx.Rect, item: int, flags: int
    ) -> None:
        if item == wx.NOT_FOUND:
            return
        face = self._faces[item]
        dc.SetFont(
            wx.Font(11, wx.FONTFAMILY_MODERN, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName=face)
        )
        if flags & wx.adv.ODCB_PAINTING_SELECTED:
            colour = wx.SYS_COLOUR_HIGHLIGHTTEXT
        else:
            colour = wx.SYS_COLOUR_WINDOWTEXT
        dc.SetTextForeground(wx.SystemSettings.GetColour(colour))
        dc.DrawText(face, rect.x + 4, rect.y + (rect.height - dc.GetCharHeight()) // 2)

    def OnMeasureItem(self, item: int) -> int:  # noqa: N802 (wx override)
        return 24


class _SettingsDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, config: Config):
        super().__init__(parent, title=f"{config.display_name} {version_string()} settings")
        self.SetIcon(wx.Icon(icon_path("app.ico")))

        file_map = _font_files()
        faces = sorted(
            face
            for face in wx.FontEnumerator.GetFacenames(fixedWidthOnly=True)
            if not face.startswith("@") and face.lower() in file_map
        )
        self._face_to_path = {face: file_map[face.lower()] for face in faces}
        self._path_to_face = {
            os.path.basename(path).lower(): face for face, path in self._face_to_path.items()
        }

        grid = wx.FlexGridSizer(rows=6, cols=2, vgap=8, hgap=8)
        grid.AddGrowableCol(1, 1)

        grid.Add(wx.StaticText(self, label="Poll interval (s):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self._poll = wx.SpinCtrl(self, min=1, max=3600, initial=int(config.poll_rate))
        grid.Add(self._poll, 0, wx.EXPAND)

        grid.Add(wx.StaticText(self, label="Font (monospaced):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self._font = _FontPicker(self, faces)
        grid.Add(self._font, 1, wx.EXPAND)

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
        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)

        bottom = wx.BoxSizer(wx.HORIZONTAL)
        bottom.Add(reset, 0)
        bottom.AddStretchSpacer()
        bottom.Add(buttons, 0)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(grid, 0, wx.EXPAND | wx.ALL, 12)
        outer.Add(bottom, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.SetSizerAndFit(outer)
        self.SetMinSize(self.GetSize())
        self.CentreOnScreen()

        self._select_font(config.font)
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

    def _select_font(self, font: str) -> None:
        face = self._path_to_face.get(os.path.basename(font).lower())
        if face:
            self._font.SetStringSelection(face)

    def _update_bands(self) -> None:
        """Show the low-band pickers only while "Color by charge level" is on."""
        show = self._dynamic_color.GetValue()
        for widget in self._band_widgets:
            widget.Show(show)
        self.Layout()

    # --- events -------------------------------------------------------------

    def _on_dynamic_color(self, evt: wx.CommandEvent) -> None:
        self._update_bands()
        evt.Skip()

    def _on_reset(self, _evt: wx.CommandEvent) -> None:
        defaults = Config()
        self._poll.SetValue(defaults.poll_rate)
        self._select_font(defaults.font)
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
        config.foreground_color = _rgb(self._color)
        config.mid_color = _rgb(self._mid_color)
        config.low_color = _rgb(self._low_color)
        config.dynamic_color = self._dynamic_color.GetValue()
        config.battery_icon = self._battery_icon.GetValue()
        config.debug = self._debug.GetValue()
