"""Resource path resolution that works both from source and PyInstaller bundles."""

from __future__ import annotations

import os
import sys

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_resource(relative_path: str) -> str:
    """Return an absolute path to a bundled resource.

    Under PyInstaller, data files live in ``sys._MEIPASS``; from source they
    live next to this package.
    """
    base_path = getattr(sys, "_MEIPASS", _PACKAGE_DIR)
    return os.path.join(base_path, relative_path)


def icon_path(name: str) -> str:
    """Path to a bundled ``.ico`` file in the ``icons`` folder."""
    return get_resource(os.path.join("icons", name))
