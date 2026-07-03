"""Driver package.

Importing this package imports every driver module, which runs their
``@register`` decorators and populates the registry. New vendors are picked up
automatically: drop a ``drivers/<vendor>.py`` that registers a driver and add
its name to ``_DRIVER_MODULES`` below.

Public API: :func:`detect_driver`, :func:`all_drivers`, plus the building
blocks :class:`MouseModel`, :class:`MouseDriver` and :func:`register`.
"""

from __future__ import annotations

import importlib

from .driver import (
    MouseDriver,
    MouseModel,
    all_drivers,
    detect_driver,
    register,
)

# Vendor modules to load. Order here is the detection probe order.
_DRIVER_MODULES = [
    "nordic52",
    "nordic54",
    "ninjutso",
    "razer",
    "realtek",
    "lamzu",
    "logitech",
    "attackshark",
]

for _name in _DRIVER_MODULES:
    importlib.import_module(f"{__name__}.{_name}")

__all__ = [
    "MouseDriver",
    "MouseModel",
    "all_drivers",
    "detect_driver",
    "register",
]
