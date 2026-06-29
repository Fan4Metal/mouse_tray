"""Persistence of the "last full charge" timestamp via the Windows registry."""

from __future__ import annotations

import logging
import winreg
from datetime import datetime

_DATE_FORMAT = "%d.%m.%Y %H:%M:%S"
_VALUE_NAME = "FullChargeDate"

log = logging.getLogger(__name__)


def _reg_path(app_name: str) -> str:
    return rf"SOFTWARE\{app_name}"


def save_full_charge_date(app_name: str, when: datetime) -> None:
    """Persist the moment the mouse was last fully charged."""
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _reg_path(app_name)) as key:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, when.strftime(_DATE_FORMAT))
    except OSError as exc:
        log.warning("Could not save full charge date: %s", exc)


def load_full_charge_date(app_name: str) -> datetime | None:
    """Read the stored full-charge timestamp, or ``None`` if absent/invalid."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _reg_path(app_name), 0, winreg.KEY_READ) as key:
            value = winreg.QueryValueEx(key, _VALUE_NAME)[0]
        return datetime.strptime(value, _DATE_FORMAT)
    except (OSError, ValueError):
        return None
