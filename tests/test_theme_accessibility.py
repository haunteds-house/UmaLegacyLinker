from __future__ import annotations

import unittest

from ui_qt.presentation import PANEL, _spark_card
from ui_qt.theme import (
    COLORS,
    SPARK_COLORS,
    SPARK_SEMANTIC_LABELS,
    application_stylesheet,
)


def _channel(value: int) -> float:
    normalized = value / 255.0
    if normalized <= 0.04045:
        return normalized / 12.92
    return ((normalized + 0.055) / 1.055) ** 2.4


def _luminance(colour: str) -> float:
    red, green, blue = (
        int(colour[index:index + 2], 16)
        for index in (1, 3, 5)
    )
    return (
        0.2126 * _channel(red)
        + 0.7152 * _channel(green)
        + 0.0722 * _channel(blue)
    )


def _contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class ThemeAccessibilityTests(unittest.TestCase):
    def test_structural_boundaries_meet_non_text_contrast(self) -> None:
        for surface in ("background", "sidebar", "surface", "surface_alt"):
            with self.subTest(surface=surface):
                self.assertGreaterEqual(
                    _contrast(COLORS["border"], COLORS[surface]),
                    3.0,
                )
        self.assertGreaterEqual(_contrast(COLORS["focus"], COLORS["border"]), 3.0)
        for surface in ("background", "sidebar", "surface", "surface_alt"):
            with self.subTest(focus_surface=surface):
                self.assertGreaterEqual(
                    _contrast(COLORS["focus"], COLORS[surface]),
                    3.0,
                )
        for surface in ("surface", "surface_alt"):
            self.assertGreaterEqual(
                _contrast(PANEL["border"], PANEL[surface]),
                3.0,
            )

    def test_every_spark_boundary_meets_non_text_contrast(self) -> None:
        for kind, (background, border, _foreground) in SPARK_COLORS.items():
            with self.subTest(kind=kind, adjacent="chip"):
                self.assertGreaterEqual(_contrast(border, background), 3.0)
            for surface in ("surface", "surface_alt"):
                with self.subTest(kind=kind, adjacent=surface):
                    self.assertGreaterEqual(
                        _contrast(border, COLORS[surface]),
                        3.0,
                    )
            for surface in (PANEL["surface"], PANEL["surface_alt"]):
                with self.subTest(kind=kind, adjacent=surface):
                    self.assertGreaterEqual(_contrast(border, surface), 3.0)

    def test_spark_meaning_is_exposed_as_text_not_only_colour(self) -> None:
        self.assertEqual(set(SPARK_SEMANTIC_LABELS), set(SPARK_COLORS))
        self.assertEqual(
            len(set(SPARK_SEMANTIC_LABELS.values())),
            len(SPARK_SEMANTIC_LABELS),
        )
        fixtures = {
            "[Stat]": {
                "type": "blue_stat",
                "name": "Speed",
                "stars": 3,
            },
            "[Priority]": {
                "type": "white_skill",
                "name": "Corner Adept",
                "stars": 2,
                "is_score_priority": True,
            },
            "[Useful]": {
                "type": "white_skill",
                "name": "Slipstream",
                "stars": 2,
                "is_score_useful": True,
            },
        }
        for expected, factor in fixtures.items():
            with self.subTest(expected=expected):
                rendered = _spark_card(factor, "en")
                self.assertIn("class='spark-kind'", rendered)
                self.assertIn(expected, rendered)

    def test_focus_is_explicit_on_every_audited_widget_family(self) -> None:
        stylesheet = application_stylesheet()
        for selector in (
            "QCheckBox:focus",
            "QTabBar::tab:selected:focus",
            "QTableView:focus",
            "QTextBrowser:focus",
            "QSlider:focus",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, stylesheet)


if __name__ == "__main__":
    unittest.main()
