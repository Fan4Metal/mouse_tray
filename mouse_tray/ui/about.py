"""About dialog: what the app is, where it lives, and every mouse it supports.

The model table is built from the driver registry rather than a hand-kept list,
so a new driver (or a new ``MouseModel`` row) shows up here with no edit -- the
same registry that drives detection. This module therefore imports
``all_drivers`` only; like the rest of the UI it never imports a driver module
and knows nothing about any particular vendor. The one piece of vendor prose it
can show, :attr:`MouseDriver.note`, is declared by the driver itself.
"""

from __future__ import annotations

import wx
import wx.adv

from ..build_info import version_string
from ..config import DESCRIPTION, HOMEPAGE, Config
from ..drivers import MouseModel, all_drivers
from ..resources import icon_path

_COLUMNS = ("Mouse", "USB ID", "Protocol")
#: Slack added to every autosized column. wx measures the text alone, which
#: leaves the last glyph touching the next column -- and clipped outright once
#: the vertical scrollbar eats into the last one.
_COLUMN_PADDING = 16
_LIST_SIZE = (-1, 240)
_ICON_SIZE = 48


def open_about(parent: wx.Window, config: Config) -> None:
    """Show the modal about dialog."""
    dialog = _AboutDialog(parent, config)
    try:
        dialog.ShowModal()
    finally:
        dialog.Destroy()


def usb_id(model: MouseModel) -> str:
    """``"373B:1031"``, plus the wired PID when the cable enumerates its own.

    The form matches what Windows shows as ``VID_373B&PID_1031``, so a row can
    be checked against Device Manager without conversion.
    """
    ids = f"{model.vid:04X}:{model.pid_wireless:04X}"
    if model.pid_wired != model.pid_wireless:
        ids += f" / {model.pid_wired:04X}"
    return ids


def supported_mice() -> list[tuple[str, str, str]]:
    """``(model name, USB id, vendor)`` for every registered model.

    In registration order -- the same order detection probes. One row per
    ``MouseModel``, since rows that repeat a name (a second dongle revision, a
    receiver family listed once per PID) differ in exactly the ids shown here;
    identical rows are still collapsed.
    """
    rows: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for driver_cls in all_drivers():
        for model in driver_cls.models:
            row = (model.name, usb_id(model), driver_cls.vendor)
            if row in seen:
                continue
            seen.add(row)
            rows.append(row)
    return rows


def driver_notes() -> list[str]:
    """The caveats drivers declare about their own model lists."""
    return [driver_cls.note for driver_cls in all_drivers() if driver_cls.note]


class _AboutDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, config: Config):
        super().__init__(parent, title=f"About {config.display_name}")
        self.SetIcon(wx.Icon(icon_path("app.ico")))

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self._header(config), 0, wx.EXPAND | wx.ALL, 12)
        outer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        # "devices", not "mice": a row is one USB id, and some of them are
        # receivers -- seven Lightspeed dongles carry the same mouse name.
        mice = supported_mice()
        label = wx.StaticText(self, label=f"Supported devices ({len(mice)}):")
        outer.Add(label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        outer.Add(_MouseList(self, mice, self.FromDIP(_LIST_SIZE)), 1, wx.EXPAND | wx.ALL, 12)

        for note in driver_notes():
            text = wx.StaticText(self, label=note)
            text.Wrap(self.FromDIP(420))
            text.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
            outer.Add(text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        buttons = self.CreateStdDialogButtonSizer(wx.OK)
        outer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.SetSizerAndFit(outer)
        self.SetMinSize(self.GetSize())
        self.CentreOnScreen()

    # --- pieces -------------------------------------------------------------

    def _header(self, config: Config) -> wx.Sizer:
        """App icon on the left; name, version, description and links right."""
        header = wx.BoxSizer(wx.HORIZONTAL)

        # app.ico holds a single 256px image, so it is scaled here rather than
        # requested at 48px -- wx would otherwise hand back an empty icon.
        size = self.FromDIP(_ICON_SIZE)
        image = wx.Image(icon_path("app.ico"), wx.BITMAP_TYPE_ICO)
        image.Rescale(size, size, wx.IMAGE_QUALITY_HIGH)
        header.Add(wx.StaticBitmap(self, bitmap=wx.Bitmap(image)), 0, wx.ALIGN_TOP | wx.RIGHT, 12)

        title = wx.StaticText(self, label=f"{config.display_name} {version_string()}")
        font = title.GetFont()
        font.SetPointSize(font.GetPointSize() + 2)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(font)

        description = wx.StaticText(self, label=DESCRIPTION)
        description.Wrap(self.FromDIP(360))

        column = wx.BoxSizer(wx.VERTICAL)
        column.Add(title, 0)
        column.Add(description, 0, wx.TOP, 6)
        column.Add(wx.adv.HyperlinkCtrl(self, label="GitHub", url=HOMEPAGE), 0, wx.TOP, 8)
        header.Add(column, 1, wx.EXPAND)
        return header


class _MouseList(wx.ListCtrl):
    """Read-only table of supported mice, sortable by either column header.

    Rows start in registry order -- the order detection probes drivers, which
    groups each driver's models together. A header click sorts by that column,
    a second click on the same one reverses it. Sorting refills the control
    instead of going through ``SortItems``: three dozen rows are cheap to
    rewrite, and the row tuples stay the single source of what is shown.
    """

    def __init__(self, parent: wx.Window, rows: list[tuple[str, ...]], size: wx.Size):
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_SINGLE_SEL, size=size)
        self._rows = rows
        self._sorted_by: int | None = None
        self._ascending = True

        for title in _COLUMNS:
            self.AppendColumn(title)
        self._fill(rows)
        self._fit_columns()
        self.Bind(wx.EVT_LIST_COL_CLICK, self._on_column_click)

    def _fill(self, rows: list[tuple[str, ...]]) -> None:
        self.DeleteAllItems()
        for row in rows:
            self.Append(row)

    def _fit_columns(self) -> None:
        """Width from the content, with the header as a floor.

        A column of short values must still show its title -- and the title now
        carries a sort arrow, so it needs the room even before one is shown.
        The columns then set the control's minimum width, so the dialog grows to
        fit the table instead of the table getting a horizontal scrollbar.
        """
        padding = self.FromDIP(_COLUMN_PADDING)
        for column in range(self.GetColumnCount()):
            self.SetColumnWidth(column, wx.LIST_AUTOSIZE)
            content = self.GetColumnWidth(column)
            self.SetColumnWidth(column, wx.LIST_AUTOSIZE_USEHEADER)
            self.SetColumnWidth(column, max(content, self.GetColumnWidth(column)) + padding)

        total = sum(self.GetColumnWidth(column) for column in range(self.GetColumnCount()))
        # The rows outrun the box, so the vertical scrollbar is always there and
        # its width has to come on top of the columns, not out of them.
        scrollbar = wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X, self)
        self.SetMinSize(wx.Size(total + scrollbar + self.FromDIP(4), self.GetMinHeight()))

    def _on_column_click(self, evt: wx.ListEvent) -> None:
        column = evt.GetColumn()
        self._ascending = not self._ascending if column == self._sorted_by else True
        self._sorted_by = column
        # The remaining columns break ties, so rows sharing a cell -- a whole
        # driver's models share one protocol -- keep a predictable order.
        order = [column] + [c for c in range(self.GetColumnCount()) if c != column]
        self._fill(
            sorted(
                self._rows,
                key=lambda row: tuple(row[c].lower() for c in order),
                reverse=not self._ascending,
            )
        )
        self.ShowSortIndicator(column, self._ascending)
