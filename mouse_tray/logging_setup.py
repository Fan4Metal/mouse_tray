"""Centralized logging configuration.

Built for a windowed (``--noconsole``) tray app:

* Always logs to a **rotating file** under ``%LOCALAPPDATA%\\<app_name>\\`` so
  there is something to diagnose with on a user's machine.
* Adds a console handler **only when a console exists** -- under PyInstaller's
  windowed build ``sys.stderr`` is ``None``, and a plain ``StreamHandler`` would
  raise on every log call.
* DEBUG (verbose HID byte dumps) is opt-in via the ``debug`` flag or the
  ``MOUSE_TRAY_DEBUG`` environment variable.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 3
_DEBUG_ENV = "MOUSE_TRAY_DEBUG"


def log_dir(app_name: str) -> str:
    """Per-user data directory for logs (``%LOCALAPPDATA%\\<app_name>``)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, app_name)


def _debug_enabled(debug: bool) -> bool:
    if debug:
        return True
    return os.environ.get(_DEBUG_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def setup_logging(app_name: str, debug: bool = False) -> str | None:
    """Configure root logging. Returns the log file path, or ``None`` if the
    file handler could not be created.

    Idempotent: existing handlers are cleared so calling it twice does not
    duplicate output.
    """
    level = logging.DEBUG if _debug_enabled(debug) else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(_FORMAT)

    # Console handler only if a usable stream exists (None under --noconsole).
    stream = sys.stderr or sys.stdout
    if stream is not None:
        console = logging.StreamHandler(stream)
        console.setFormatter(formatter)
        root.addHandler(console)

    # Rotating file handler -- best effort; never let logging setup crash the app.
    log_path: str | None = None
    try:
        directory = log_dir(app_name)
        os.makedirs(directory, exist_ok=True)
        log_path = os.path.join(directory, "app.log")
        file_handler = RotatingFileHandler(
            log_path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT,
            encoding="utf-8", delay=True,
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        log_path = None

    if log_path:
        logging.getLogger(__name__).info("Logging to %s (level=%s)", log_path, logging.getLevelName(level))
    return log_path
