"""Compx mice on the Nordic 54L15 MCU.

A 64-byte report (ID 8) tagged with command 0x72, on a dedicated HID collection
(usage page 0xFF05). The request differs by link, and the cable does not report
a usable level -- so wired just shows "charging" while wireless reads the
percent at byte 7. So far only the ATK Zero uses this silicon.

The older Nordic 52840 mice (ATK/VXE/VGN/Zaopin/Scyrox) speak a simpler 17-byte
protocol -- see :mod:`~mouse_tray.drivers.nordic52`. Reference implementation:
https://github.com/Fan4Metal/ATK_tray
"""

from __future__ import annotations

import logging

from ..battery import BatteryStatus
from .driver import MouseModel, register
from .hid import HidDriver

log = logging.getLogger(__name__)

_USAGE_PAGE = 0xFF05
_USAGE = 0x0001
_CMD = 0x72


def _model(name: str, vid: int, pid_wireless: int, pid_wired: int) -> MouseModel:
    return MouseModel(name, vid, pid_wireless, pid_wired, _USAGE_PAGE, _USAGE)


@register
class Nordic54Driver(HidDriver):
    vendor = "ATK"
    models = [
        _model("ATK Zero", 0x373B, 0x1155, 0x1154),
    ]

    def read_status(self) -> BatteryStatus:
        wired = self._connected_wired()
        report = [0] * 64
        report[0] = 0x08  # report ID
        report[1] = 0x7C if wired else 0x7D
        report[2] = _CMD
        report[3] = 0x02
        report[5] = 0x00 if wired else 0x01
        report[6] = 0x07
        report[7] = 0x01
        res = self._transact(report, 64, feature=False, delay=0.1)
        if res is None or len(res) < 8:
            return BatteryStatus.absent()
        if res[1] != _CMD or res[5] != 0x07:
            log.warning("%s unexpected reply: %s", self.name, res[:8])
            return BatteryStatus.absent()

        if wired:
            # On the cable this gives no usable level -- report charging only.
            log.info("%s wired: charging, level not reported", self.name)
            return BatteryStatus(present=True, percent=None, charging=True)

        percent = res[7]
        log.info("%s battery=%s (wireless)", self.name, percent)
        return BatteryStatus(present=True, percent=percent, asleep=False)
