from __future__ import annotations

import math


DEFAULT_ZOOM = 1.0
MIN_ZOOM = 0.75
MAX_ZOOM = 2.0
ZOOM_STEP = 0.1

LINEAGE_ZOOM_KEY = "lineage_view_zoom"
CALENDAR_ZOOM_KEY = "lineage_calendar_zoom"


def normalise_zoom(value: object, default: float = DEFAULT_ZOOM) -> float:
    """Return a persisted zoom value clamped to the supported step grid."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if not math.isfinite(number):
        number = default
    clipped = max(MIN_ZOOM, min(MAX_ZOOM, number))
    return round(clipped, 2)


def stepped_zoom(value: object, direction: int) -> float:
    """Move one zoom step in ``direction`` while respecting both bounds."""
    current = normalise_zoom(value)
    if direction == 0:
        return current
    return normalise_zoom(current + (ZOOM_STEP if direction > 0 else -ZOOM_STEP))


def scaled_dimension(value: float | int, zoom: object) -> int:
    """Scale logical canvas geometry without clipping its final pixel."""
    return max(1, int(math.ceil(float(value) * normalise_zoom(zoom))))


def zoom_percentage(value: object) -> str:
    return f"{int(round(normalise_zoom(value) * 100.0))} %"


def stored_zoom(value: object) -> str:
    return f"{normalise_zoom(value):.2f}"
