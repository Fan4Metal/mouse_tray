"""Startup self-diagnostics for the frozen build.

Written for the "Class 'wxPyCallback' already in RTTI table" report (issue #3):
that assert can only fire when two copies of wxPython's ``_core`` extension
are loaded into one process, and it fires while ``import wx`` runs, before any
log line or ``wx.App`` exists. The dialog itself can't be prevented from
Python, but the second copy stays loaded afterwards, so this module lets the
log explain the situation after the fact instead of relying on a bug report.

Windows-only (``psapi``); everywhere else it silently reports nothing.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from collections import defaultdict

log = logging.getLogger(__name__)

_LIST_MODULES_ALL = 0x03


def loaded_modules() -> list[str]:
    """Full paths of every module (exe, DLL, pyd) mapped into this process."""
    try:
        from ctypes import wintypes

        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, ImportError, OSError):
        return []

    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.EnumProcessModulesEx.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD,
        wintypes.LPDWORD, wintypes.DWORD,
    ]
    psapi.EnumProcessModulesEx.restype = wintypes.BOOL
    psapi.GetModuleFileNameExW.argtypes = [
        wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD,
    ]
    psapi.GetModuleFileNameExW.restype = wintypes.DWORD

    process = kernel32.GetCurrentProcess()
    needed = wintypes.DWORD()
    if not psapi.EnumProcessModulesEx(process, None, 0, ctypes.byref(needed), _LIST_MODULES_ALL):
        return []
    handles = (wintypes.HMODULE * (needed.value // ctypes.sizeof(wintypes.HMODULE)))()
    if not psapi.EnumProcessModulesEx(
        process, handles, ctypes.sizeof(handles), ctypes.byref(needed), _LIST_MODULES_ALL,
    ):
        return []
    count = min(len(handles), needed.value // ctypes.sizeof(wintypes.HMODULE))

    buf = ctypes.create_unicode_buffer(32768)
    paths: list[str] = []
    for handle in handles[:count]:
        if psapi.GetModuleFileNameExW(process, handle, buf, len(buf)):
            paths.append(buf.value)
    return paths


def wx_modules(paths: list[str] | None = None) -> list[str]:
    """The subset of loaded modules that belong to wxPython / wxWidgets.

    Matches the wx DLLs (``wxbase*``, ``wxmsw*``), every extension living in
    a ``wx`` package directory (``wx/_core.pyd``, ``wx/_adv.pyd``, ...) and,
    wherever it was loaded from, any file named like the ``wx._core`` module
    Python imported -- a stray second copy is exactly what we're looking for.
    """
    core = getattr(sys.modules.get("wx._core"), "__file__", None) or ""
    core_name = os.path.basename(core).lower()
    result = []
    for path in loaded_modules() if paths is None else paths:
        name = os.path.basename(path).lower()
        parent = os.path.basename(os.path.dirname(path)).lower()
        if name.startswith("wx") or (parent == "wx" and name.endswith(".pyd")) or name == core_name:
            result.append(path)
    return result


def duplicate_wx_modules(paths: list[str] | None = None) -> dict[str, list[str]]:
    """wx modules whose file name is loaded from more than one location."""
    by_name: dict[str, list[str]] = defaultdict(list)
    for path in wx_modules(paths):
        by_name[os.path.basename(path).lower()].append(path)
    return {name: found for name, found in by_name.items() if len(found) > 1}


def log_startup_diagnostics() -> None:
    """One WARNING if wx is loaded twice, the full wx module list at DEBUG,
    nothing otherwise."""
    modules = wx_modules()
    log.debug("Running from %s; wx modules: %s", sys.executable, modules)
    for name, paths in duplicate_wx_modules(modules).items():
        log.warning(
            "%s is loaded twice in this process (expect wxWidgets RTTI asserts): %s",
            name, " | ".join(paths),
        )
