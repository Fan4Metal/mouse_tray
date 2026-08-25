"""Build a standalone Windows executable with PyInstaller.

Run with:  uv run --extra build python tools/make_release.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Project root is the parent of this script's "tools" directory.
ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "mouse_tray"

# Battery/state icons are generated procedurally at runtime (ui/icons.py);
# only the window/exe icon still needs to ship as a file.
ICONS = ["app.ico"]

# Modules nothing in the app reaches, each dragging real weight into the bundle.
# PyInstaller pulls them in through Pillow's optional codecs and the stdlib's
# optional imports, never through our code: the app uses PIL only for text on an
# RGBA canvas, wx only for widgets/SVG, and it opens no socket. Verified by
# running the whole UI -- icons, tray menu, both dialogs -- with each of these
# blocked at import time.
#
# Two that look excludable but are not: `socket` (logging.handlers imports it
# for SocketHandler) and `zlib` (PyInstaller's own archive).
EXCLUDES = [
    "PIL._avif",  # ~7.6 MB of AVIF codec
    "PIL._webp",
    "PIL._imagingcms",
    "PIL._imagingtk",
    "PIL._imagingmath",
    "wx.html",  # the module plus its own wxWidgets DLL, ~1.3 MB
    "ssl",  # with _ssl/_hashlib go libcrypto + libssl, ~9.5 MB
    "_ssl",
    "_hashlib",
    "unicodedata",
    "decimal",
    "_decimal",
    "pyexpat",
    "_elementtree",
    "xml",
    "lzma",
    "_lzma",
    "bz2",
    "_bz2",
    "_zstd",  # base_library.zip is stored uncompressed, so no codec is needed
    "tkinter",
]


def _write_commit_module() -> Path | None:
    """Bake the current git commit into mouse_tray/_commit.py for the exe.

    git isn't available inside the frozen build, so capture it here and let
    build_info.commit_hash() read the baked-in value at runtime.
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,  # no git / not a checkout -> just skip the commit hash
        ).stdout.strip()
    except Exception:
        commit = ""
    if not commit:
        return None
    path = PKG / "_commit.py"
    path.write_text(f'COMMIT = "{commit}"\n', encoding="utf-8")
    return path


def main() -> None:
    commit_module = _write_commit_module()
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
    for module in EXCLUDES:
        cmd += ["--exclude-module", module]
    # The baked-in commit hash is imported lazily, so PyInstaller can't see it.
    if commit_module is not None:
        cmd += ["--hidden-import", "mouse_tray._commit"]
    for icon in ICONS:
        # Bundle into <bundle>/icons -- matches resources.icon_path(), which
        # resolves to "<_MEIPASS>/icons/<name>" at runtime.
        cmd += ["--add-data", f"mouse_tray/icons/{icon};icons"]
    cmd.append("main.py")

    print("Running:", " ".join(cmd))
    # Run from the project root so the relative paths above resolve, no matter
    # where the script itself was invoked from.
    result = subprocess.run(cmd, cwd=ROOT, check=False)  # exit code handled below
    if result.returncode != 0:
        sys.exit(result.returncode)
    print("\n=== Release created in dist/mouse_tray ===")


if __name__ == "__main__":
    main()
