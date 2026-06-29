"""ATK / VXE / VGN mice (shared HID protocol).

Protocol: interrupt write of a 17-byte report (ID 8) followed by a 17-byte
read. Battery percent is at byte 6, the wired/charging flag at byte 7.
"""

from __future__ import annotations

import logging

from ..battery import BatteryStatus
from .driver import MouseModel, register
from .hid import HidDriver

log = logging.getLogger(__name__)

_USAGE_PAGE = 0xFF02
_USAGE = 0x0002


def _m(name: str, vid: int, pid_wireless: int, pid_wired: int) -> MouseModel:
    return MouseModel(name, vid, pid_wireless, pid_wired, _USAGE_PAGE, _USAGE)


@register
class AtkDriver(HidDriver):
    vendor = "ATK / VXE / VGN"
    models = [
        _m("ATK F1 Ultimate", 0x373B, 0x1031, 0x102E),
        _m("ATK A9 Ultimate", 0x373B, 0x11D9, 0x11B6),
        _m("VXE MAD R", 0x373B, 0x104D, 0x103F),
        _m("VXE MAD R Major Plus", 0x373B, 0x1040, 0x104C),
        _m("VXE R1 Pro Max", 0x3554, 0xF58A, 0xF58C),
        _m("VXE R1 SE+", 0x3554, 0xF58E, 0xF58F),
        _m("VGN F1 Pro", 0x3554, 0xF503, 0xF502),
    ]

    def read_status(self) -> BatteryStatus:
        report = [0] * 17
        report[0] = 8  # report ID
        report[1] = 4
        report[16] = 73
        res = self._transact(report, 17, feature=False, delay=0.1)
        if res is None:
            return BatteryStatus.absent()

        percent = res[6]
        wired = bool(res[7])
        log.info("%s battery=%s wired=%s", self.name, percent, wired)
        return BatteryStatus(
            present=True,
            percent=percent,
            charging=wired and percent < 100,
            full=wired and percent >= 100,
            asleep=False,
        )
