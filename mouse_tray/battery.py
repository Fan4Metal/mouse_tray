"""The universal battery status model.

Every driver, regardless of vendor or transport, returns one of these.
The UI state machine renders it without knowing which mouse produced it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BatteryStatus:
    """Normalized snapshot of a mouse battery.

    Attributes:
        present:  The device is connected/reachable. ``False`` -> "no mouse".
        percent:  Charge level 0-100, or ``None`` when unknown.
        charging: On the cable/dock and actively charging (not yet full).
        full:     Sitting on power and fully charged (100%).
        asleep:   Device is in sleep/standby (reports no usable level -> "Zzz").
    """

    present: bool
    percent: int | None = None
    charging: bool = False
    full: bool = False
    asleep: bool = False

    @classmethod
    def absent(cls) -> "BatteryStatus":
        """No supported mouse is currently reachable."""
        return cls(present=False)
