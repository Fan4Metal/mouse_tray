"""Per-mouse persistence of the "last full charge" timestamp (Windows registry).

Each mouse keeps its own timestamp, keyed by its display name, stored as one
value under ``SOFTWARE\\<app_name>\\FullCharge``. Switching mice therefore keeps
each timer independent.
"""

from __future__ import annotations

import logging
import winreg
from datetime import datetime

_DATE_FORMAT = "%d.%m.%Y %H:%M:%S"

log = logging.getLogger(__name__)


def _reg_path(app_name: str) -> str:
    return rf"SOFTWARE\{app_name}\FullCharge"


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
