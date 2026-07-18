"""Compx mice on the Nordic 52840 MCU.

This is the shared protocol of the underlying Compx/Nordic silicon, not anything
brand-specific: receivers enumerate as "Compx" and every rebrand of the chipset
speaks it -- ATK, VXE, VGN, Zaopin, Scyrox, Dareu... Adding such a mouse is just
one more ``_model`` row with its VID/PID. Reference implementation:
https://github.com/Fan4Metal/ATK_tray

Every report -- in both directions -- is 17 bytes, numbered id ``0x08``, with the
second byte selecting a sub-command. The battery query is sub-command ``0x04``:

    write   08 04 00 00 00 00 00 00 00 00 00 00 00 00 00 00 49
    read    08 04 00 00 00 02 23 00 0e 94 00 00 00 00 00 00 82
            ^id ^sub          ^st ^%  ^w  ^^^^^ voltage        ^cksum
                                 0x23 = 35%      0x0e94 = 3732 mV

Battery percent sits at offset 6; offset 7 is the wired/charging flag -- ``0`` on
the 2.4G link, ``1`` on a direct cable (confirmed from Zaopin captures reading the
same percent at offset 6 over both). Offset 5 is a status byte and offset 8-9 the
cell voltage in millivolts (~3.7 V here); neither is needed. The last byte is a
checksum -- all 17 bytes sum to ``0x55`` mod 256, so the fixed request carries a
baked-in ``0x49`` (= 73). The battery collection is usage page ``0xFF02`` (usage
``0x02``), which pins it among the several the vendor interface splits into.

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
    vendor = "Compx / Nordic"
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
        # "DAREU Receiver" dongle 0x1175, direct cable 0x1193.
        _model("Dareu A950 Air", 0x260D, 0x1175, 0x1193),
        # "G-Wolves Receiver RS" dongle 0x3854, direct cable 0x4719.
        _model("G-Wolves Lycan", 0x33E4, 0x3854, 0x4719),
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
