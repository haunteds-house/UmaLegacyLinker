from __future__ import annotations

import unittest
from pathlib import Path

from i18n import translate_text


PROJECT_DIR = Path(__file__).resolve().parents[1]


class DataPageHierarchyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (PROJECT_DIR / "ui_qt" / "pages_home_data.py").read_text(
            encoding="utf-8"
        )

    def test_extraction_is_the_primary_first_action(self) -> None:
        self.assertIn('self.extract_button.setObjectName("primary")', self.source)
        self.assertNotIn('self.link_button.setObjectName("primary")', self.source)
        self.assertLess(
            self.source.index("actions.addWidget(self.extract_card"),
            self.source.index("actions.addWidget(self.link_card"),
        )
        self.assertIn('t("Extraire ma collection")', self.source)
        self.assertIn('t("Relier un export existant")', self.source)

    def test_maintenance_actions_are_separated_and_explained(self) -> None:
        self.assertIn("maintenance_actions.addWidget(self.catalog_button)", self.source)
        self.assertIn("maintenance_actions.addWidget(self.force_link_button)", self.source)
        self.assertIn("maintenance_actions.addWidget(self.open_button)", self.source)
        self.assertGreaterEqual(self.source.count(".setToolTip("), 9)


class TransferGuidanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (PROJECT_DIR / "ui_qt" / "pages_transfer.py").read_text(
            encoding="utf-8"
        )

    def test_transfer_controls_and_verdicts_have_contextual_help(self) -> None:
        targets = (
            "mode_combo",
            "upcoming_cm_check",
            "team_trials_check",
            "generic_profiles_check",
            "safe_card",
            "recommended_card",
            "review_card",
            "keep_card",
            "protected_card",
            "table",
            "detail",
        )
        for target in targets:
            with self.subTest(target=target):
                self.assertIn(f"self.{target}.setToolTip(", self.source)

    def test_new_guidance_is_translated(self) -> None:
        strings = (
            "Extraire ma collection",
            "Relier un export existant",
            "Maintenance et fichiers",
            "Le mode rapide repère les redondances ; seul l’audit exhaustif peut conclure à un transfert strictement sûr.",
            "La couverture désigne le remplaçant ou l’ensemble de vétérans qui préserve les rôles compétitifs de la copie.",
            "Un verrou ou un mémo en jeu interdit toute recommandation de transfert, quel que soit le score.",
        )
        for source in strings:
            with self.subTest(source=source):
                self.assertNotEqual(translate_text(source, "en"), source)


if __name__ == "__main__":
    unittest.main()
