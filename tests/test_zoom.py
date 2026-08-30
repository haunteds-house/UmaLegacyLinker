from __future__ import annotations

import math

from ui_qt.zoom import (
    DEFAULT_ZOOM,
    MAX_ZOOM,
    MIN_ZOOM,
    normalise_zoom,
    scaled_dimension,
    stepped_zoom,
    stored_zoom,
    zoom_percentage,
)


def test_normalise_zoom_recovers_invalid_values_and_clamps_bounds() -> None:
    assert normalise_zoom(None) == DEFAULT_ZOOM
    assert normalise_zoom("not-a-number") == DEFAULT_ZOOM
    assert normalise_zoom(math.nan) == DEFAULT_ZOOM
    assert normalise_zoom(0.1) == MIN_ZOOM
    assert normalise_zoom(9.0) == MAX_ZOOM
    assert normalise_zoom("1.25") == 1.25


def test_stepped_zoom_moves_by_ten_points_and_stops_at_bounds() -> None:
    assert stepped_zoom(1.0, 1) == 1.1
    assert stepped_zoom(1.0, -1) == 0.9
    assert stepped_zoom(MIN_ZOOM, -1) == MIN_ZOOM
    assert stepped_zoom(MAX_ZOOM, 1) == MAX_ZOOM
    assert stepped_zoom(1.25, 0) == 1.25


def test_zoom_formatting_and_geometry_are_deterministic() -> None:
    assert scaled_dimension(101, 1.25) == 127
    assert zoom_percentage(1.25) == "125 %"
    assert stored_zoom(1.25) == "1.25"
