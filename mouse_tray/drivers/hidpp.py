"""HID++ transport base (Logitech).

Unlike the other vendors -- one fixed feature report, fixed offsets -- Logitech
speaks the multi-step HID++ 2.0 protocol through a receiver:

* Two report formats on interface 2 / usage page 0xFF00: *short* (report id
  0x10, 7 bytes) and *long* (0x11, 20 bytes). On Windows these are two separate
  HID collections: a short request is written to the usage-0x01 handle, a long
  request to the usage-0x02 handle, and replies may arrive on *either* -- so we
  open both and read both.
* Each request carries a device index (1..6 for a receiver's paired devices,
  0xFF for the receiver itself) and a feature *index*, which is discovered at
  runtime from the feature *id* via the root feature (index 0x00).

This base implements that machinery; concrete drivers implement
:meth:`read_status`. It deliberately subclasses :class:`MouseDriver` directly
(not :class:`HidDriver`) because it shares none of the single-transaction model
-- the proof that the top-level driver contract is the real abstraction.

Verified against a Logitech Lightspeed receiver (PID 0xC54D).
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager

import hid

from .driver import MouseDriver, MouseModel

log = logging.getLogger(__name__)

_SHORT_REPORT = 0x10
_LONG_REPORT = 0x11
_SOFTWARE_ID = 0x01  # nonzero tag so we recognize our own replies
_ROOT_FEATURE = 0x00  # feature index 0 is always the root feature
_ERROR_MARKER = 0xFF  # res[2] == 0xFF marks a HID++ 2.0 error reply
_PING_MARKER = 0xAA


class HidppDriver(MouseDriver):
    """Base for Logitech mice spoken to over HID++ via a receiver."""

    #: Paired-device index on the receiver. Auto-resolved on first read.
    default_device_index: int = 0x01

    def __init__(self, model: MouseModel):
        super().__init__(model)
        self._device_index: int | None = None
        self._name: str | None = None
        self._feature_cache: dict[int, int | None] = {}

    @property
    def name(self) -> str:
        return self._name or self.model.name

    # --- detection / connection --------------------------------------------

    @classmethod
    def _collections(cls, model: MouseModel) -> tuple[bytes, bytes] | None:
        """Return (short_path, long_path) for the HID++ collections, or None."""
        short_path = long_path = None
        pids = {model.pid_wireless, model.pid_wired}
        devices = []
        for pid in pids:
            devices += hid.enumerate(model.vid, pid)
        for d in devices:
            if d["interface_number"] != model.interface or d["usage_page"] != model.usage_page:
                continue
            if d["usage"] == 0x01:
                short_path = d["path"]
            elif d["usage"] == 0x02:
                long_path = d["path"]
        if short_path and long_path:
            return short_path, long_path
        return None

    @classmethod
    def detect(cls) -> "HidppDriver | None":
        for model in cls.models:
            if cls._collections(model):
                return cls(model)
        return None

    @contextmanager
    def _connection(self):
        """Open both HID++ collections; yield (short, long) handles or None."""
        paths = self._collections(self.model)
        if paths is None:
            yield None
            return
        short_path, long_path = paths
        short_h = hid.device()
        long_h = hid.device()
        try:
            short_h.open_path(short_path)
            long_h.open_path(long_path)
            short_h.set_nonblocking(1)
            long_h.set_nonblocking(1)
        except OSError as exc:
            log.warning("%s could not open HID++ collections: %s", self.model.name, exc)
            short_h.close()
            long_h.close()
            yield None
            return
        try:
            yield short_h, long_h
        finally:
            short_h.close()
            long_h.close()

    # --- HID++ primitives ---------------------------------------------------

    def _call(self, conn, feature_index, function_id, *params, device_index=None, timeout=0.5):
        """Run one HID++ function call; return the reply report or ``None``.

        Writes a short request and reads replies from both handles, matching on
        device index, feature index and the echoed address. ``None`` on error
        or timeout.
        """
        short_h, long_h = conn
        dev = self.default_device_index if device_index is None else device_index
        address = (function_id << 4) | _SOFTWARE_ID
        p = (list(params) + [0, 0, 0])[:3]
        request = [_SHORT_REPORT, dev, feature_index, address, *p]
        try:
            short_h.write(request)
        except OSError as exc:
            log.warning("%s HID++ write failed: %s", self.model.name, exc)
            return None

        deadline = time.time() + timeout
        while time.time() < deadline:
            for handle in (short_h, long_h):
                try:
                    res = handle.read(20)
                except OSError as exc:
                    # The receiver was unplugged mid-read (hot-unplug) -- bail out
                    # now; next poll's _connection sees no collections -> absent.
                    log.warning("%s HID++ read failed: %s", self.model.name, exc)
                    return None
                if not res or res[1] != dev:
                    continue
                if res[2] == _ERROR_MARKER and res[3] == feature_index:
                    return None  # device returned an error for this feature
                if res[2] == feature_index and res[3] == address:
                    return res
            time.sleep(0.01)
        return None

    def _feature_index(self, conn, feature_id, device_index=None) -> int | None:
        """Resolve a feature *id* to its runtime *index* (cached)."""
        if feature_id in self._feature_cache:
            return self._feature_cache[feature_id]
        res = self._call(
            conn, _ROOT_FEATURE, 0x00,
            (feature_id >> 8) & 0xFF, feature_id & 0xFF,
            device_index=device_index,
        )
        index = res[4] if res else None
        index = index or None  # index 0 means "not supported"
        self._feature_cache[feature_id] = index
        return index

    def _resolve_device_index(self, conn) -> int | None:
        """Find which paired device index answers (ping root feature)."""
        for dev in range(1, 7):
            res = self._call(conn, _ROOT_FEATURE, 0x01, 0, 0, _PING_MARKER, device_index=dev)
            if res and len(res) > 6 and res[6] == _PING_MARKER:
                log.info("%s responding at device index %d", self.model.name, dev)
                return dev
        return None

    def _read_device_name(self, conn, device_index) -> str | None:
        """Best-effort device name via feature 0x0005 (GetDeviceName)."""
        idx = self._feature_index(conn, 0x0005, device_index=device_index)
        if not idx:
            return None
        count_res = self._call(conn, idx, 0x00, device_index=device_index)
        if not count_res:
            return None
        count = count_res[4]
        chars: list[int] = []
        while len(chars) < count:
            res = self._call(conn, idx, 0x01, len(chars), device_index=device_index)
            if not res:
                break
            chunk = res[4:20]
            chars += [c for c in chunk if c != 0]
            if all(c == 0 for c in chunk):
                break
        name = bytes(chars[:count]).decode("ascii", errors="ignore").strip()
        return name or None
