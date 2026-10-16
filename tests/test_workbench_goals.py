import json
import tempfile
import unittest
from pathlib import Path

from uma_workbench.core import MasterData, Store
from uma_workbench.goals import validate_training_goal


class GoalConstraintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        for filename, data in (
            ("card_data.json", [{"card_id": 100101}]),
            ("support_card_data.json", [{"support_card_id": 1}, {"support_card_id": 2}]),
            ("trained_chara_data.json", [
                {"trained_chara_id": 10, "card_id": 100201},
                {"trained_chara_id": 11, "card_id": 100201},
            ]),
        ):
            self.store.import_bytes(filename, json.dumps(data).encode())
        self.master = MasterData()
        self.master.supports = {1: {"chara_id": 1001}, 2: {"chara_id": 1003}, 3: {"chara_id": 1004}}
        self.payload = {"card_id": 100101, "role": "TT", "stats": {},
            "deck_ids": [2, 3], "parent_ids": [10], "max_attempts": 10,
            "stop_condition": "Reach the recorded targets"}

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_deck_allows_one_borrowed_support(self):
        validate_training_goal(self.payload, self.store, self.master)

    def test_deck_rejects_target_character_and_extra_borrowed_supports(self):
        with self.assertRaisesRegex(ValueError, "target trainee"):
            validate_training_goal({**self.payload, "deck_ids": [1]}, self.store, self.master)
        with self.assertRaisesRegex(ValueError, "at most one borrowed"):
            validate_training_goal({**self.payload, "deck_ids": [3, 4]}, self.store, self.master)

    def test_distinct_copies_of_the_same_parent_character_cannot_fill_both_slots(self):
        with self.assertRaisesRegex(ValueError, "distinct characters"):
            validate_training_goal({**self.payload, "parent_ids": [10, 11]}, self.store, self.master)
