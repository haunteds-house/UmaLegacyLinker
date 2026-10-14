from __future__ import annotations

import unittest
from pathlib import Path

from ui_qt.accessibility import accessible_text, describe_control, label_control


PROJECT_DIR = Path(__file__).resolve().parents[1]


class _Control:
    def __init__(self, tooltip: str = "") -> None:
        self.name = ""
        self.description = ""
        self.tooltip = tooltip

    def setAccessibleName(self, value: str) -> None:
        self.name = value

    def setAccessibleDescription(self, value: str) -> None:
        self.description = value

    def toolTip(self) -> str:
        return self.tooltip


class _Label:
    def __init__(self, text: str) -> None:
        self._text = text
        self.buddy = None

    def text(self) -> str:
        return self._text

    def setBuddy(self, control: _Control) -> None:
        self.buddy = control


class AccessibilityContractTests(unittest.TestCase):
    def test_accessible_text_is_single_line_and_stable(self) -> None:
        self.assertEqual(
            accessible_text("  Parent\n  to   produce  "),
            'Parent to produce',
        )

    def test_visible_label_is_bound_and_exposed_to_assistive_apis(self) -> None:
        label = _Label('Analysis mode')
        control = _Control("Compare fast and exhaustive")

        label_control(label, control)

        self.assertIs(label.buddy, control)
        self.assertEqual(control.name, 'Analysis mode')
        self.assertEqual(control.description, "Compare fast and exhaustive")

        describe_control(control, " Analysis mode ", " Fast\n or exhaustive ")
        self.assertEqual(control.name, "Analysis mode")
        self.assertEqual(control.description, "Fast or exhaustive")

    def test_main_window_no_longer_guesses_names_from_tooltips(self) -> None:
        source = (PROJECT_DIR / "ui_qt" / "main_window.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("_assign_accessible_names", source)
        for module in (
            "components.py",
            "curve_editor.py",
            "lineage_settings.py",
            "lineage_view.py",
            "main_window.py",
            "online_options.py",
            "pages_search.py",
            "pages_tools.py",
            "pages_transfer.py",
            "pages_weights.py",
            "result_families.py",
            "result_panes.py",
        ):
            with self.subTest(module=module):
                module_source = (PROJECT_DIR / "ui_qt" / module).read_text(
                    encoding="utf-8"
                )
                self.assertTrue(
                    "describe_control" in module_source
                    or "label_control" in module_source
                    or "setAccessible" in module_source
                )


if __name__ == "__main__":
    unittest.main()
