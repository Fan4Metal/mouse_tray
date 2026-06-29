"""Build a standalone Windows executable with PyInstaller.

Run with:  uv run --extra build python tools/make_release.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Project root is the parent of this script's "tools" directory.
ROOT = Path(__file__).resolve().parent.parent

ICONS = [
    "battery_0.ico",
    "battery_50.ico",
    "battery_100.ico",
    "battery_100_green.ico",
]


def main() -> None:
    cmd = [
        "uv", "run", "--extra", "build", "pyinstaller",
        "--clean",
        "--noconsole",
        "--noconfirm",
        "--onedir",
        "--icon", "mouse_tray/icons/app.ico",
        "--name", "mouse_tray",
        # Driver modules are imported dynamically (importlib) in
        # drivers/__init__.py, so PyInstaller can't see them statically.
        # Collect the whole subpackage; new drivers are then included for free.
        "--collect-submodules", "mouse_tray.drivers",
    ]
    for icon in ICONS:
        # Bundle into <bundle>/icons -- matches resources.icon_path(), which
        # resolves to "<_MEIPASS>/icons/<name>" at runtime.
        cmd += ["--add-data", f"mouse_tray/icons/{icon};icons"]
    cmd.append("main.py")

    print("Running:", " ".join(cmd))
    # Run from the project root so the relative paths above resolve, no matter
    # where the script itself was invoked from.
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        sys.exit(result.returncode)
    print("\n=== Release created in dist/mouse_tray ===")


if __name__ == "__main__":
    main()
