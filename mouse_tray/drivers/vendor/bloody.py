"""A4Tech Bloody mice on the "8K" wireless dongle (VID 0x1956).

Not the classic Bloody protocol (VID 0x09DA, 64/72-byte feature report 7 that
every public tool speaks) -- the 8K dongle is a different firmware with its own
VID, and nothing about it is documented anywhere. Everything here comes from a
USBPcap of the vendor's *Wireless 8KM-Esport Editor* talking to a Bloody SG5 Pro,
contributed by JurecUA in https://github.com/Fan4Metal/mouse_tray/issues/5.

The device exposes three HID interfaces; two of them matter:

* **interface 2** (usage page ``0xFF02``): the command channel. Commands are
  8-byte *feature* reports with report id 0.
* the **mouse interface** (usage page ``0xFF01``, usage 1 -- interface 0 on the
  dongle, interface 1 on the wired mouse): the status channel. The mouse
  answers with 8-byte *input* reports numbered ``0x06``.

Request
=======

The vendor software sends two commands on interface 2::

    80 00 00 00 00 00 00 7f     "are you there" -- answered on interface 2's
                                own input endpoint with 80 01 01 00 24 01 ...
                                and with a 06 55 .. status line on the mouse
                                interface. Repeated until the mouse answers.
    80 ff 00 00 00 00 00 80     "dump status" -- answered with a burst of 06 xx
                                reports on the mouse interface, the battery
                                among them.

Whether ``80 ff`` works without the ping in front of it is not known, so the
driver sends both, back to back, exactly like the capture.

Reply
=====

The battery line of the burst::

    06 56 PP CC 00 00 00 00
    |  |  |  `-- 1 on the cable, 0 on the 2.4G link
    |  |  `----- charge percent (0x55 = 85)
    |  `-------- status sub-type: 0x56 = battery
    `----------- report id

The other sub-types seen in the burst (``0x55``, ``0x81``, ``0x87``) are link,
DPI and polling-rate lines; ignored. The mouse also *pushes* a ``06 56`` line
on its own when the cable state changes, but never periodically -- the vendor
software does not poll at all -- so this driver always asks.

Wired
=====

On the cable the mouse enumerates as its own device (PID ``0x3144``, "Wired
Gaming Mouse") with the same three-interface layout, and pushes ``06 56`` on
connect. The dongle keeps reporting the same mouse meanwhile, so with the
dongle plugged in the wireless PID wins (see :func:`~mouse_tray.drivers.bus.devices_for`).
"""

from __future__ import annotations

import logging
import time
from contextlib import suppress
from typing import ClassVar

import hid  # hidapi -- the single core transport dependency

from ...battery import BatteryStatus
from ..bus import devices_for
from ..driver import MouseModel, register
from ..hid import HidDriver

log = logging.getLogger(__name__)

_VID = 0x1956

# Status channel: the vendor collection on the mouse interface.
_STATUS_USAGE_PAGE = 0xFF01
_STATUS_USAGE = 0x0001
# Command channel: the vendor collection on interface 2.
_COMMAND_USAGE_PAGE = 0xFF02
_COMMAND_USAGE = 0x0001

# Feature report id 0 + 8 command bytes.
_PING = [0x00, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x7F]
_QUERY = [0x00, 0x80, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80]
#: The capture shows the query ~13 ms after the ping's reply.
_PING_GAP = 0.02

_REPORT_ID = 0x06
_SUBTYPE_BATTERY = 0x56
_PERCENT_BYTE = 2
_CABLE_BYTE = 3
_REPORT_LEN = 8
#: The burst lands within ~70 ms of the query; leave generous headroom.
_READ_TIMEOUT = 1.0


def _model(name: str, pid_wireless: int, pid_wired: int) -> MouseModel:
    return MouseModel(name, _VID, pid_wireless, pid_wired, _STATUS_USAGE_PAGE, _STATUS_USAGE)


@register
class BloodyDriver(HidDriver):
    vendor = "A4Tech Bloody"
    note = "Only the 8K dongle firmware (VID 0x1956); classic Bloody mice speak a different protocol."
    models: ClassVar[list[MouseModel]] = [
        # 2.4G "Mouse 8K dongle" 0x3069, direct cable "Wired Gaming Mouse" 0x3144.
        _model("Bloody SG5 Pro", 0x3069, 0x3144),
    ]

    def _command_path(self) -> bytes | None:
        """OS path of the command collection (interface 2, usage page 0xFF02)."""
        for device in devices_for(self.model):
            if device["usage_page"] == _COMMAND_USAGE_PAGE and device["usage"] == _COMMAND_USAGE:
                return device["path"]
        return None

    def read_status(self) -> BatteryStatus:
        report = self._read_battery_report()
        if report is None:
            return self._no_reply()
        return self._decode(report)

    def _read_battery_report(self) -> list[int] | None:
        """Ask for status and return the raw ``06 56`` line, or ``None``."""
        status_path = self._device_path()
        command_path = self._command_path()
        if status_path is None or command_path is None:
            return None
        # Open the status channel *before* asking, so the reply is queued for
        # this handle rather than dropped on the floor.
        status = hid.device()
        try:
            status.open_path(status_path)
            if not self._send_query(command_path):
                return None
            return self._wait_for_battery(status)
        except OSError as exc:
            log.warning("%s HID read failed: %s", self.name, exc)
            return None
        finally:
            with suppress(Exception):
                status.close()

    def _no_reply(self) -> BatteryStatus:
        if self._connected_wired():
            # Cable only: charging for sure, level unknown until it answers.
            log.info("%s wired, no battery reply: charging, level not reported", self.name)
            return BatteryStatus(present=True, percent=None, charging=True)
        log.info("%s no battery reply within %.1fs", self.name, _READ_TIMEOUT)
        return BatteryStatus.absent()

    def _decode(self, report: list[int]) -> BatteryStatus:
        percent = report[_PERCENT_BYTE]
        cable = bool(report[_CABLE_BYTE])
        if not 0 <= percent <= 100:
            log.warning("%s implausible percent %s", self.name, percent)
            return BatteryStatus.absent()
        log.info("%s battery=%s%% cable=%s", self.name, percent, cable)
        return BatteryStatus(
            present=True,
            percent=percent,
            charging=cable and percent < 100,
            full=cable and percent >= 100,
            asleep=False,
        )

    def _send_query(self, command_path: bytes) -> bool:
        """Send ping + status query on the command channel. False if unreachable."""
        command = hid.device()
        try:
            command.open_path(command_path)
            log.debug("%s sending ping: %s", self.name, _PING)
            command.send_feature_report(_PING)
            time.sleep(_PING_GAP)
            log.debug("%s sending query: %s", self.name, _QUERY)
            command.send_feature_report(_QUERY)
            return True
        except OSError as exc:
            log.warning("%s HID command failed: %s", self.name, exc)
            return False
        finally:
            with suppress(Exception):
                command.close()

    def _wait_for_battery(self, status: hid.device) -> list[int] | None:
        """Read the status channel until the ``06 56`` line arrives, or time out."""
        deadline = time.monotonic() + _READ_TIMEOUT
        while True:
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                return None
            data = status.read(_REPORT_LEN, timeout_ms=remaining_ms)
            if not data:
                continue
            log.debug("%s status report: %s", self.name, data)
            if len(data) > _CABLE_BYTE and data[0] == _REPORT_ID and data[1] == _SUBTYPE_BATTERY:
                return data
