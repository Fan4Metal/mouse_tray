"""Start with Windows: one value under the current user's ``Run`` registry key.

Windows' own keys are the single source of truth -- nothing about autostart is
kept in :class:`~mouse_tray.config.Config` -- so the settings checkbox always
shows what Windows will really do at sign-in. That includes the switch on Task
Manager's Startup tab: it leaves the ``Run`` value in place and records the
"disabled" flag under ``Explorer\\StartupApproved\\Run`` instead, so both keys are
read. Turning autostart on from the app clears that flag again.

The value is named after ``app_name`` (the stable identity key) and holds the
command line of *this* copy of the program. If that copy is moved or deleted,
:func:`repair` points the value at the running copy on the next start.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import winreg

log = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"

#: The project root (the folder with ``main.py``) when running from source.
_SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def command() -> str:
    """The command line Windows runs at sign-in.

    The exe itself in a frozen build; from source, ``pythonw`` (no console
    window) running ``main.py``. Every path is quoted -- they may contain spaces.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    interpreter = pythonw if os.path.isfile(pythonw) else sys.executable
    return f'"{interpreter}" "{os.path.join(_SOURCE_ROOT, "main.py")}"'


def _run_value(app_name: str) -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            return str(winreg.QueryValueEx(key, app_name)[0])
    except OSError:
        return None


def _disabled_in_task_manager(app_name: str) -> bool:
    """Whether Task Manager's Startup tab has this entry switched off.

    The value is 12 bytes: a flag byte (even = enabled, odd = disabled) and the
    FILETIME of the switch. A missing value means enabled.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _APPROVED_KEY) as key:
            data = winreg.QueryValueEx(key, app_name)[0]
    except OSError:
        return False
    return isinstance(data, bytes) and bool(data) and bool(data[0] & 1)


def _delete_value(path: str, name: str) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        pass  # key or value already gone


def is_enabled(app_name: str) -> bool:
    """Whether Windows will start the program at sign-in."""
    return _run_value(app_name) is not None and not _disabled_in_task_manager(app_name)


def set_enabled(app_name: str, enabled: bool) -> None:
    """Turn autostart on (pointing at this copy) or off. Raises ``OSError`` on failure."""
    if enabled:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command())
    else:
        _delete_value(_RUN_KEY, app_name)
    # On: an explicit tick overrides an earlier Task Manager switch-off. Off: no
    # point leaving a flag behind for a value that no longer exists.
    _delete_value(_APPROVED_KEY, app_name)


def repair(app_name: str) -> None:
    """Re-point an autostart entry whose program no longer exists at this copy.

    Only a *stale* entry is rewritten: one that works keeps pointing where it
    does, so running a second copy (or the source tree) never steals it. Called
    once at start-up; logs instead of raising.
    """
    current = _run_value(app_name)
    if current is None:
        return
    paths = re.findall(r'"([^"]+)"', current)
    if not paths or all(os.path.isfile(p) for p in paths):
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command())
    except OSError as exc:
        log.warning("Could not repair the autostart entry: %s", exc)
        return
    log.info("Autostart entry pointed at a missing program (%s); now %s", current, command())
