# Mouse Tray Charge

**English** | [Русский](README.ru.md)

A **universal** wireless-mouse battery indicator for the Windows system tray.
One app, many vendors — adding a new manufacturer or model is a single small
file, no changes to the UI or polling code.

![Screenshot](images/screenshot.png)

## Supported models

- **ATK / VXE / VGN:** ATK F1 Ultimate, ATK A9 Ultimate, ATK Zero, VXE MAD R,
  VXE MAD R Major Plus, VXE R1 Pro Max, VXE R1 SE+, VGN F1 Pro
- **Zaopin:** Z2 Mini
- **Scyrox:** V8
- **Dareu:** A950 Air
- **G-Wolves:** Lycan
- **MCHOSE:** L7 Pro
- **Ninjutso:** Sora V2
- **Razer:** Viper V2 Pro, Viper V3 Pro, DeathAdder V3 Pro, DeathAdder V4 Pro,
  Basilisk V3 Pro, Basilisk V3 Pro 35K, Basilisk Ultimate, Cobra Pro, Naga Pro,
  Naga V2 Pro, Lancehead Wireless, Pro Click V2
- **Lamzu:** Maya X, Inca
- **Attack Shark:** X3
- **Logitech:** any Lightspeed/Bolt/Unifying mouse with the UnifiedBattery
  feature, via a receiver **or connected directly by USB cable / Bluetooth**
  (model name auto-detected over HID++) — verified on PRO X2 SUPERSTRIKE
  (receiver and wired)

> The Razer driver was ported from a `pyusb` implementation to `hidapi` for
> uniformity; the report offset / HID collection may need confirmation on
> hardware (see the note in [`drivers/razer.py`](mouse_tray/drivers/razer.py)).
> Only **Viper V2 Pro** is verified on real hardware — the rest of the list was
> taken from [OpenRazer](https://github.com/openrazer/openrazer)'s device
> database. These are the models whose battery query uses transaction id `0x1F`
> (what the driver hardcodes), so they need no code change; older Razer families
> that use `0x3F` / `0xFF` are not covered yet. If one of the unverified models
> reads wrong, confirm the response offset / `usage_page` on hardware.

## Run from source

The project is managed with [uv](https://docs.astral.sh/uv/) — a fast Python
package/project manager that handles the virtualenv and dependencies for you
(no manual `pip install` or `venv`). Install it once:

```sh
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# or via winget / pipx
winget install astral-sh.uv
```

Then, from the project root:

```sh
uv sync                      # create .venv and install dependencies from uv.lock
uv run python main.py        # or:  uv run python -m mouse_tray
```

`uv run` auto-syncs first, so `uv run python main.py` alone is enough after a
fresh clone. `uv.lock` pins exact versions for reproducible installs.

## Build a standalone .exe

```sh
uv run --extra build python tools/make_release.py
# -> dist/mouse_tray/
```

The resulting folder is about 37 MB. Drivers are collected as a whole
(`--collect-submodules`), so a new driver ships without touching the script.
Modules the app cannot reach — Pillow's codecs, `ssl` with its libcrypto/libssl,
`wx.html` and the like — are dropped through the `EXCLUDES` list in
[`tools/make_release.py`](tools/make_release.py), which also records what must
stay. A new dependency is reason to revisit that list.

## Multiple mice

Every supported mouse that is plugged in is detected, and the tray shows one of
them. By default that is the first one that actually answers — a receiver whose
mouse is switched off is skipped rather than shown as "no mouse" — and it stays
the active one until it disappears.

When two or more are connected, the tray menu grows a mouse list: pick **Auto**
for that behaviour, or pin a specific mouse. A pin is strict — if the pinned
mouse is unplugged the tray shows `-` and names it in the tooltip, it never
quietly switches to another mouse. The choice is saved to the registry and
survives restarts. Only the shown mouse is polled, so the others cost nothing.

The "time since last full charge" timer is kept per mouse, so switching keeps
each one's own timer.

## Settings

Right-click the tray icon and choose **Settings…** to change the poll interval,
font, font color, charge-level coloring, the indicator style and debug logging
from a dialog. Changes apply immediately and are saved to the registry
(`HKCU\SOFTWARE\Mouse_Tray\Settings`), so they survive restarts; **Reset to
defaults** restores the code defaults.

With **Color by charge level** enabled, the battery-percent indicator is colored
by charge: the font color above 50%, and two extra pickers appear next to it for
the low bands — **≤ 50%** (yellow by default) and **≤ 20%** (red by default).

With **Show battery icon** enabled, the charge level is drawn as a battery
filled to that percent instead of as digits, and the exact number moves to the
hover tooltip (which also shows the mouse name and time since the last full
charge). "No mouse", sleep and unknown-level states stay textual either way.

For the full set of fields (including those not exposed in the dialog), edit
[`mouse_tray/config.py`](mouse_tray/config.py):

| Field              | Meaning                                            |
| ------------------ | -------------------------------------------------- |
| `poll_rate`        | Seconds between reads while awake & discharging    |
| `fast_poll_rate`   | Seconds between reads while charging/asleep/absent |
| `foreground_color` | RGB color of the indicator digits (and the top band) |
| `dynamic_color`    | Color the percent by charge level                  |
| `mid_color`        | RGB color of the ≤ 50% band (yellow)               |
| `low_color`        | RGB color of the ≤ 20% band (red)                  |
| `battery_icon`     | Draw a filled battery instead of the percent digits |
| `background_color` | RGBA icon background (transparent by default)      |
| `font`             | Font file for the digits (`consola.ttf`)           |
| `app_name`         | Storage key: registry subkey + log directory name  |
| `display_name`     | Human-facing name (tray tooltip, toasts, settings) |
| `debug`            | Verbose DEBUG logging (raw HID reports)            |

## About

**About…** in the tray menu opens a dialog with the version and build commit, a
link to the project page, and the table of every device the running build
supports — model, USB id (`VID:PID`, plus the wired PID when the cable
enumerates its own) and the protocol behind it, sortable by any column header.
The table is generated from the driver registry, so it always matches the
drivers actually bundled — a build with a new driver lists its models without
any edit here.

## Logging

Logs go to a rotating file at `%LOCALAPPDATA%\Mouse_Tray\app.log` (1 MB × 3
backups), plus the console when one is available — under the windowed `.exe`
build there is no console, so the file is the place to look. Enable verbose
DEBUG output (raw HID reports) with the `debug` config flag or by setting the
`MOUSE_TRAY_DEBUG=1` environment variable. Configured in
[`mouse_tray/logging_setup.py`](mouse_tray/logging_setup.py).

## Adding a new mouse

**Same vendor, new model** — add a row to that driver's `models` list:

```python
# drivers/chipset/nordic52.py
_model("VXE NewModel", 0x373B, 0x1234, 0x5678),
```

> The `nordic52` driver covers the shared **Compx/Nordic 52840 chipset**, not just
> ATK/VXE/VGN. Many off-brand mice ride the same silicon (the receiver enumerates
> as "Compx") and work by adding a single `_model` row with their VID/PID — no new
> driver. The Zaopin Z2 Mini, Scyrox V8, Dareu A950 Air and G-Wolves Lycan were added exactly this
> way; if a percent reads at byte 6 of the report-8 reply, it's this protocol. The newer
> Nordic 54L15 silicon (ATK Zero) speaks a different 64-byte protocol and lives in
> `nordic54`.

**New vendor** — create `drivers/vendor/<vendor>.py` (or `drivers/chipset/<chip>.py`
if the silicon is shared across brands), subclass `HidDriver`, list the models and
implement `read_status()`:

```python
from ...battery import BatteryStatus
from ..driver import MouseModel, register
from ..hid import HidDriver

@register
class AcmeDriver(HidDriver):
    vendor = "Acme"
    models = [MouseModel("Acme X1", 0xABCD, 0x0001, 0x0002, usage_page=0xFF00)]

    def read_status(self) -> BatteryStatus:
        res = self._transact([0x00, ...], read_length=32, feature=True)
        if res is None:
            return BatteryStatus.absent()
        return BatteryStatus(present=True, percent=res[5], charging=bool(res[6]))
```

Then add `"vendor.acme"` to `_DRIVER_MODULES` in
[`drivers/__init__.py`](mouse_tray/drivers/__init__.py). Done — detection, the
tray UI and packaging pick it up automatically.

> Most mice fit `HidDriver` (one request, fixed offsets). Multi-step protocols
> like Logitech HID++ instead subclass `HidppDriver` — but they return the same
> `BatteryStatus`, so the UI/registry are unchanged either way. That the two
> very different transports plug into one `MouseDriver` contract is the whole
> point of the design.

## How it works

Every mouse, regardless of vendor, is reduced to one normalized
[`BatteryStatus`](mouse_tray/battery.py) — `present / percent / charging / full
/ asleep`. A single state machine in [`ui/app.py`](mouse_tray/ui/app.py) renders
that into the tray icon (digits, charging animation, full-charge notification,
"time since last full charge" tooltip). Vendor code only does two things:
**detect the device** and **parse its battery report**.

```
hid.enumerate (cached 0.5 s)  →  detect_all_drivers()  →  driver.read_status()
         bus.py                      driver.py                → BatteryStatus
                                                                     ↓
                                                       _apply_status() → tray icon
```

### The bus

[`drivers/bus.py`](mouse_tray/drivers/bus.py) enumerates the whole HID bus once
and caches the snapshot for 0.5 s. Detection walks every model of every driver —
dozens of VID/PID pairs — so matching happens in memory instead of rescanning the
bus once per model. The TTL sits well below the fastest poll rate, so a
hot-plugged mouse still lands within one tick.

### Drivers

The [`MouseDriver`](mouse_tray/drivers/driver.py) contract is two methods —
`detect_all()` and `read_status()` — plus a stable `key` (driver class + VID/PID)
that identifies the mouse across re-plugs. Classes register themselves with the
`@register` decorator; the module list in
[`drivers/__init__.py`](mouse_tray/drivers/__init__.py) is both the import list
and the detection probe order. Neither method may raise for an absent device or
an I/O hiccup: an empty list and `BatteryStatus.absent()` are the answers there.

Two transport bases sit under that contract:
[`HidDriver`](mouse_tray/drivers/hid.py) for the common one-request/one-reply
case (a subclass writes only `read_status()` on top of `_transact()`), and
[`HidppDriver`](mouse_tray/drivers/hidpp.py) for multi-step HID++ 2.0 (feature
discovery, device-index routing). The two share no code, which is precisely why
the real abstraction is `MouseDriver` rather than either base.

### Polling

A daemon thread runs the poll loop. Detection re-runs on every tick — it costs
one cached bus enumeration — so a mouse plugged in later appears on its own,
without a restart. Driver objects are reused across sweeps, keyed by `key`,
because they cache per-device state (an HID++ driver, for instance, discovers its
device index and feature indices on the first read). The interval is `poll_rate`
(60 s by default) while the mouse is awake and discharging, and `fast_poll_rate`
(1 s) in the transient states — charging, asleep, or no mouse — where a quick
reaction matters. The worker touches widgets only through `wx.CallAfter`, so all
UI work stays on the main thread.

### Which mouse is shown

All connected mice are detected; only one is read. With no pin the worker takes
the first that reports `present` and sticks to it, so a connected receiver whose
mouse is switched off never shadows a working one. A pin chosen from the tray
menu is strict — an unplugged pinned mouse yields `-` rather than a silent switch
to another device. The pin lives in the registry and is only ever *read* by the
worker, which keeps the driver objects single-threaded.

### Rendering

[`_apply_status`](mouse_tray/ui/app.py) is a flat, ordered chain of guard
clauses, one per state: no mouse → `-`; charging → the fill animation (a
main-thread timer); full → a green icon, a toast and a fresh full-charge
timestamp; asleep → `Zzz`; present but with no readable level → `?`; otherwise
the percent, as digits or as a filled battery.
[`ui/icons.py`](mouse_tray/ui/icons.py) draws the digits with PIL and rasterizes
the battery from an SVG template through `wx.svg` (NanoSVG, bundled with
wxPython), both keeping a real alpha channel all the way to the icon.

### Storage

[`storage.py`](mouse_tray/storage.py) keeps the settings, the pinned mouse and
the per-mouse "last full charge" timestamp under `HKCU\SOFTWARE\Mouse_Tray\`.
That timestamp is what the tooltip's elapsed-time line is computed from.

One architectural rule holds the whole thing together: `ui/app.py` never imports
a driver module — only `detect_all_drivers()` and the `MouseDriver` contract.

### Layout

```
mouse_tray/
  battery.py            BatteryStatus — the universal status model
  config.py             settings (poll rate, colors, font)
  resources.py          PyInstaller-safe resource paths
  storage.py            "last full charge" timestamp, settings, pinned mouse
  drivers/
    driver.py           MouseModel, MouseDriver, @register + registry
    bus.py              one cached hid.enumerate snapshot per detection sweep
    hid.py              HidDriver — shared single-transaction hidapi base
    hidpp.py            HidppDriver — multi-step HID++ base (Logitech)
    __init__.py         auto-imports drivers -> registry is populated
    chipset/            shared-silicon protocols (named by chipset)
      nordic52.py       Compx/Nordic 52840 (HID write/read, report 8, 17-byte)
      nordic54.py       Compx/Nordic 54L15 (HID write/read, report 8, 64-byte)
      realtek.py        MCHOSE / RealTek  (pushed report 0x13, XOR 0xFF)
    vendor/             brand-specific protocols
      ninjutso.py       Ninjutso Sora     (HID feature report 5)
      razer.py          Razer             (HID feature report 0, OpenRazer)
      lamzu.py          Lamzu             (HID feature report, iface 2)
      logitech.py       Logitech          (HID++ 2.0 via receiver)
      attackshark.py    Attack Shark      (pushed HID input report 3)
  ui/
    icons.py            tray icon rendering (PIL digits + SVG battery)
    tray.py             TaskBarIcon wrapper
    settings.py         settings dialog
    about.py            about dialog (model table from the registry)
    app.py              wx app + the single state machine
  icons/                bundled .ico assets
```

## Protocol sources & credits

Each driver's protocol was ported from (or verified against) these projects:

- **ATK / VXE / VGN** — [Fan4Metal/ATK_tray](https://github.com/Fan4Metal/ATK_tray)
- **Ninjutso** — [Fan4Metal/Sora_tray](https://github.com/Fan4Metal/Sora_tray)
- **Razer** — [Fan4Metal/razer_tray](https://github.com/Fan4Metal/razer_tray),
  based on [OpenRazer](https://github.com/openrazer/openrazer) and
  [rsmith-nl/scripts](https://github.com/rsmith-nl/scripts)
- **Lamzu** — [Sheroune/lamzu-battery-monitory](https://github.com/Sheroune/lamzu-battery-monitory)
- **Logitech (HID++ 2.0)** — [l2-/LogitechBatteryIndicator](https://github.com/l2-/LogitechBatteryIndicator),
  with protocol details from [Solaar](https://github.com/pwr-Solaar/Solaar) and
  [libratbag](https://github.com/libratbag/libratbag)
- **Attack Shark** — [HarukaYamamoto0/attack-shark-x11-driver](https://github.com/HarukaYamamoto0/attack-shark-x11-driver),
  whose notes on the shared messaging protocol were contributed in
  [issue #1](https://github.com/Fan4Metal/mouse_tray/issues/1)
