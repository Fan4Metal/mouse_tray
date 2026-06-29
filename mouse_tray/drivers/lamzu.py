"""Lamzu mice (HID feature-report protocol).

Protocol (interface 2, usage page 0xFFFF): send a 65-byte feature report
(ID 0) whose command byte selects the battery query, then read it back. A valid
reply is tagged ``0xA1`` at byte 1 and echoes the command ``0x83`` at byte 6;
charging lives at byte 7 and the percent at byte 8.

Ported from the Rust ``lamzu-battery-monitor``:
https://github.com/Sheroune/lamzu-battery-monitory
"""

from __future__ import annotations

import logging

from ..battery import BatteryStatus
from .driver import MouseModel, register
from .hid import HidDriver

log = logging.getLogger(__name__)

_USAGE_PAGE = 0xFFFF
_INTERFACE = 2
_REPLY_TAG = 0xA1
_BATTERY_CMD = 0x83


@register
class LamzuDriver(HidDriver):
    vendor = "Lamzu"
    models = [
        MouseModel(
            "Lamzu Maya X",
            0x373E,
            0x001E,
            0x001C,
            usage_page=_USAGE_PAGE,
            interface=_INTERFACE,
        ),
        MouseModel(
            "Lamzu Inca",
            0x37B0,
            0x0010,
            0x0009,
            usage_page=_USAGE_PAGE,
            interface=_INTERFACE,
        ),
    ]

    def read_status(self) -> BatteryStatus:
        report = [0] * 65
        report[0] = 0x00  # report ID
        report[3] = 0x02  # device ID
        report[4] = 0x02  # length
        report[6] = _BATTERY_CMD
        res = self._transact(report, 65, feature=True, delay=0.1)
        if res is None or len(res) < 9:
            return BatteryStatus.absent()

        # Validate the reply tag and command echo before trusting the bytes.
        if res[1] != _REPLY_TAG or res[6] != _BATTERY_CMD:
            log.warning("%s unexpected reply: tag=%s cmd=%s", self.name, res[1], res[6])
            return BatteryStatus.absent()

        charging = res[7] == 1
        percent = res[8]
        log.info("%s battery=%s charging=%s", self.name, percent, charging)
        return BatteryStatus(
            present=True,
            percent=percent,
            charging=charging and percent < 100,
            full=charging and percent >= 100,
            asleep=False,
        )
