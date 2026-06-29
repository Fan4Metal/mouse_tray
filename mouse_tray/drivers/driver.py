"""Driver contract and the auto-registry.

A *driver* knows how to detect a family of mice and read their battery. Adding
support for a new vendor means writing one module under ``drivers/`` that
declares a :class:`MouseDriver` subclass decorated with :func:`register` and a
table of :class:`MouseModel` rows. Everything else (UI, polling, packaging)
stays untouched.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..battery import BatteryStatus

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MouseModel:
    """A single supported mouse and how to find it on the bus.

    ``usage_page`` / ``usage`` / ``interface`` are HID disambiguators: a mouse
    exposes several HID collections and the battery lives on a specific one.
    Set only the ones a given device actually needs to be matched uniquely;
    leave the rest as ``None``.
    """

    name: str
    vid: int
    pid_wireless: int
    pid_wired: int
    usage_page: int | None = None
    usage: int | None = None
    interface: int | None = None


class MouseDriver(ABC):
    """Base class for all vendor drivers.

    A driver instance is bound to one concrete, currently-connected
    :class:`MouseModel` (set by :meth:`detect`).
    """

    #: Human-readable vendor label, e.g. "ATK / VXE / VGN".
    vendor: str = ""
    #: Models this driver can talk to. Subclasses override.
    models: list[MouseModel] = []

    def __init__(self, model: MouseModel):
        self.model = model

    @property
    def name(self) -> str:
        """Display name shown in the tooltip and notifications."""
        return self.model.name

    @classmethod
    @abstractmethod
    def detect(cls) -> "MouseDriver | None":
        """Return an instance bound to the first connected supported model.

        ``None`` when no model handled by this driver is plugged in. Must not
        raise for an absent device.
        """

    @abstractmethod
    def read_status(self) -> BatteryStatus:
        """Read the current battery state.

        Returns :meth:`BatteryStatus.absent` if the device vanished between
        detection and this call (hot-unplug). Must not raise for I/O hiccups.
        """


# --- Registry ---------------------------------------------------------------

_REGISTRY: list[type[MouseDriver]] = []


def register(driver_cls: type[MouseDriver]) -> type[MouseDriver]:
    """Class decorator that adds a driver to the global registry."""
    _REGISTRY.append(driver_cls)
    log.debug("Registered driver: %s", driver_cls.__name__)
    return driver_cls


def all_drivers() -> list[type[MouseDriver]]:
    """Every registered driver class, in registration order."""
    return list(_REGISTRY)


def detect_driver() -> MouseDriver | None:
    """Probe every registered driver and return the first connected mouse.

    Drivers whose optional backend (e.g. pyusb) is missing are skipped with a
    warning rather than crashing the app.
    """
    for driver_cls in _REGISTRY:
        try:
            driver = driver_cls.detect()
        except Exception as exc:  # a misbehaving driver must not kill detection
            log.warning("Driver %s failed during detection: %s", driver_cls.__name__, exc)
            continue
        if driver is not None:
            log.info("Detected %s (%s)", driver.name, driver_cls.vendor)
            return driver
    return None
