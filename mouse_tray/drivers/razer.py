"""Razer wireless mice (HID feature-report protocol).

Razer's battery query is the classic OpenRazer report: a 90-byte payload whose
header selects command class 0x02 / id 0x07, terminated by an XOR checksum.
Older tools sent it through raw ``pyusb`` control transfers, but those are
exactly HID SET_REPORT / GET_REPORT calls on *feature report id 0*, so we drive
them with ``hidapi`` like every other driver -- no pyusb / libusb needed.

The battery level comes back as 0-255 and is scaled to a percent.

NOTE: report byte offsets and the target HID collection were derived from the
pyusb implementation (https://github.com/Fan4Metal/razer_tray). If a Razer model reads
wrong, confirm ``usage_page``/``usage`` and the response offset on hardware --
that is the only vendor-specific part.
"""

from __future__ import annotations

import logging

from ..battery import BatteryStatus
from .driver import MouseModel, register
from .hid import HidDriver

log = logging.getLogger(__name__)

_TRANSACTION_ID = 0x1F


def _battery_report() -> list[int]:
    """Build the 90-byte battery request, prefixed with feature report id 0."""
    # status, transaction_id, remaining(2), protocol_type, command_class,
    # command_id, data_size  -- then 80 data bytes, an XOR checksum and a pad.
    header = [0x00, _TRANSACTION_ID, 0x00, 0x00, 0x00, 0x02, 0x07, 0x80]
    crc = 0
    for byte in header[2:]:
        crc ^= byte
    payload = header + [0] * 80 + [crc, 0]
    return [0x00] + payload  # leading 0x00 = HID feature report id


@register
class RazerDriver(HidDriver):
    vendor = "Razer"
    models = [
        # usage_page/usage left unset: match the first reachable collection.
        MouseModel("Razer Viper V2 Pro", 0x1532, 0x00A6, 0x00A5),
    ]

    def read_status(self) -> BatteryStatus:
        report = _battery_report()
        # Wireless needs a longer settle before the reply is ready.
        res = self._transact(report, len(report), feature=True, delay=0.34)
        if res is None:
            return BatteryStatus.absent()

        # +1 vs the pyusb offset (9) because hidapi prepends the report id.
        raw = res[10] if len(res) > 10 else 0
        percent = round(raw / 255 * 100)
        log.info("%s raw=%s percent=%s", self.name, raw, percent)
        return BatteryStatus(
            present=True,
            percent=percent,
            charging=False,  # this query does not expose charge state
            full=False,
            asleep=percent == 0,  # sleeping mice report 0
        )
