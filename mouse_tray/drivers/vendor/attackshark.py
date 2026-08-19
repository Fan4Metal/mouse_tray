"""Attack Shark wireless mice (Beken / Feeling Technology dongle).

Unlike every request/reply vendor in this package, these dongles *push*
unsolicited status reports on a vendor HID collection roughly every two seconds
-- no command is ever sent. So this driver does not :meth:`_transact`; it opens
the collection and waits for the next pushed input report. The reports ride the
vendor-defined interface (interface 2), tagged with the oddly-numbered usage
page ``0x000A``; that page is unique among the device's collections, so it pins
the right one.

Report layout
=============

The 5-byte report (numbered ID ``0x03``) is one instance of a small generic
event format the dongle uses for *every* asynchronous message::

    03 DD EE P1 P2
    |  |  |  |  |
    |  |  |  |  `-- param 2
    |  |  |  `----- param 1
    |  |  `-------- event code
    |  `----------- device id
    `-------------- event opcode, always 0x03

Event code ``0x40`` (``0x41`` is also seen in the wild) is the battery event.
The vendor software calls it the *device connection message*, but battery state
is what it actually carries: ``P1`` is the charging state (``1`` charging
complete, ``2`` fully charged, ``3`` charging in progress -- the last one also
implying the mouse is running off a cable) and ``P2`` is the charge level.

The device id is not a constant -- it names the model, not the vendor, and the
VID/PID are shared across much of the line, so it is the only in-band model
marker. Published ids: X3 ``0x4D``, X11 ``0x55``, R1 ``0x10``, X6 ``0x85``,
X11 Pro ``0xBE``, X11 SE ``0x07``. The driver ignores the byte entirely.

Two decoding details here **disagree with that documentation**, and both are
worth settling against hardware before this driver grows a second model:

* The published ``P2`` is a plain percent (``0x64`` = 100%) on every mouse
  speaking this protocol, but the note left behind by the capture this driver
  was written from reads the level in steps of ten (``0x07`` -> 70%, ``0x0a``
  -> 100%), which is what :meth:`read_status` still decodes. What tipped the
  scale then was that the level pegged at ``0x0a`` while charging over the
  dongle link -- 10% would be an odd place for a charging battery to sit. The
  capture itself is gone, so nothing here re-verifies it; a debug log of one
  raw report at a known charge level settles it in one reading.
* That same note records the device id as ``0x10``, which the table above
  assigns to the R1, not to the X3 this driver lists. Either the byte was
  mis-transcribed or the unit is a rebadge. Harmless, since nothing reads it.

The charging state is likewise not parsed: ``P1`` was recorded as a constant
``0x01`` (charging complete) throughout, charging included, so on this unit
charging cannot be told from a full battery -- the driver reports the percent
and marks 100% as full. Trusting ``P1`` needs a model seen to move it.

Note also that opcode ``0x03`` is shared by *every* asynchronous event the
dongle sends (a feature-report status and a vibration-mode notification are
documented elsewhere), so the report id alone does not pin the battery event --
the event code in byte 2 does. Only ``0x40`` was ever seen there on this
device, which is why matching on the report id gets away with it here.

One more quirk worth knowing when a reading looks too good: on the X11 the
first battery report after the link comes up can read ``0x64`` (100%) before
the firmware has measured anything, with the true value arriving in a later
report.

Wired mode
==========

The push only happens on the wireless link. Plugged in *directly* by cable the
mouse enumerates under its own wired PID and never pushes a battery report, so
that mode is reported as charging without a level (same as the Nordic 54
driver).

Originally reverse-engineered from a USB capture of the Attack Shark X3. The
event format, the device-id table, the charging-state field and the first-report
quirk come from HarukaYamamoto0's notes on the X11, contributed in
https://github.com/Fan4Metal/mouse_tray/issues/1 and documented at
https://github.com/HarukaYamamoto0/attack-shark-x11-driver/tree/main/docs/messages
"""

from __future__ import annotations

import logging
import time
from contextlib import suppress
from typing import ClassVar

import hid  # hidapi -- the single core transport dependency

from ...battery import BatteryStatus
from ..driver import MouseModel, register
from ..hid import HidDriver

log = logging.getLogger(__name__)

_BATTERY_REPORT_ID = 0x03  # event opcode, shared by every pushed event
_REPORT_LEN = 8  # report is 5 bytes; read a little extra to be safe
_LEVEL_BYTE = 4  # param 2 of the battery event
#: The device pushes a report about every 2 s; wait a bit longer than that.
_POLL_TIMEOUT_MS = 2500

# The battery report lives on this collection (see module docstring).
_USAGE_PAGE = 0x000A
_USAGE = 0x0000
_INTERFACE = 2


@register
class AttackSharkDriver(HidDriver):
    vendor = "Attack Shark"
    models: ClassVar[list[MouseModel]] = [
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
        # The charging state (param 1) never moved on this model; over the
        # dongle link the level just pegs at 100% instead. See the docstring.
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
            with suppress(Exception):
                device.close()
