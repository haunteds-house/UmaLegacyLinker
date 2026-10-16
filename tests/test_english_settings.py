import json
import tempfile
import unittest
from pathlib import Path

from tests.check_english import audit
from uma_legacy_linker.application import SettingsStore


class EnglishSettingsTests(unittest.TestCase):
    def test_existing_race_conditions_keep_their_codes_after_migration(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text(json.dumps({
                "ui_language": "fr", "optimizer_rotation": "Gauche",
                "optimizer_season": "Été", "optimizer_weather": "Pluie",
                "optimizer_ground": "Soft", "optimizer_ace_card_id": "100101",
            }))
            store = SettingsStore(path)
            self.assertNotIn("ui_language", store.as_dict())
            self.assertEqual(store.get("optimizer_rotation"), "Left")
            self.assertEqual(store.get("optimizer_season"), "Summer")
            self.assertEqual(store.get("optimizer_weather"), "Rain")
            self.assertEqual(store.get("optimizer_ace_card_id"), "100101")
            store.update({"master_path": "master.mdb"})
            saved = json.loads(path.read_text())
            self.assertEqual(saved["optimizer_rotation"], "Left")
            self.assertEqual(saved["optimizer_ground"], "Soft")
            self.assertNotIn("ui_language", saved)

    def test_active_ui_copy_is_english(self):
        self.assertEqual(audit(), [])
