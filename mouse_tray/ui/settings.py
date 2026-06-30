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

from ..config import Config


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
        super().__init__(parent, title=f"{config.app_name} settings")

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

        grid = wx.FlexGridSizer(rows=4, cols=2, vgap=8, hgap=8)
        grid.AddGrowableCol(1, 1)

        grid.Add(wx.StaticText(self, label="Poll interval (s):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self._poll = wx.SpinCtrl(self, min=1, max=3600, initial=int(config.poll_rate))
        grid.Add(self._poll, 0, wx.EXPAND)

        grid.Add(wx.StaticText(self, label="Font (monospaced):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self._font = _FontPicker(self, faces)
        grid.Add(self._font, 1, wx.EXPAND)

        grid.Add(wx.StaticText(self, label="Font color:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self._color = wx.ColourPickerCtrl(self, colour=wx.Colour(*config.foreground_color))
        grid.Add(self._color, 0)

        grid.Add(wx.StaticText(self, label="Debug logging:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self._debug = wx.CheckBox(self)
        self._debug.SetValue(config.debug)
        grid.Add(self._debug, 0, wx.ALIGN_CENTER_VERTICAL)

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
        # Validate the chosen font before the OK button closes the dialog.
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    # --- helpers ------------------------------------------------------------

    def _select_font(self, font: str) -> None:
        face = self._path_to_face.get(os.path.basename(font).lower())
        if face:
            self._font.SetStringSelection(face)

    # --- events -------------------------------------------------------------

    def _on_reset(self, _evt: wx.CommandEvent) -> None:
        defaults = Config()
        self._poll.SetValue(defaults.poll_rate)
        self._select_font(defaults.font)
        self._color.SetColour(wx.Colour(*defaults.foreground_color))
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
        colour = self._color.GetColour()
        config.foreground_color = (colour.Red(), colour.Green(), colour.Blue())
        config.debug = self._debug.GetValue()
