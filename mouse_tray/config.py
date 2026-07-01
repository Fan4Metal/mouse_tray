"""User-tunable settings and shared color constants."""

from __future__ import annotations

from dataclasses import dataclass

# Colors (RGB)
RED = (255, 0, 0)
GREEN = (71, 255, 12)
BLUE = (91, 184, 255)
YELLOW = (255, 255, 0)


def charge_color(percent: int) -> tuple[int, int, int]:
    """Traffic-light color for a battery ``percent``: red low, yellow mid, green high."""
    if percent <= 20:
        return RED
    if percent <= 50:
        return YELLOW
    return GREEN


@dataclass
class Config:
    """Application settings.

    Attributes:
        poll_rate:        Seconds between battery reads when the mouse is awake
                          and discharging.
        fast_poll_rate:   Seconds between reads in transient states
                          (charging, asleep, or no mouse) where we want to
                          react quickly.
        foreground_color: RGB color of the indicator digits.
        dynamic_color:    When True, the battery-percent digits are colored by
                          charge level (green/yellow/red) instead of using
                          ``foreground_color``.
        background_color: RGBA color of the icon background (transparent default).
        font:             Font file used for the digital indicator.
        app_name:         Used for the tray title, notifications, the registry
                          key that stores the "last full charge" time, and the
                          log directory name.
        debug:            Enable verbose DEBUG logging (raw HID reports). Can
                          also be turned on via the MOUSE_TRAY_DEBUG env var.
    """

    poll_rate: int = 60
    fast_poll_rate: int = 1
    foreground_color: tuple[int, int, int] = BLUE
    dynamic_color: bool = False
    background_color: tuple[int, int, int, int] = (0, 0, 0, 0)
    font: str = "consola.ttf"
    app_name: str = "Mouse_Tray"
    debug: bool = False


# Default instance used across the app. Replace fields here to retune.
config = Config()
