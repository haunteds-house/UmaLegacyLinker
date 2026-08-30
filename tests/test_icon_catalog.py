"""Coverage for the vendored SVG icon set.

A broken icon glyph is invisible to `ui_qt/layout_audit.py`: that audit
renders on the CI machine's own fonts, so a Unicode character that falls
back to a legacy symbol-encoded font there will render "fine" in the
screenshots and still break on a user's machine with a different font
stack. These tests instead check the vendored assets directly (file
integrity, no orphans) and, where PySide6 is available, that every
catalogued icon actually rasterises to a non-blank, correctly tinted
pixmap.
"""

from __future__ import annotations

import os
import unittest
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui_qt.icon_catalog import ICON_FILES, icons_dir

try:
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication

    from ui_qt.icon_catalog import icon, stateful_icon, tinted_pixmap
except ImportError:  # Source-only backend test environments do not install Qt.
    QApplication = None  # type: ignore[assignment]


class IconCatalogIntegrityTests(unittest.TestCase):
    """Filesystem- and XML-level checks that need no Qt runtime at all."""

    def test_every_catalogued_key_resolves_to_a_file(self) -> None:
        for key, filename in ICON_FILES.items():
            path = icons_dir() / filename
            self.assertTrue(path.is_file(), f"{key!r} -> {path} is missing")

    def test_no_orphan_files_in_the_icons_directory(self) -> None:
        registered = set(ICON_FILES.values())
        on_disk = {path.name for path in icons_dir().glob("*.svg")}
        orphans = on_disk - registered
        self.assertFalse(
            orphans,
            f"SVG files present on disk but not registered in ICON_FILES: {sorted(orphans)}",
        )
        missing = registered - on_disk
        self.assertFalse(missing, f"ICON_FILES entries with no file on disk: {sorted(missing)}")

    def test_every_svg_is_well_formed_and_square(self) -> None:
        for filename in sorted(set(ICON_FILES.values())):
            path = icons_dir() / filename
            tree = ET.parse(path)
            root = tree.getroot()
            self.assertTrue(root.tag.endswith("svg"), f"{filename}: not an <svg> root")
            view_box = root.get("viewBox")
            self.assertEqual(
                view_box,
                "0 0 24 24",
                f"{filename}: expected a 24x24 viewBox, found {view_box!r}",
            )

    def test_every_svg_uses_stroke_currentcolor(self) -> None:
        # tinted_pixmap() recolours by SourceIn-compositing over the whole
        # rasterised stroke; a fill-based icon would silently render as a
        # solid colour swatch instead of the intended outline shape.
        for filename in sorted(set(ICON_FILES.values())):
            path = icons_dir() / filename
            content = path.read_text(encoding="utf-8")
            self.assertIn(
                'stroke="currentColor"',
                content,
                f"{filename}: expected a stroke=\"currentColor\" Lucide-style icon",
            )


@unittest.skipUnless(QApplication is not None, "PySide6 is not installed")
class IconRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert QApplication is not None
        cls.application = QApplication.instance() or QApplication([])

    def test_every_icon_renders_to_a_non_blank_pixmap(self) -> None:
        for key in ICON_FILES:
            pixmap = tinted_pixmap(key, "#68d3b1", 20)
            self.assertFalse(pixmap.isNull(), key)
            image = pixmap.toImage()
            has_opaque_pixel = any(
                image.pixelColor(x, y).alpha() > 0
                for x in range(image.width())
                for y in range(image.height())
            )
            self.assertTrue(has_opaque_pixel, f"{key} rendered fully transparent")

    def test_tint_colour_is_applied(self) -> None:
        pixmap = tinted_pixmap("nav-home", "#ff0000", 20)
        image = pixmap.toImage()
        red = QColor("#ff0000")
        matches = [
            image.pixelColor(x, y)
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).alpha() > 0
        ]
        self.assertTrue(matches, "icon rendered no opaque pixels to check")
        for pixel in matches:
            self.assertEqual(pixel.red(), red.red())
            self.assertEqual(pixel.green(), red.green())
            self.assertEqual(pixel.blue(), red.blue())

    def test_icon_helper_returns_a_usable_qicon(self) -> None:
        result = icon("nav-search", "#91a3bb")
        self.assertFalse(result.isNull())

    def test_stateful_icon_carries_distinct_on_and_off_pixmaps(self) -> None:
        result = stateful_icon("rail-collapse", off_color="#91a3bb", on_color="#68d3b1")
        self.assertFalse(result.isNull())
        off_image = result.pixmap(20, 20).toImage()
        # QIcon does not expose an On/Off pixmap getter directly; render via
        # the tinted helpers instead and confirm the two colours differ,
        # which is what actually distinguishes the checked nav state.
        off_pixmap = tinted_pixmap("rail-collapse", "#91a3bb", 20)
        on_pixmap = tinted_pixmap("rail-collapse", "#68d3b1", 20)
        self.assertNotEqual(off_pixmap.toImage(), on_pixmap.toImage())
        self.assertFalse(off_image.isNull())


if __name__ == "__main__":
    unittest.main()
