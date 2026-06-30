"""ATK / VXE / VGN mice (shared HID protocols).

Two wire protocols are in the wild:

* **v1** (Nordic 52840 MCU): interrupt write of a 17-byte report (ID 8) then a
  17-byte read. Battery percent is at byte 6, the wired/charging flag at byte 7.
  Covers everything except ATK Zero.
* **v2** (Nordic 54L15 MCU, ATK Zero): a 64-byte report (ID 8) tagged with
  command 0x72, on a different HID collection (usage page 0xFF05). The request
  differs by link, and the cable does not report a usable level -- so wired just
  shows "charging" while wireless reads the percent at byte 7.

A model's ``usage_page`` selects the protocol (v2 lives on 0xFF05), so a single
driver serves both. Reference implementation:
https://github.com/Fan4Metal/ATK_tray

These are really the shared protocols of the underlying Compx/Nordic silicon
(receivers enumerate as "Compx"), not anything brand-specific, so same-chipset
rebrands beyond ATK/VXE/VGN fit too -- e.g. the Zaopin Z2 Mini speaks plain v1.
Adding such a mouse is just one more ``_v1`` (or ``_v2``) row with its VID/PID.
Unlike v2, v1 reports a usable level on the cable as well, with byte 7
distinguishing wired from wireless -- confirmed from Zaopin captures reading the
percent at byte 6 over both the 2.4G receiver (byte 7 = 0) and a direct cable
(byte 7 = 1).
"""

from __future__ import annotations

import logging

from ..battery import BatteryStatus
from .driver import MouseModel, register
from .hid import HidDriver

log = logging.getLogger(__name__)

_USAGE_PAGE = 0xFF02
_USAGE = 0x0002

# ATK Zero speaks v2 on its own HID collection.
_V2_USAGE_PAGE = 0xFF05
_V2_USAGE = 0x0001
_V2_CMD = 0x72


def _v1(name: str, vid: int, pid_wireless: int, pid_wired: int) -> MouseModel:
    return MouseModel(name, vid, pid_wireless, pid_wired, _USAGE_PAGE, _USAGE)


def _v2(name: str, vid: int, pid_wireless: int, pid_wired: int) -> MouseModel:
    return MouseModel(name, vid, pid_wireless, pid_wired, _V2_USAGE_PAGE, _V2_USAGE)


@register
class AtkDriver(HidDriver):
    vendor = "ATK / VXE / VGN"
    models = [
        _v1("ATK F1 Ultimate", 0x373B, 0x1031, 0x102E),
        _v1("ATK A9 Ultimate", 0x373B, 0x11D9, 0x11B6),
        _v2("ATK Zero", 0x373B, 0x1155, 0x1154),
        _v1("VXE MAD R", 0x373B, 0x104D, 0x103F),
        _v1("VXE MAD R Major Plus", 0x373B, 0x1040, 0x104C),
        _v1("VXE R1 Pro Max", 0x3554, 0xF58A, 0xF58C),
        _v1("VXE R1 SE+", 0x3554, 0xF58E, 0xF58F),
        _v1("VGN F1 Pro", 0x3554, 0xF503, 0xF502),
        # Compx rebrand on the same v1 silicon; receiver F524, direct cable F526.
        _v1("Zaopin Z2 Mini", 0x3554, 0xF524, 0xF526),
    ]

    def read_status(self) -> BatteryStatus:
        if self.model.usage_page == _V2_USAGE_PAGE:
            return self._read_v2()
        return self._read_v1()

    def _read_v1(self) -> BatteryStatus:
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

    def _read_v2(self) -> BatteryStatus:
        wired = self._connected_wired()
        report = [0] * 64
        report[0] = 0x08  # report ID
        report[1] = 0x7C if wired else 0x7D
        report[2] = _V2_CMD
        report[3] = 0x02
        report[5] = 0x00 if wired else 0x01
        report[6] = 0x07
        report[7] = 0x01
        res = self._transact(report, 64, feature=False, delay=0.1)
        if res is None or len(res) < 8:
            return BatteryStatus.absent()
        if res[1] != _V2_CMD or res[5] != 0x07:
            log.warning("%s unexpected v2 reply: %s", self.name, res[:8])
            return BatteryStatus.absent()

        if wired:
            # On the cable v2 gives no usable level -- report charging only.
            log.info("%s wired (v2): charging, level not reported", self.name)
            return BatteryStatus(present=True, percent=None, charging=True)

        percent = res[7]
        log.info("%s battery=%s (v2, wireless)", self.name, percent)
        return BatteryStatus(present=True, percent=percent, asleep=False)
