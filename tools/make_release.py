"""Build a standalone Windows executable with PyInstaller.

Run with:  uv run --extra build python tools/make_release.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from datetime import date
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


#: Windows version resource. Without one the shell has no name for the process,
#: so tray notifications and Task Manager both fall back to "mouse_tray.exe";
#: FileDescription is the string they show instead. Filled from config so the
#: exe never disagrees with the app about its own name and version.
VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0,
    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        "040904B0",  # US English, Unicode
        [
          StringStruct("CompanyName", "{author}"),
          StringStruct("FileDescription", "{name}"),
          StringStruct("FileVersion", "{version}"),
          StringStruct("InternalName", "mouse_tray"),
          StringStruct("LegalCopyright", "(c) {year} {author}"),
          StringStruct("OriginalFilename", "mouse_tray.exe"),
          StringStruct("ProductName", "{name}"),
          StringStruct("ProductVersion", "{version}"),
        ],
      )
    ]),
    VarFileInfo([VarStruct("Translation", [1033, 1200])]),
  ],
)
"""


def _write_version_file(directory: Path) -> Path:
    """Write the version resource PyInstaller stamps into the exe.

    Not into ``build/``: that is PyInstaller's workpath and ``--clean`` empties
    it before the build reads anything.
    """
    sys.path.insert(0, str(ROOT))
    from mouse_tray.config import AUTHOR, VERSION, config

    numbers = [int(part) for part in VERSION.split(".") if part.isdigit()]
    numbers = [*numbers, 0, 0, 0, 0][:4]
    path = directory / "version_info.txt"
    path.write_text(
        VERSION_INFO.format(
            nums=tuple(numbers),
            name=config.display_name,
            version=VERSION,
            author=AUTHOR,
            year=date.today().year,
        ),
        encoding="utf-8",
    )
    return path


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


def _command(commit_module: Path | None, version_file: Path) -> list[str]:
    """Assemble the PyInstaller command line."""
    cmd = [
        "uv", "run", "--extra", "build", "pyinstaller",
        "--clean",
        "--noconsole",
        "--noconfirm",
        "--onedir",
        "--icon", "mouse_tray/icons/app.ico",
        "--name", "mouse_tray",
        "--version-file", str(version_file),
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
    return cmd


def main() -> None:
    commit_module = _write_commit_module()
    with tempfile.TemporaryDirectory() as tmp:
        cmd = _command(commit_module, _write_version_file(Path(tmp)))
        print("Running:", " ".join(cmd))
        # Run from the project root so the relative paths above resolve, no
        # matter where the script itself was invoked from.
        result = subprocess.run(cmd, cwd=ROOT, check=False)  # exit code handled below
    if result.returncode != 0:
        sys.exit(result.returncode)
    print("\n=== Release created in dist/mouse_tray ===")


if __name__ == "__main__":
    main()
