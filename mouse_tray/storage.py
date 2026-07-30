"""Per-mouse persistence of the "last full charge" timestamp (Windows registry).

Each mouse keeps its own timestamp, keyed by its display name, stored as one
value under ``SOFTWARE\\<app_name>\\FullCharge``. Switching mice therefore keeps
each timer independent.
"""

from __future__ import annotations

import logging
import winreg
from datetime import datetime

from .config import Config

_DATE_FORMAT = "%d.%m.%Y %H:%M:%S"

log = logging.getLogger(__name__)


def _reg_path(app_name: str) -> str:
    return rf"SOFTWARE\{app_name}\FullCharge"


def _settings_path(app_name: str) -> str:
    return rf"SOFTWARE\{app_name}\Settings"


def _value_name(mouse: str) -> str:
    """Registry-safe value name for a mouse (backslashes break key paths)."""
    return mouse.replace("\\", "_").strip() or "Unknown"


def save_full_charge_date(app_name: str, mouse: str, when: datetime) -> None:
    """Persist the moment ``mouse`` was last fully charged."""
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _reg_path(app_name)) as key:
            winreg.SetValueEx(key, _value_name(mouse), 0, winreg.REG_SZ, when.strftime(_DATE_FORMAT))
    except OSError as exc:
        log.warning("Could not save full charge date for %s: %s", mouse, exc)


def load_full_charge_date(app_name: str, mouse: str) -> datetime | None:
    """Read ``mouse``'s stored full-charge timestamp, or ``None`` if absent/invalid."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _reg_path(app_name), 0, winreg.KEY_READ) as key:
            value = winreg.QueryValueEx(key, _value_name(mouse))[0]
        return datetime.strptime(value, _DATE_FORMAT)
    except (OSError, ValueError):
        return None


# --- user settings (poll rate, font, color, debug) -------------------------


def _color_to_str(color: tuple[int, int, int]) -> str:
    return ",".join(str(c) for c in color)


def _str_to_color(value: str) -> tuple[int, int, int] | None:
    try:
        parts = tuple(int(p) for p in value.split(","))
    except ValueError:
        return None
    if len(parts) != 3 or not all(0 <= p <= 255 for p in parts):
        return None
    return parts


def _read_int(key: winreg.HKEYType, name: str) -> int | None:
    try:
        return int(winreg.QueryValueEx(key, name)[0])
    except (OSError, ValueError, TypeError):
        return None


def _read_str(key: winreg.HKEYType, name: str) -> str | None:
    try:
        return str(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return None


def save_settings(app_name: str, config: Config) -> None:
    """Persist the user-tunable settings (poll rate, font, color, debug)."""
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _settings_path(app_name)) as key:
            winreg.SetValueEx(key, "PollRate", 0, winreg.REG_DWORD, int(config.poll_rate))
            winreg.SetValueEx(key, "Font", 0, winreg.REG_SZ, config.font)
            color = _color_to_str(config.foreground_color)
            winreg.SetValueEx(key, "ForegroundColor", 0, winreg.REG_SZ, color)
            winreg.SetValueEx(key, "DynamicColor", 0, winreg.REG_DWORD, 1 if config.dynamic_color else 0)
            winreg.SetValueEx(key, "MidColor", 0, winreg.REG_SZ, _color_to_str(config.mid_color))
            winreg.SetValueEx(key, "LowColor", 0, winreg.REG_SZ, _color_to_str(config.low_color))
            winreg.SetValueEx(key, "BatteryIcon", 0, winreg.REG_DWORD, 1 if config.battery_icon else 0)
            winreg.SetValueEx(key, "Debug", 0, winreg.REG_DWORD, 1 if config.debug else 0)
    except OSError as exc:
        log.warning("Could not save settings: %s", exc)


def load_settings(app_name: str, config: Config) -> None:
    """Apply persisted settings onto ``config`` in place.

    Missing or invalid values are skipped so each field keeps its code default.
    """
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _settings_path(app_name), 0, winreg.KEY_READ)
    except OSError:
        return
    with key:
        poll_rate = _read_int(key, "PollRate")
        if poll_rate is not None and poll_rate > 0:
            config.poll_rate = poll_rate

        font = _read_str(key, "Font")
        if font:
            config.font = font

        color = _read_str(key, "ForegroundColor")
        if color is not None and (parsed := _str_to_color(color)) is not None:
            config.foreground_color = parsed

        dynamic_color = _read_int(key, "DynamicColor")
        if dynamic_color is not None:
            config.dynamic_color = bool(dynamic_color)

        mid_color = _read_str(key, "MidColor")
        if mid_color is not None and (parsed := _str_to_color(mid_color)) is not None:
            config.mid_color = parsed

        low_color = _read_str(key, "LowColor")
        if low_color is not None and (parsed := _str_to_color(low_color)) is not None:
            config.low_color = parsed

        battery_icon = _read_int(key, "BatteryIcon")
        if battery_icon is not None:
            config.battery_icon = bool(battery_icon)

        debug = _read_int(key, "Debug")
        if debug is not None:
            config.debug = bool(debug)


# --- pinned mouse -----------------------------------------------------------
#
# Kept out of Config on purpose: the pin is chosen from the tray menu, not from
# the settings dialog, so it must not ride along with save_settings.

_SELECTED_KEY = "SelectedMouse"
_SELECTED_NAME = "SelectedMouseName"


def save_selected_mouse(app_name: str, key: str | None, name: str | None) -> None:
    """Persist which mouse the user pinned (``None`` restores auto-select).

    The display name is stored next to the key so a pinned-but-offline mouse can
    still be named in the tooltip and in the tray menu -- the key alone
    (``DriverClass/VID/PID``) is not something to show a user.
    """
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _settings_path(app_name)) as reg_key:
            winreg.SetValueEx(reg_key, _SELECTED_KEY, 0, winreg.REG_SZ, key or "")
            winreg.SetValueEx(reg_key, _SELECTED_NAME, 0, winreg.REG_SZ, name or "")
    except OSError as exc:
        log.warning("Could not save the selected mouse: %s", exc)


def load_selected_mouse(app_name: str) -> tuple[str | None, str | None]:
    """Read the pinned mouse as ``(key, name)``; ``(None, None)`` means auto."""
    path = _settings_path(app_name)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ) as reg_key:
            key = _read_str(reg_key, _SELECTED_KEY)
            name = _read_str(reg_key, _SELECTED_NAME)
    except OSError:
        return None, None
    return (key or None), (name or None)
