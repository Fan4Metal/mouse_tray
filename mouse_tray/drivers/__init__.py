"""Driver package.

Importing this package imports every driver module, which runs their
``@register`` decorators and populates the registry. Drivers live in two
subpackages: ``chipset/`` for shared-silicon protocols (named after the chipset,
spanning whatever brands rebrand it) and ``vendor/`` for brand-specific
protocols. Adding one means dropping a module in the right subpackage and listing
it in ``_DRIVER_MODULES`` below.

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

# Driver modules to load. Order here is the detection probe order.
_DRIVER_MODULES = [
    "chipset.nordic52",
    "chipset.nordic54",
    "vendor.ninjutso",
    "vendor.razer",
    "chipset.realtek",
    "vendor.lamzu",
    "vendor.logitech",
    "vendor.attackshark",
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
