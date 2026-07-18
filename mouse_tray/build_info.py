"""Resolve the git commit the running build was made from.

Two sources, in order:
  * ``_commit.py`` — written at build time by ``tools/make_release.py`` and
    bundled into the frozen exe (where git isn't available).
  * ``git rev-parse`` in the source checkout during development.

Returns ``""`` when neither is available, so callers can hide it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


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
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""
