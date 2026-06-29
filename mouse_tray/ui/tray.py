"""The system-tray icon and its context menu."""

from __future__ import annotations

from collections.abc import Callable

import wx
from wx.adv import TaskBarIcon


class TrayIcon(TaskBarIcon):
    """Thin wrapper around ``TaskBarIcon`` that forwards events to callbacks.

    Keeping the UI widget free of app logic means the state machine in
    :mod:`mouse_tray.ui.app` owns all behavior.
    """

    def __init__(
        self,
        *,
        on_left_click: Callable[[], None],
        on_reset_timer: Callable[[], None],
        on_exit: Callable[[], None],
    ):
        super().__init__()
        self._on_left_click = on_left_click
        self._on_reset_timer = on_reset_timer
        self._on_exit = on_exit
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, lambda _evt: self._on_left_click())

    def CreatePopupMenu(self) -> wx.Menu:  # noqa: N802 (wx override)
        menu = wx.Menu()
        reset_item = menu.Append(wx.ID_ANY, "Reset timer")
        self.Bind(wx.EVT_MENU, lambda _evt: self._on_reset_timer(), reset_item)
        exit_item = menu.Append(wx.ID_EXIT, "Exit")
        self.Bind(wx.EVT_MENU, lambda _evt: self._on_exit(), exit_item)
        return menu

    def update(self, icon: wx.Icon, tooltip: str) -> None:
        """Set the tray icon and hover tooltip (safe to call from any thread)."""
        wx.CallAfter(self.SetIcon, icon, tooltip)
