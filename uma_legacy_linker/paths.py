"""Stable source and frozen-build paths for bundled application resources."""

from __future__ import annotations

import sys
from pathlib import Path


def app_base_dir() -> Path:
    """Directory containing user-adjacent tools and generated output."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_base_dir() -> Path:
    """Directory containing the immutable resources shipped with the app."""

    bundle_dir = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False):
        bundle_root = Path(bundle_dir).resolve() if bundle_dir else app_base_dir()
        return bundle_root / "resources"
    return Path(__file__).resolve().parent.parent / "resources"
