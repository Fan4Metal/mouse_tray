"""Attack Shark wireless mice (Beken / Feeling Technology dongle).

Unlike every request/reply vendor in this package, these dongles *push* an
unsolicited battery report on a vendor HID collection roughly every two seconds
-- no command is ever sent. So this driver does not :meth:`_transact`; it opens
the collection and waits for the next pushed input report.

The 5-byte report (numbered ID ``0x03``) looks like ``03 10 40 01 LL``:

* bytes 1-3 (``10 40 01``) are constant -- there is **no charging flag**;
* ``LL`` is the charge level in steps of ten, so ``percent = LL * 10``
  (``0x07`` -> 70%, ``0x08`` -> 80%, ``0x0a`` -> 100%).

While charging over the dongle link the level simply pegs at ``0x0a`` (100%),
so charging cannot be distinguished from a full battery -- we report the percent
and mark 100% as full. The report rides an oddly-tagged collection (usage page
``0x000A``); that page is unique among the device's collections, so it pins the
right one.

The push only happens on the wireless link. Plugged in *directly* by cable the
mouse enumerates under its own wired PID and never pushes a battery report, so
that mode is reported as charging without a level (same as the Nordic 54 driver).
Reverse-engineered from a USB capture of the Attack Shark X3.
"""

from __future__ import annotations

import logging
import time

import hid  # hidapi -- the single core transport dependency

from ...battery import BatteryStatus
from ..driver import MouseModel, register
from ..hid import HidDriver

log = logging.getLogger(__name__)

_BATTERY_REPORT_ID = 0x03
_REPORT_LEN = 8  # report is 5 bytes; read a little extra to be safe
_LEVEL_BYTE = 4
#: The device pushes a report about every 2 s; wait a bit longer than that.
_POLL_TIMEOUT_MS = 2500

# The battery report lives on this collection (see module docstring).
_USAGE_PAGE = 0x000A
_USAGE = 0x0000
_INTERFACE = 2


@register
class AttackSharkDriver(HidDriver):
    vendor = "Attack Shark"
    models = [
        MouseModel("Attack Shark X3", 0x1D57, 0xFA60, 0xFA61, _USAGE_PAGE, _USAGE, _INTERFACE),
    ]

    def read_status(self) -> BatteryStatus:
        if self._connected_wired():
            # Direct USB: the mouse doesn't push a battery report; it's just
            # running off (and charging from) the cable. Report charging only.
            log.info("%s wired: charging, level not reported", self.name)
            return BatteryStatus(present=True, percent=None, charging=True)

        report = self._read_battery_report()
        if report is None or len(report) <= _LEVEL_BYTE:
            return BatteryStatus.absent()

        percent = min(report[_LEVEL_BYTE] * 10, 100)
        # No charging flag is exposed; on the cable the level just pegs at 100%.
        log.info("%s battery=%s%%", self.name, percent)
        return BatteryStatus(
            present=True,
            percent=percent,
            full=percent >= 100,
            asleep=False,
        )

    def _read_battery_report(self) -> list[int] | None:
        """Wait for the next pushed battery report (ID ``0x03``).

        Returns the raw report, or ``None`` if the collection is gone
        (hot-unplug) or no battery report arrived within the timeout.
        """
        path = self._device_path()
        if path is None:
            return None
        device = hid.device()
        try:
            device.open_path(path)
        except OSError as exc:
            log.warning("%s could not open battery collection: %s", self.name, exc)
            return None
        try:
            deadline = time.monotonic() + _POLL_TIMEOUT_MS / 1000
            while True:
                remaining_ms = int((deadline - time.monotonic()) * 1000)
                if remaining_ms <= 0:
                    return None
                data = device.read(_REPORT_LEN, timeout_ms=remaining_ms)
                if data and data[0] == _BATTERY_REPORT_ID:
                    log.debug("%s battery report: %s", self.name, data)
                    return data
                # Empty read (timed out) or some other report id -> keep waiting
                # until the deadline for the next pushed battery report.
        except OSError as exc:
            log.warning("%s HID read failed: %s", self.name, exc)
            return None
        finally:
            try:
                device.close()
            except Exception:
                pass
