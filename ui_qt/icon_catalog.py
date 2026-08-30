"""Vendored SVG icons, tinted at paint time.

A bare Unicode character used as an icon is a request addressed to the host
font stack, not a self-contained glyph: if the selected UI font lacks the
character, Qt falls back through whatever fonts are installed, and that
fallback chain depends on the OS version, installed fonts and locale. When
it lands on a legacy symbol-encoded font (Symbol, Wingdings, Webdings), the
codepoint is remapped onto that font's own encoding and an unrelated letter
is drawn instead of the intended shape.

SVG assets avoid this entirely: the file is self-contained, recoloured for
the active theme with :class:`QPainter`, and stays crisp at any DPI or
window scale.

Chrome icons are vendored from `Lucide <https://lucide.dev>`_ (ISC licence —
see ``docs/THIRD_PARTY.md``) as flat 24x24 ``stroke="currentColor"`` SVGs and
registered in :data:`ICON_FILES`. Domain badges whose colour is itself useful
information (weather, season and running style) live beside them in
:data:`FIXED_ICON_FILES` and are rendered as authored instead of being tinted.
Call sites only reference semantic keys, never file names directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ui_qt.core import resource_base_dir

# Semantic key -> vendored Lucide file name. Keys are what the rest of the
# UI imports; file names are an implementation detail of the vendored set.
ICON_FILES: dict[str, str] = {
    "nav-home": "house.svg",
    "nav-data": "database.svg",
    "nav-search": "search.svg",
    "nav-transfer": "arrow-left-right.svg",
    "nav-weights": "sliders-horizontal.svg",
    "nav-tools": "settings.svg",
    "rail-collapse": "chevron-left.svg",
    "rail-expand": "chevron-right.svg",
    "affinity": "heart.svg",
}

# Domain badges keep their authored palette. Colour is functional information
# for these values, so theme tinting would deliberately erase a distinction.
FIXED_ICON_FILES: dict[str, str] = {
    "weather-sunny": "weather-sunny.svg",
    "weather-cloudy": "weather-cloudy.svg",
    "weather-rain": "weather-rain.svg",
    "weather-snow": "weather-snow.svg",
    "season-spring": "season-spring.svg",
    "season-summer": "season-summer.svg",
    "season-autumn": "season-autumn.svg",
    "season-winter": "season-winter.svg",
    "style-front-runner": "style-front-runner.svg",
    "style-pace-chaser": "style-pace-chaser.svg",
    "style-late-surger": "style-late-surger.svg",
    "style-end-closer": "style-end-closer.svg",
}

DEFAULT_SIZE = 20


def icons_dir() -> Path:
    return resource_base_dir() / "ui_qt" / "icons"


def icon_path(key: str) -> Path:
    try:
        filename = ICON_FILES[key]
    except KeyError:
        try:
            filename = FIXED_ICON_FILES[key]
        except KeyError as exc:
            raise KeyError(f"Unknown icon key: {key!r}") from exc
    return icons_dir() / filename


@lru_cache(maxsize=None)
def _raw_svg(key: str) -> bytes:
    return icon_path(key).read_bytes()


@lru_cache(maxsize=None)
def tinted_pixmap(key: str, color: str, size: int = DEFAULT_SIZE) -> QPixmap:
    """Render a tintable SVG for ``key`` at ``size`` px in ``color``.

    Lucide draws with ``stroke="currentColor"``; Qt's SVG renderer does not
    resolve that against a paint colour, so the stroke is rasterised at its
    literal colour first and then remapped with ``SourceIn`` compositing.
    That keeps the renderer's anti-aliased stroke edges intact instead of
    hard-thresholding them, which a colour-key replace would do.
    """
    if key not in ICON_FILES:
        raise KeyError(f"{key!r} is not a tintable icon; use native_icon() instead")
    renderer = QSvgRenderer(QByteArray(_raw_svg(key)))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return pixmap


def icon(key: str, color: str, size: int = DEFAULT_SIZE) -> QIcon:
    """A flat, single-colour :class:`QIcon` for ``key``."""
    return QIcon(tinted_pixmap(key, color, size))


@lru_cache(maxsize=None)
def native_pixmap(key: str, size: int = DEFAULT_SIZE) -> QPixmap:
    """Render a fixed-palette SVG exactly as authored."""

    if key not in FIXED_ICON_FILES:
        raise KeyError(f"{key!r} is not a fixed-palette icon; use icon() instead")
    renderer = QSvgRenderer(QByteArray(_raw_svg(key)))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


def native_icon(key: str, size: int = DEFAULT_SIZE) -> QIcon:
    """Return a :class:`QIcon` for a fixed-palette domain badge."""

    return QIcon(native_pixmap(key, size))


def stateful_icon(
    key: str,
    *,
    off_color: str,
    on_color: str,
    size: int = DEFAULT_SIZE,
) -> QIcon:
    """A :class:`QIcon` that recolours itself with a checkable button's state.

    Qt paints a checkable :class:`QAbstractButton` using the icon's
    ``QIcon.State.On`` pixmap while checked and ``QIcon.State.Off``
    otherwise, with no extra wiring needed on the caller's side once the
    icon carries both.
    """
    result = QIcon()
    result.addPixmap(tinted_pixmap(key, off_color, size), QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(tinted_pixmap(key, on_color, size), QIcon.Mode.Normal, QIcon.State.On)
    return result
