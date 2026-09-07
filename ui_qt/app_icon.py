"""Optional application branding, separate from the UI icon catalogue."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

from uma_legacy_linker.paths import resource_base_dir


def application_icon(resources: Path | None = None) -> QIcon:
    """Prefer the Windows ICO, then PNG; missing artwork is a supported state."""
    branding = (resources if resources is not None else resource_base_dir()) / "branding"
    for filename in ("app.ico", "app.png"):
        path = branding / filename
        if path.is_file():
            icon = QIcon(str(path))
            if not icon.isNull() and not icon.pixmap(32, 32).isNull():
                return icon
    return QIcon()
