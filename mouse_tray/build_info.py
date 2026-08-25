"""Resolve the git commit the running build was made from.

Two sources, in order:
  * ``_commit.py`` — written at build time by ``tools/make_release.py`` and
    bundled into the frozen exe (where git isn't available).
  * ``git rev-parse`` in the source checkout during development.

Returns ``""`` when neither is available, so callers can hide it.
:func:`version_string` wraps that into the label every dialog shows.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def version_string() -> str:
    """The user-facing version: ``"0.1.0 (abc1234)"``, or just ``"0.1.0"``."""
    from .config import VERSION

    commit = commit_hash()
    return f"{VERSION} ({commit})" if commit else VERSION


def commit_hash() -> str:
    """Short commit hash of this build, or ``""`` if it can't be determined."""
    try:
        from ._commit import COMMIT  # type: ignore  # generated at build time

        if COMMIT:
            return COMMIT
    except Exception:
        pass

    # In a frozen exe there's no repo to query; the baked-in value above is all
    # we get. Only shell out to git from a real source checkout.
    if getattr(sys, "frozen", False):
        return ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,  # a git failure just means "no commit info"
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""
