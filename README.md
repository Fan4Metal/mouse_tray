# Mouse Tray Charge

**English** | [Русский](README.ru.md)

A **universal** wireless-mouse battery indicator for the Windows system tray.
One app, many vendors — adding a new manufacturer or model is a single small
file, no changes to the UI or polling code.

![Screenshot](images/screenshot.png)

## How it works

Every mouse, regardless of vendor, is reduced to one normalized
[`BatteryStatus`](mouse_tray/battery.py) — `present / percent / charging / full
/ asleep`. A single state machine in [`ui/app.py`](mouse_tray/ui/app.py) renders
that into the tray icon (digits, charging animation, full-charge notification,
"time since last full charge" tooltip). Vendor code only does two things:
**detect the device** and **parse its battery report**.

```
mouse_tray/
  battery.py            BatteryStatus — the universal status model
  config.py             settings (poll rate, colors, font)
  resources.py          PyInstaller-safe resource paths
  storage.py            "last full charge" timestamp (Windows registry)
  drivers/
    driver.py           MouseModel, MouseDriver, @register + registry
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
    icons.py            tray icon rendering (PIL text + .ico)
    tray.py             TaskBarIcon wrapper
    app.py              wx app + the single state machine
  icons/                bundled .ico assets
```

## Run from source

```sh
uv sync
uv run python main.py        # or:  uv run python -m mouse_tray
```

## Build a standalone .exe

```sh
uv run --extra build python tools/make_release.py
# -> dist/mouse_tray/
```

## Adding a new mouse

**Same vendor, new model** — add a row to that driver's `models` list:

```python
# drivers/chipset/nordic52.py
_model("VXE NewModel", 0x373B, 0x1234, 0x5678),
```

> The `nordic52` driver covers the shared **Compx/Nordic 52840 chipset**, not just
> ATK/VXE/VGN. Many off-brand mice ride the same silicon (the receiver enumerates
> as "Compx") and work by adding a single `_model` row with their VID/PID — no new
> driver. The Zaopin Z2 Mini, Scyrox V8 and Dareu A950 Air were added exactly this
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

## Settings

Right-click the tray icon and choose **Settings…** to change the poll interval,
font, font color, charge-level coloring and debug logging from a dialog. Changes
apply immediately and are saved to the registry
(`HKCU\SOFTWARE\Mouse_Tray\Settings`), so they survive restarts; **Reset to
defaults** restores the code defaults.

With **Color by charge level** enabled, the battery-percent digits are colored
by charge instead of using the fixed font color: **red ≤ 20%**, **yellow ≤ 50%**,
**green > 50%**.

For the full set of fields (including those not exposed in the dialog), edit
[`mouse_tray/config.py`](mouse_tray/config.py):

| Field              | Meaning                                            |
| ------------------ | -------------------------------------------------- |
| `poll_rate`        | Seconds between reads while awake & discharging    |
| `fast_poll_rate`   | Seconds between reads while charging/asleep/absent |
| `foreground_color` | RGB color of the indicator digits                  |
| `dynamic_color`    | Color the percent by charge (red/yellow/green)     |
| `background_color` | RGBA icon background (transparent by default)      |
| `font`             | Font file for the digits (`consola.ttf`)           |
| `app_name`         | Storage key: registry subkey + log directory name  |
| `display_name`     | Human-facing name (tray tooltip, toasts, settings) |
| `debug`            | Verbose DEBUG logging (raw HID reports)            |

## Logging

Logs go to a rotating file at `%LOCALAPPDATA%\Mouse_Tray\app.log` (1 MB × 3
backups), plus the console when one is available — under the windowed `.exe`
build there is no console, so the file is the place to look. Enable verbose
DEBUG output (raw HID reports) with the `debug` config flag or by setting the
`MOUSE_TRAY_DEBUG=1` environment variable. Configured in
[`mouse_tray/logging_setup.py`](mouse_tray/logging_setup.py).

## Supported models

- **ATK / VXE / VGN:** ATK F1 Ultimate, ATK A9 Ultimate, ATK Zero, VXE MAD R,
  VXE MAD R Major Plus, VXE R1 Pro Max, VXE R1 SE+, VGN F1 Pro
- **Zaopin:** Z2 Mini
- **Scyrox:** V8
- **Dareu:** A950 Air
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
