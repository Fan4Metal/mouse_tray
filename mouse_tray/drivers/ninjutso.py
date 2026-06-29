"""Ninjutso mice (HID feature-report protocol).

Protocol: send a 32-byte feature report (ID 5), then read it back. The reply
carries battery percent (byte 9), charging (10), full-charge (11) and an
online flag (12).
"""

from __future__ import annotations

import logging

from ..battery import BatteryStatus
from .driver import MouseModel, register
from .hid import HidDriver

log = logging.getLogger(__name__)

_USAGE_PAGE = 0xFFA0


@register
class NinjutsoDriver(HidDriver):
    vendor = "Ninjutso"
    models = [
        MouseModel("Ninjutso Sora V2", 0x1915, 0xAE1C, 0xAE11, _USAGE_PAGE),
    ]

    def read_status(self) -> BatteryStatus:
        report = [0] * 32
        report[0] = 5  # report ID
        report[1] = 21
        report[4] = 1
        res = self._transact(report, 32, feature=True, delay=0.09)
        if res is None:
            return BatteryStatus.absent()

        percent = res[9]
        charging = bool(res[10])
        full = bool(res[11])
        online = bool(res[12])
        log.info(
            "%s battery=%s charging=%s full=%s online=%s",
            self.name, percent, charging, full, online,
        )
        return BatteryStatus(
            present=True,
            percent=percent,
            charging=charging,
            full=full,
            asleep=(not online) or percent == 0,
        )
