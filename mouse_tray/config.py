"""User-tunable settings and shared color constants."""

from __future__ import annotations

from dataclasses import dataclass

#: Application version, shown in the settings and about dialogs. Single source
#: for the runtime version (re-exported as ``mouse_tray.__version__``).
VERSION = "0.1.0"

#: Project identity, shown in the about dialog. Kept here with VERSION so the
#: dialog has a single source for everything it prints about the app itself.
DESCRIPTION = "Universal wireless-mouse battery indicator for the Windows system tray."
HOMEPAGE = "https://github.com/Fan4Metal/mouse_tray"

# Colors (RGB)
RED = (255, 0, 0)
GREEN = (71, 255, 12)
BLUE = (91, 184, 255)
YELLOW = (255, 255, 0)


#: Charge thresholds (percent) for the two low bands of ``dynamic_color``.
MID_THRESHOLD = 50
LOW_THRESHOLD = 20


@dataclass
class Config:
    """Application settings.

    Attributes:
        poll_rate:        Seconds between battery reads when the mouse is awake
                          and discharging.
        fast_poll_rate:   Seconds between reads in transient states
                          (charging, asleep, or no mouse) where we want to
                          react quickly.
        foreground_color: RGB color of the indicator digits. Under
                          ``dynamic_color`` it is also the color of the top
                          charge band (above ``MID_THRESHOLD``).
        dynamic_color:    When True, the battery-percent indicator is colored by
                          charge level: ``low_color`` at or below
                          ``LOW_THRESHOLD``, ``mid_color`` at or below
                          ``MID_THRESHOLD``, ``foreground_color`` above it.
        mid_color:        RGB color of the middle charge band under
                          ``dynamic_color``.
        low_color:        RGB color of the lowest charge band under
                          ``dynamic_color``.
        battery_icon:     When True, the charge level is drawn as a battery
                          filled to that percent instead of as digits; the exact
                          number moves to the hover tooltip. Only affects the
                          percent readout -- "no mouse", sleep and unknown-level
                          states stay textual.
        background_color: RGBA color of the icon background (transparent default).
        font:             Font file used for the digital indicator.
        app_name:         Storage/identity key -- the registry subkey that holds
                          settings and "last full charge" times, and the log
                          directory name. Kept underscore-form so those paths
                          stay stable; it is not shown to the user.
        display_name:     Human-facing app name (tray tooltip, notifications,
                          settings-dialog title). Change this freely; it does not
                          affect any stored path.
        debug:            Enable verbose DEBUG logging (raw HID reports). Can
                          also be turned on via the MOUSE_TRAY_DEBUG env var.
    """

    poll_rate: int = 60
    fast_poll_rate: int = 1
    foreground_color: tuple[int, int, int] = BLUE
    dynamic_color: bool = False
    mid_color: tuple[int, int, int] = YELLOW
    low_color: tuple[int, int, int] = RED
    battery_icon: bool = False
    background_color: tuple[int, int, int, int] = (0, 0, 0, 0)
    font: str = "consola.ttf"
    app_name: str = "Mouse_Tray"
    display_name: str = "Mouse Tray"
    debug: bool = False

    def charge_color(self, percent: int) -> tuple[int, int, int]:
        """Color for a battery ``percent`` when ``dynamic_color`` is on.

        The top band keeps ``foreground_color`` -- so enabling the option only
        recolors the two low bands, and the user's chosen color still means "the
        charge is fine".
        """
        if percent <= LOW_THRESHOLD:
            return self.low_color
        if percent <= MID_THRESHOLD:
            return self.mid_color
        return self.foreground_color


# Default instance used across the app. Replace fields here to retune.
config = Config()
