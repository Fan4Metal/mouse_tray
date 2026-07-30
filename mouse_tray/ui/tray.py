"""The system-tray icon and its context menu."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import wx
from wx.adv import TaskBarIcon


@dataclass(frozen=True)
class MouseChoice:
    """One entry of the mouse selector.

    ``key`` is :attr:`~mouse_tray.drivers.driver.MouseDriver.key` -- opaque to
    the UI, handed straight back to ``on_select_mouse``.
    """

    key: str
    name: str
    selected: bool


class TrayIcon(TaskBarIcon):
    """Thin wrapper around ``TaskBarIcon`` that forwards events to callbacks.

    Keeping the UI widget free of app logic means the state machine in
    :mod:`mouse_tray.ui.app` owns all behavior -- including which mice exist and
    which one is pinned; this class only renders the list it is handed.
    """

    def __init__(  # noqa: PLR0913 -- one keyword-only callback per menu action
        self,
        *,
        on_left_click: Callable[[], None],
        mice_provider: Callable[[], list[MouseChoice]],
        on_select_mouse: Callable[[str | None], None],
        on_reset_timer: Callable[[], None],
        on_settings: Callable[[], None],
        on_exit: Callable[[], None],
    ):
        super().__init__()
        self._on_left_click = on_left_click
        self._mice_provider = mice_provider
        self._on_select_mouse = on_select_mouse
        self._on_reset_timer = on_reset_timer
        self._on_settings = on_settings
        self._on_exit = on_exit
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, lambda _evt: self._on_left_click())

    def CreatePopupMenu(self) -> wx.Menu:  # noqa: N802 (wx override)
        menu = wx.Menu()
        self._append_mice(menu)
        reset_item = menu.Append(wx.ID_ANY, "Reset timer")
        self.Bind(wx.EVT_MENU, lambda _evt: self._on_reset_timer(), reset_item)
        settings_item = menu.Append(wx.ID_PREFERENCES, "Settings...")
        self.Bind(wx.EVT_MENU, lambda _evt: self._on_settings(), settings_item)
        menu.AppendSeparator()
        exit_item = menu.Append(wx.ID_EXIT, "Exit")
        self.Bind(wx.EVT_MENU, lambda _evt: self._on_exit(), exit_item)
        return menu

    def _append_mice(self, menu: wx.Menu) -> None:
        """Radio list of detected mice, plus "Auto", when there is a choice.

        Hidden in the single-mouse case -- one mouse and no pin is not a choice,
        and the menu stays exactly as it was before multi-mouse support.
        """
        choices = self._mice_provider()
        pinned = any(choice.selected for choice in choices)
        if len(choices) < 2 and not pinned:
            return

        auto_item = menu.AppendRadioItem(wx.ID_ANY, "Auto")
        auto_item.Check(not pinned)
        self.Bind(wx.EVT_MENU, lambda _evt: self._on_select_mouse(None), auto_item)
        for choice in choices:
            item = menu.AppendRadioItem(wx.ID_ANY, choice.name)
            item.Check(choice.selected)
            self.Bind(wx.EVT_MENU, lambda _evt, key=choice.key: self._on_select_mouse(key), item)
        menu.AppendSeparator()

    def update(self, icon: wx.Icon, tooltip: str) -> None:
        """Set the tray icon and hover tooltip (safe to call from any thread)."""
        wx.CallAfter(self.SetIcon, icon, tooltip)
