from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from ui_qt.presentation import _detail_styles, _rank_badge, transfer_detail_html
from ui_qt.theme import application_stylesheet
from ui_qt.typography import (
    BASE_POINT_SIZE,
    TYPE_SCALE_FACTORS,
    TYPE_SCALE_PT,
    css_point_size,
    point_size,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = PROJECT_ROOT / "ui_qt"
LITERAL_FONT_SIZE = re.compile(r"font-size\s*:\s*[0-9]+(?:\.[0-9]+)?(?:px|pt)")
RENDERED_FONT_SIZE = re.compile(r"font-size\s*:\s*([0-9]+(?:\.[0-9]+)?(?:px|pt))")


class TypographyTests(unittest.TestCase):
    def test_scale_is_closed_derived_and_readable(self) -> None:
        self.assertEqual(TYPE_SCALE_PT["body"], BASE_POINT_SIZE)
        self.assertEqual(
            TYPE_SCALE_PT,
            {
                role: BASE_POINT_SIZE * factor
                for role, factor in TYPE_SCALE_FACTORS.items()
            },
        )
        values = list(TYPE_SCALE_PT.values())
        self.assertEqual(values, sorted(values))
        self.assertGreaterEqual(min(values), 8.0)
        self.assertEqual(css_point_size("body"), "10pt")
        with self.assertRaisesRegex(ValueError, "Unknown typography role"):
            point_size("unknown")

    def test_rendered_styles_use_only_scale_points(self) -> None:
        transfer_html = transfer_detail_html(
            {"status": "keep", "card_name": "Test", "rank_score": 1234},
            "en",
        )
        rendered = "\n".join(
            (
                application_stylesheet(),
                _detail_styles(),
                _rank_badge("S"),
                _rank_badge("S", large=True),
                transfer_html,
            )
        )
        sizes = RENDERED_FONT_SIZE.findall(rendered)
        self.assertTrue(sizes)
        self.assertNotIn("px", " ".join(sizes))
        self.assertLessEqual(set(sizes), {css_point_size(role) for role in TYPE_SCALE_PT})

    def test_sources_do_not_reintroduce_literal_font_sizes(self) -> None:
        offenders = []
        for path in UI_ROOT.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for match in LITERAL_FONT_SIZE.finditer(source):
                offenders.append(f"{path.name}: {match.group(0)}")
        self.assertEqual(offenders, [])

    def test_painter_fonts_use_named_roles_instead_of_numeric_sizes(self) -> None:
        offenders = []
        for path in UI_ROOT.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("setPixelSize(", source, path.name)
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in {"setPointSize", "setPointSizeF"} or not node.args:
                    continue
                if isinstance(node.args[0], ast.Constant):
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [])

    def test_rich_text_inherits_the_application_font_family(self) -> None:
        presentation = (UI_ROOT / "presentation.py").read_text(encoding="utf-8")
        self.assertNotIn("font-family", presentation)
        self.assertEqual(application_stylesheet().count("font-family:"), 1)

    def test_share_bar_uses_geometry_instead_of_tiny_text(self) -> None:
        styles = _detail_styles()
        source = (UI_ROOT / "presentation.py").read_text(encoding="utf-8")
        self.assertIn(".share-bar td { padding:0; border:0; height:5px; }", styles)
        self.assertNotIn("font-size:5px", source)


if __name__ == "__main__":
    unittest.main()
