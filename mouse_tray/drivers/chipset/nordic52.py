"""Compx mice on the Nordic 52840 MCU.

Interrupt write of a 17-byte report (ID 8) then a 17-byte read. Battery percent
is at byte 6, the wired/charging flag at byte 7. This is really the shared
protocol of the underlying Compx/Nordic silicon (receivers enumerate as
"Compx"), not anything brand-specific, so any same-chipset rebrand fits -- ATK,
VXE, VGN, Zaopin, Scyrox all speak it. Adding such a mouse is just one more
``_model`` row with its VID/PID. Reference implementation:
https://github.com/Fan4Metal/ATK_tray

It reports a usable level on the cable as well, with byte 7 distinguishing wired
from wireless -- confirmed from Zaopin captures reading the percent at byte 6
over both the 2.4G receiver (byte 7 = 0) and a direct cable (byte 7 = 1).

The newer Nordic 54L15 silicon (e.g. ATK Zero) speaks a different, 64-byte
protocol on its own HID collection -- see :mod:`~mouse_tray.drivers.chipset.nordic54`.
"""

from __future__ import annotations

import logging

from ...battery import BatteryStatus
from ..driver import MouseModel, register
from ..hid import HidDriver

log = logging.getLogger(__name__)

_USAGE_PAGE = 0xFF02
_USAGE = 0x0002


def _model(name: str, vid: int, pid_wireless: int, pid_wired: int) -> MouseModel:
    return MouseModel(name, vid, pid_wireless, pid_wired, _USAGE_PAGE, _USAGE)


@register
class Nordic52Driver(HidDriver):
    vendor = "ATK / VXE / VGN / Zaopin / Scyrox"
    models = [
        _model("ATK F1 Ultimate", 0x373B, 0x1031, 0x102E),
        _model("ATK A9 Ultimate", 0x373B, 0x11D9, 0x11B6),
        _model("VXE MAD R", 0x373B, 0x104D, 0x103F),
        _model("VXE MAD R Major Plus", 0x373B, 0x1040, 0x104C),
        _model("VXE R1 Pro Max", 0x3554, 0xF58A, 0xF58C),
        _model("VXE R1 SE+", 0x3554, 0xF58E, 0xF58F),
        _model("VGN F1 Pro", 0x3554, 0xF503, 0xF502),
        # Compx rebrand on the same silicon; receiver F524, direct cable F526.
        _model("Zaopin Z2 Mini", 0x3554, 0xF524, 0xF526),
        # Another Compx rebrand; "SCYROX 8K Dongle" F5F7, direct cable F5F6.
        _model("Scyrox V8", 0x3554, 0xF5F7, 0xF5F6),
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
