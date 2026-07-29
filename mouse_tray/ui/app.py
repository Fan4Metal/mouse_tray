"""Application entry point: the wx app, the polling loop and the one state
machine that turns any :class:`BatteryStatus` into a tray icon.

All vendor differences are already gone by the time we get here -- this module
never imports a driver, only the registry's :func:`detect_driver`.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from contextlib import suppress
from datetime import datetime, timedelta

import wx
from wx.adv import NotificationMessage

from ..battery import BatteryStatus
from ..build_info import commit_hash
from ..config import GREEN, VERSION, Config
from ..config import config as default_config
from ..drivers import detect_driver
from ..logging_setup import setup_logging
from .icons import IconRenderer
from .tray import TrayIcon

log = logging.getLogger(__name__)

#: Charge levels cycled through while the mouse is charging.
_ANIMATION_FRAMES = (0, 50, 100)
_ANIMATION_INTERVAL_MS = 500
_NO_MOUSE = "No Mouse Detected"


def format_timedelta(delta: timedelta) -> str:
    """Format a duration like ``"1 days, 23:59:59"``."""
    days = delta.days
    seconds = int(delta.total_seconds()) - days * 86400
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{days} days, {hours:02d}:{minutes:02d}:{secs:02d}"


class TrayApp(wx.Frame):
    """Hidden frame that owns the tray icon, notification and worker thread.

    A frame is needed because ``NotificationMessage`` and the wx main loop
    require a top-level window; it never becomes visible.
    """

    def __init__(self, config: Config):
        super().__init__(None, title=config.display_name)
        self.config = config
        self.icons = IconRenderer(config)

        # The full-charge timer is per mouse, keyed by its display name. We
        # only know which mouse is connected after detection, so the date is
        # (re)loaded in _sync_mouse whenever the active mouse changes.
        self.full_charge_date: datetime | None = None
        self._current_mouse: str | None = None
        self.driver = None
        self._was_full = False

        self.tray = TrayIcon(
            on_left_click=self._wake,
            on_reset_timer=self._reset_timer,
            on_settings=self._open_settings,
            on_exit=self._exit,
        )
        self.tray.update(self.icons.text_icon(" "), config.display_name)

        self.notification = NotificationMessage(title=config.display_name, message="Charged 100%")
        self.notification.SetFlags(wx.ICON_INFORMATION)
        self.notification.UseTaskBarIcon(self.tray)

        # Charge animation runs on the main thread via a timer.
        self._anim_timer = wx.Timer(self)
        self._anim_index = 0
        self._anim_tooltip = config.display_name
        self.Bind(wx.EVT_TIMER, self._on_anim_tick, self._anim_timer)

        # Polling runs on a background thread; it only ever calls back into the
        # UI through wx.CallAfter, so all widget work stays on the main thread.
        self._stop = threading.Event()
        self._wakeup = threading.Event()
        self._worker = threading.Thread(target=self._poll_loop, daemon=True)
        self._worker.start()

    # --- polling thread -----------------------------------------------------

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            if self.driver is None:
                self.driver = detect_driver()

            if self.driver is None:
                status, name = BatteryStatus.absent(), None
            else:
                status = self.driver.read_status()
                name = self.driver.name
                if not status.present:
                    self.driver = None  # hot-unplug / model switch -> re-detect

            wx.CallAfter(self._apply_status, status, name)

            awake = status.present and not status.charging and not status.asleep
            interval = self.config.poll_rate if awake else self.config.fast_poll_rate
            self._wakeup.wait(interval)
            self._wakeup.clear()

    def _wake(self) -> None:
        """Trigger an immediate re-poll (e.g. tray clicked to wake a mouse)."""
        self._wakeup.set()

    # --- state machine (main thread) ---------------------------------------

    def _apply_status(self, status: BatteryStatus, name: str | None) -> None:  # noqa: PLR0911
        """Render one status snapshot. The single point that drives the tray.

        The guard-clause chain is the design (see CLAUDE.md): one flat, ordered
        list of states, each rendering and returning. Collapsing it to fit a
        return-count limit would bury the ordering that makes it readable.
        """
        self._sync_mouse(name)

        if not status.present:
            self._stop_animation()
            self._was_full = False
            self.tray.update(self.icons.text_icon("-"), _NO_MOUSE)
            return

        tooltip = self._tooltip(name, status)

        if status.charging:
            self._was_full = False
            self._start_animation(tooltip)
            return

        self._stop_animation()

        if status.full:
            self.tray.update(self.icons.battery_icon(100, GREEN), tooltip)
            if not self._was_full:
                self._was_full = True
                self._record_full_charge()
                self.notification.Show(timeout=NotificationMessage.Timeout_Auto)
            return

        self._was_full = False

        if status.asleep:
            self.tray.update(self.icons.text_icon("Zzz"), tooltip)
            return

        if status.percent is None:
            # Present and awake but the driver could not read a level. Neither
            # a number nor a fill height is meaningful, so say so.
            self.tray.update(self.icons.text_icon("?"), tooltip)
            return

        if status.percent == 100:
            # 100% but no "full" flag from the driver. The foreground color is
            # what dynamic_color would pick for this band anyway, and green
            # stays reserved for the full state above.
            self.tray.update(self.icons.battery_icon(100), tooltip)
            return

        color = self.config.charge_color(status.percent) if self.config.dynamic_color else None
        if self.config.battery_icon:
            # The exact number is in the tooltip built above.
            self.tray.update(self.icons.battery_icon(status.percent, color), tooltip)
            return
        self.tray.update(self.icons.text_icon(str(status.percent), color), tooltip)

    def _sync_mouse(self, name: str | None) -> None:
        """Load the active mouse's own full-charge date when the mouse changes."""
        if name is None or name == self._current_mouse:
            return
        from ..storage import load_full_charge_date

        self._current_mouse = name
        self.full_charge_date = load_full_charge_date(self.config.app_name, name)
        self._was_full = False  # don't carry full-state across a mouse switch

    def _tooltip(self, name: str | None, status: BatteryStatus) -> str:
        """Mouse name, the charge percent when known, and time since full.

        The percent line is what makes ``battery_icon`` mode usable -- the tray
        then shows a fill level and this is the only place the exact number
        appears -- but it is cheap and consistent enough to always include.
        """
        lines = [name or _NO_MOUSE]
        if status.percent is not None:
            lines.append(f"{status.percent}%")
        if self.full_charge_date:
            lines.append(format_timedelta(datetime.now() - self.full_charge_date))
        return "\n".join(lines)

    # --- animation ----------------------------------------------------------

    def _start_animation(self, tooltip: str) -> None:
        self._anim_tooltip = tooltip
        if not self._anim_timer.IsRunning():
            self._anim_index = 0
            self._on_anim_tick()
            self._anim_timer.Start(_ANIMATION_INTERVAL_MS)

    def _stop_animation(self) -> None:
        if self._anim_timer.IsRunning():
            self._anim_timer.Stop()

    def _on_anim_tick(self, _evt: wx.TimerEvent | None = None) -> None:
        level = _ANIMATION_FRAMES[self._anim_index % len(_ANIMATION_FRAMES)]
        self._anim_index += 1
        self.tray.update(self.icons.battery_icon(level), self._anim_tooltip)

    # --- full-charge timer --------------------------------------------------

    def _record_full_charge(self, when: datetime | None = None) -> None:
        if self._current_mouse is None:
            return  # no active mouse to attribute the timer to
        from ..storage import save_full_charge_date

        self.full_charge_date = when or datetime.now()
        save_full_charge_date(self.config.app_name, self._current_mouse, self.full_charge_date)
        log.info("Full charge timer for %s set to %s", self._current_mouse, self.full_charge_date)

    def _reset_timer(self) -> None:
        self._record_full_charge()

    # --- settings -----------------------------------------------------------

    def _open_settings(self) -> None:
        from ..storage import save_settings
        from .settings import open_settings

        if not open_settings(self, self.config):
            return

        # self.config is mutated in place, so IconRenderer (which holds the same
        # reference) picks up the new font/color and the worker thread reads the
        # new poll rate on its next iteration. Persist and refresh now.
        save_settings(self.config.app_name, self.config)
        setup_logging(self.config.app_name, self.config.debug)
        self._wake()  # force an immediate re-poll so the icon repaints

    # --- lifecycle ----------------------------------------------------------

    def _exit(self) -> None:
        self._stop.set()
        self._wakeup.set()
        self._stop_animation()
        self.tray.RemoveIcon()
        self.tray.Destroy()
        self.Destroy()


class _App(wx.App):
    def __init__(self, config: Config):
        self._config = config
        super().__init__(False)

    def OnInit(self) -> bool:  # noqa: N802 (wx override)
        frame = TrayApp(self._config)
        self.SetTopWindow(frame)
        return True


def run(config: Config | None = None) -> None:
    """Launch the tray application."""
    from ..storage import load_settings

    cfg = config or default_config
    load_settings(cfg.app_name, cfg)  # apply any persisted user settings
    setup_logging(cfg.app_name, cfg.debug)
    commit = commit_hash()
    version = f"{VERSION} ({commit})" if commit else VERSION
    log.info("Starting %s %s", cfg.display_name, version)
    with suppress(AttributeError, OSError):  # non-Windows or older Windows
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    app = _App(cfg)
    app.MainLoop()
