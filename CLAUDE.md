# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A **universal** wireless-mouse battery indicator for the Windows system tray. The
whole design turns on one idea: every mouse — whatever the vendor or transport —
is reduced to a single normalized [`BatteryStatus`](mouse_tray/battery.py), and a
single state machine in [`ui/app.py`](mouse_tray/ui/app.py) renders that into the
tray icon. Vendor code does exactly two things: **detect the device** and **parse
its battery report**. Nothing else in the app knows which mouse is connected.

Windows-only at runtime (wxPython tray, `hidapi`, Windows registry for storage).

## Commands

```sh
uv sync                                          # install deps into .venv
uv run python main.py                            # run from source (or: uv run python -m mouse_tray)
uv run --extra build python tools/make_release.py   # build dist/mouse_tray/ (.exe via PyInstaller)
MOUSE_TRAY_DEBUG=1 uv run python main.py          # verbose logging: raw HID reports
```

There is **no test suite, linter, or formatter configured** — no pytest, ruff, or
CI. "Testing" a driver means running against real hardware and reading
`%LOCALAPPDATA%\Mouse_Tray\app.log` (rotating, 1 MB × 3; set `debug` / the env var
above for raw report bytes). Protocols are reverse-engineered from USB captures
kept under `examples/`.

**`examples/` is gitignored and local-only — it is not part of the repository.**
Do not reference anything under `examples/` in committed docs (README, CLAUDE.md,
code comments): those paths won't exist for anyone else. Use it as a local
scratch/reference source only.

## Architecture

The layering is deliberately strict — respect it when adding code:

- [`battery.py`](mouse_tray/battery.py) — `BatteryStatus(present/percent/charging/full/asleep)`.
  The one type every driver returns and the UI consumes. `BatteryStatus.absent()`
  means "no mouse".
- [`drivers/driver.py`](mouse_tray/drivers/driver.py) — the `MouseDriver` ABC
  (`detect()` + `read_status()`), the `MouseModel` row (VID/PID + optional HID
  disambiguators), and the `@register` decorator + registry (`detect_driver()`
  probes drivers in registration order, returns the first connected one).
- [`drivers/hid.py`](mouse_tray/drivers/hid.py) — `HidDriver`: the common
  single-transaction base (one request → one reply, fixed offsets) over `hidapi`.
  Subclasses implement only `read_status()` and call `self._transact(...)`.
- [`drivers/hidpp.py`](mouse_tray/drivers/hidpp.py) — `HidppDriver`: multi-step
  HID++ 2.0 base for Logitech (feature discovery, device-index routing, two
  report formats). Subclasses `MouseDriver` **directly**, sharing none of the
  single-transaction model — the proof that `MouseDriver`, not `HidDriver`, is the
  real abstraction.
- [`ui/app.py`](mouse_tray/ui/app.py) — the wx app, the background polling thread,
  and the single `_apply_status` state machine. This module **never imports a
  driver**, only `detect_driver()`.

### Two things to know about the runtime

- **Threading:** polling runs on a daemon worker thread; it touches widgets only
  via `wx.CallAfter`. All wx/UI work stays on the main thread. Don't call UI code
  from `read_status()` or the poll loop.
- **Re-detection:** when `read_status()` returns a non-present status, the poll
  loop drops the driver and re-detects next tick — this is how hot-unplug and
  model-switching are handled. So `detect()`/`read_status()` **must never raise**
  for an absent device or I/O hiccup; return `None` / `BatteryStatus.absent()`.

## Adding mouse support

Drivers live in two subpackages: `drivers/chipset/` for shared-silicon protocols
(named after the chipset, e.g. `nordic52`, `nordic54`, `realtek` — one protocol
spanning every brand that rebrands that chip) and `drivers/vendor/` for
brand-specific protocols. Pick by what the protocol actually keys on, not the
brand on the box.

- **Same protocol, new model** — add one `MouseModel` row to that driver's
  `models` list (VID, wireless PID, wired PID, plus `usage_page`/`usage`/
  `interface` only as needed to select the right HID collection). No new code.
  Many off-brand mice ride the Compx/Nordic 52840 silicon and drop straight into
  `chipset/nordic52` this way.
- **New protocol** — add `drivers/<subpkg>/<name>.py`, subclass `HidDriver` (or
  `HidppDriver` for multi-step), declare `vendor` + `models`, implement
  `read_status()`, decorate the class with `@register`, **and add the module to
  `_DRIVER_MODULES` in [`drivers/__init__.py`](mouse_tray/drivers/__init__.py)**
  (that list is both the import list and the detection probe order). Detection,
  the tray UI, and packaging then pick it up automatically.

PyInstaller can't see the dynamically-imported drivers statically, so the build
uses `--collect-submodules mouse_tray.drivers` — new drivers are bundled for free,
no `.spec` edit needed.

## Storage & config

- User settings and per-mouse "last full charge" timestamps live in the Windows
  registry under `HKCU\SOFTWARE\Mouse_Tray\` (see
  [`storage.py`](mouse_tray/storage.py)). Settings apply immediately and persist.
- [`config.py`](mouse_tray/config.py) holds `Config` (poll rates, colors, font,
  debug) and `VERSION` (the single source of the runtime version). Note the split:
  **`app_name`** is the stable storage/identity key (registry subkey + log dir —
  do not change casually) while **`display_name`** is the human-facing label
  (tooltip, toasts, settings title) and is free to change.
