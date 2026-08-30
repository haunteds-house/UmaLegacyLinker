"""Typography helpers for dense numeric Qt views."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget


# PySide6 6.8 advertises ``str`` as an accepted setFeature() overload, but the
# binding rejects it at runtime. Construct the strongly typed OpenType tag once
# so every table works in both source and packaged Windows builds.
TABULAR_NUMBERS_FEATURE = QFont.Tag("tnum")


def enable_tabular_numbers(widget: QWidget) -> None:
    """Use equal-width OpenType figures without replacing the UI typeface."""
    font = widget.font()
    font.setFeature(TABULAR_NUMBERS_FEATURE, 1)
    widget.setFont(font)
