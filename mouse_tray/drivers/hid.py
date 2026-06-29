"""Single-transaction HID transport.

Base for the common case: one request, one reply, fixed offsets -- driven over
``hidapi`` with either plain interrupt write/read or feature reports. Most
vendors fit this, including Razer (whose protocol, once driven through raw
``pyusb`` control transfers, is really a HID SET_REPORT/GET_REPORT on feature
report id 0 -- see ``razer.py``). A vendor driver subclasses :class:`HidDriver`
and implements only :meth:`read_status`, using :meth:`_transact` to talk to the
device: declare a model table, build a request, parse the reply.

Multi-step protocols (handshake, feature discovery, device-index routing) do not
fit this shape; they subclass :class:`~mouse_tray.drivers.hidpp.HidppDriver`
instead. Both bases return the same :class:`~mouse_tray.battery.BatteryStatus`,
so the rest of the app is unaffected by which one a driver uses.
"""

from __future__ import annotations

import logging
import time

import hid  # hidapi -- the single core transport dependency

from .driver import MouseDriver

log = logging.getLogger(__name__)


class HidDriver(MouseDriver):
    """Base for all mice, spoken to over HID via ``hidapi``.

    Detection and device-path resolution are generic and live here; subclasses
    implement only :meth:`read_status`.
    """

    @classmethod
    def detect(cls) -> "HidDriver | None":
        for model in cls.models:
            if hid.enumerate(model.vid, model.pid_wireless) or hid.enumerate(model.vid, model.pid_wired):
                return cls(model)
        return None

    def _connected_wired(self) -> bool:
        """True when the device is reachable only on its wired PID.

        Some protocols build a different request depending on the link (the
        wired and wireless dongles enumerate under distinct PIDs). When a model
        uses the same PID for both, the wireless PID always matches first and
        this returns ``False`` -- drivers that don't care simply never call it.
        """
        model = self.model
        if hid.enumerate(model.vid, model.pid_wireless):
            return False
        return bool(hid.enumerate(model.vid, model.pid_wired))

    def _device_path(self) -> bytes | None:
        """Resolve the OS device path for the battery HID collection.

        Prefers the wireless PID, falls back to wired, then keeps only the
        collection matching whichever of ``usage_page`` / ``usage`` /
        ``interface`` the model specifies (a mouse exposes several HID
        collections and the battery lives on a specific one).
        """
        model = self.model
        devices = hid.enumerate(model.vid, model.pid_wireless) or hid.enumerate(model.vid, model.pid_wired)
        if not devices:
            return None
        for device in devices:
            if model.usage_page is not None and device["usage_page"] != model.usage_page:
                continue
            if model.usage is not None and device["usage"] != model.usage:
                continue
            if model.interface is not None and device["interface_number"] != model.interface:
                continue
            return device["path"]
        return None

    def _transact(
        self,
        report: list[int],
        read_length: int,
        *,
        feature: bool = False,
        delay: float = 0.1,
    ) -> list[int] | None:
        """Send ``report`` and return the reply, or ``None`` if unreachable.

        ``feature=True`` uses HID feature reports (send/get); otherwise plain
        interrupt write/read. ``report[0]`` is the report ID. Never raises for
        I/O errors -- returns ``None`` so the caller can show "no mouse".
        """
        path = self._device_path()
        if path is None:
            return None
        device = hid.device()
        try:
            device.open_path(path)
            log.debug("%s sending report: %s", self.name, report)
            if feature:
                device.send_feature_report(report)
                time.sleep(delay)
                res = device.get_feature_report(report[0], read_length)
            else:
                device.write(report)
                time.sleep(delay)
                res = device.read(read_length)
            log.debug("%s received report: %s", self.name, res)
            return res
        except OSError as exc:
            log.warning("%s HID transaction failed: %s", self.name, exc)
            return None
        finally:
            try:
                device.close()
            except Exception:
                pass
