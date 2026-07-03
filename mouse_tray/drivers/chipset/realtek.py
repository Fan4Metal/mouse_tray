"""MCHOSE mice on the RealTek chipset (VID 0x5253).

Unlike the request/reply vendors, the battery here rides a **pushed** input
report. The mouse periodically emits report id ``0x13`` on its vendor HID
collection (usage page 0xFF01); sub-type ``0x1d`` carries the battery. All
payload bytes are obfuscated with **XOR 0xFF** -- decode and the tail spells the
model name ("L7 Pro") with the battery percent sitting at offset 5:

    raw   13 1d fe fe ff a2 fd fd f9 d9 b3 c8 df af 8d 90
    ^0xFF          .. .. .. 5d .. .. .. .. 4c 37 20 50 72 6f   -> 0x5d = 93%, "L7 Pro"

The push arrives roughly every ~2 s. Poking the device with the vendor's
``0xf9`` feature report nudges it along, but we still just wait for the next
``0x1d`` within a short window. The device's feature-report *reads* are racy
(they return the previous command's buffer), so the pushed report is the
reliable source. Reverse-engineered from a USB capture of the MCHOSE L7 Pro;
see ``examples/Mchose L7 pro``.

On the cable the mouse enumerates under a different PID but the same vendor
collection, and decoded offset 4 of the ``0x1d`` report flips to 1 (offset 2
mirrors it) -- that is the wired flag, treated as charging until 100%.
"""

from __future__ import annotations

import logging
import time

import hid

from ...battery import BatteryStatus
from ..driver import MouseModel, register
from ..hid import HidDriver

log = logging.getLogger(__name__)

_USAGE_PAGE = 0xFF01
_USAGE = 0x0001

# Vendor feature report that nudges the mouse to emit its status push.
_NUDGE = [0x11, 0xF9] + [0xFF] * 19
# Pushed report: id 0x13, sub-type 0x1d, battery percent (XOR 0xFF) at offset 5.
_REPORT_ID = 0x13
_SUBTYPE = 0x1D
_BATTERY_OFFSET = 5
# Decoded offset 4: 1 on the cable, 0 on the 2.4G link (offset 2 mirrors it).
_WIRED_OFFSET = 4
# The push cycles about every 2 s; give it a little headroom.
_READ_TIMEOUT = 3.0


def _model(name: str, vid: int, pid_wireless: int, pid_wired: int) -> MouseModel:
    return MouseModel(name, vid, pid_wireless, pid_wired, _USAGE_PAGE, _USAGE)


@register
class RealtekDriver(HidDriver):
    vendor = "MCHOSE"
    models = [
        # 2.4G dongle 0x1020, direct cable 0x00B0.
        _model("MCHOSE L7 Pro", 0x5253, 0x1020, 0x00B0),
    ]

    def read_status(self) -> BatteryStatus:
        path = self._device_path()
        if path is None:
            return BatteryStatus.absent()
        device = hid.device()
        try:
            device.open_path(path)
            try:
                device.send_feature_report(_NUDGE)  # nudge; harmless if it fails
            except OSError:
                pass
            device.set_nonblocking(1)
            deadline = time.monotonic() + _READ_TIMEOUT
            while time.monotonic() < deadline:
                res = device.read(64)
                if not res:
                    time.sleep(0.01)
                    continue
                if res[0] == _REPORT_ID and len(res) > _BATTERY_OFFSET and res[1] == _SUBTYPE:
                    percent = res[_BATTERY_OFFSET] ^ 0xFF
                    if 0 <= percent <= 100:
                        wired = bool(res[_WIRED_OFFSET] ^ 0xFF)
                        log.info("%s battery=%s wired=%s", self.name, percent, wired)
                        return BatteryStatus(
                            present=True,
                            percent=percent,
                            charging=wired and percent < 100,
                            full=wired and percent >= 100,
                            asleep=False,
                        )
                    log.warning("%s implausible percent %s", self.name, percent)
            log.info("%s no status push within %.0fs", self.name, _READ_TIMEOUT)
            return BatteryStatus.absent()
        except OSError as exc:
            log.warning("%s HID read failed: %s", self.name, exc)
            return BatteryStatus.absent()
        finally:
            try:
                device.close()
            except Exception:
                pass
