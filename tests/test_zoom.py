from __future__ import annotations

import math

from ui_qt.zoom import (
    DEFAULT_ZOOM,
    MAX_ZOOM,
    MIN_POINTER_TARGET_PX,
    MIN_ZOOM,
    minimum_pointer_target_extent,
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


def test_pointer_targets_never_shrink_below_twenty_four_pixels() -> None:
    for zoom in (MIN_ZOOM, 0.8, 0.9, 1.0, 1.25, MAX_ZOOM):
        logical_extent = minimum_pointer_target_extent(25.0, zoom)
        assert logical_extent * zoom >= MIN_POINTER_TARGET_PX
    assert minimum_pointer_target_extent(25.0, MIN_ZOOM) == 32.0
    assert minimum_pointer_target_extent(25.0, 1.0) == 25.0
    assert minimum_pointer_target_extent(25.0, MAX_ZOOM) == 25.0
