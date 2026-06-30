"""Logitech wireless mice (HID++ 2.0 via receiver).

Battery is read through the UnifiedBattery feature (0x1004): function 1
(get_status) returns state-of-charge %, a level enum, a charging-status byte
and an external-power flag.

charging_status: 0 discharging, 1 charging, 2 almost full, 3 full,
4 slow recharge, 5 invalid battery, 6 thermal error.

The device name is queried at runtime (feature 0x0005), so a single receiver
entry covers every Lightspeed mouse paired to it. Verified live against a
Lightspeed receiver (PID 0xC54D).
"""

from __future__ import annotations

import logging

from ..battery import BatteryStatus
from .driver import MouseModel, register
from .hidpp import HidppDriver

log = logging.getLogger(__name__)

_UNIFIED_BATTERY = 0x1004
_CHARGING_STATES = {1, 2, 4}  # actively charging (not yet "full")
_FULL_STATE = 3

# The receiver is plugged in but the mouse is not answering -- over HID++ a
# sleeping mouse is indistinguishable from an absent one, so we report "asleep"
# (the tray shows "Zzz") rather than "no mouse" whenever the receiver is there.
_ASLEEP = BatteryStatus(present=True, asleep=True)


def _hidpp_device(name: str, pid: int) -> MouseModel:
    # A HID++ endpoint -- a receiver or a mouse connected directly. Either way
    # HID++ lives on interface 2 / usage page 0xFF00 (short + long collections).
    return MouseModel(name, 0x046D, pid, pid, usage_page=0xFF00, interface=2)


@register
class LogitechDriver(HidppDriver):
    vendor = "Logitech"
    # One entry per PID, mostly receivers; the actual mouse name is resolved
    # over HID++. PIDs not marked "verified" come from Solaar's receiver table
    # and are best-effort -- only HID++ 2.0 capable receivers belong here (older
    # Nano / HID++ 1.0 dongles don't expose UnifiedBattery and would never read).
    models = [
        # Lightspeed gaming receivers (incl. Powerplay mat, which is one too).
        _hidpp_device("Logitech Lightspeed", 0xC54D),  # verified
        _hidpp_device("Logitech Lightspeed", 0xC539),
        _hidpp_device("Logitech Lightspeed", 0xC545),
        _hidpp_device("Logitech Lightspeed", 0xC53A),  # Powerplay
        _hidpp_device("Logitech Lightspeed", 0xC53F),
        _hidpp_device("Logitech Lightspeed", 0xC541),
        _hidpp_device("Logitech Lightspeed", 0xC547),
        # Mice connected directly (USB cable / Bluetooth) expose HID++ under
        # their own PID instead of a receiver's; the same code path works (the
        # device answers on every index, so index 1 resolves). Verified wired.
        _hidpp_device("Logitech PRO X2 SUPERSTRIKE", 0xC0A8),
        # Bolt receivers.
        _hidpp_device("Logitech Bolt", 0xC548),
        # Unifying receivers.
        _hidpp_device("Logitech Unifying", 0xC52B),
        _hidpp_device("Logitech Unifying", 0xC532),
    ]

    def read_status(self) -> BatteryStatus:
        with self._connection() as conn:
            if conn is None:
                return BatteryStatus.absent()

            if self._device_index is None:
                self._device_index = self._resolve_device_index(conn)
            if self._device_index is None:
                return _ASLEEP  # receiver present, mouse silent -> asleep
            dev = self._device_index

            if self._name is None:
                self._name = self._read_device_name(conn, dev)

            batt_idx = self._feature_index(conn, _UNIFIED_BATTERY, device_index=dev)
            if not batt_idx:
                log.warning("%s has no UnifiedBattery feature", self.name)
                return BatteryStatus.absent()

            res = self._call(conn, batt_idx, 0x01, device_index=dev)
            if not res:
                return _ASLEEP  # stopped answering -> asleep

            percent = res[4]
            charging_status = res[6]
            log.info("%s SoC=%s%% charging_status=%s", self.name, percent, charging_status)
            return BatteryStatus(
                present=True,
                percent=percent,
                charging=charging_status in _CHARGING_STATES,
                full=charging_status == _FULL_STATE,
                asleep=False,
            )
