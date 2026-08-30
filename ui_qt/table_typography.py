"""Typography helpers for dense numeric Qt views."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


TABULAR_NUMBERS_FEATURE = "tnum"


def enable_tabular_numbers(widget: QWidget) -> None:
    """Use equal-width OpenType figures without replacing the UI typeface."""
    font = widget.font()
    font.setFeature(TABULAR_NUMBERS_FEATURE, 1)
    widget.setFont(font)
