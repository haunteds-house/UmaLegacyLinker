import itertools
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from uma_workbench.collection import collection_facets, matches_filters
from uma_workbench.core import MasterData, Store
from uma_workbench.goals import validate_training_goal
from uma_workbench.planning import PlanningCatalog, _deck_frontier, find_setups
from uma_workbench.roster_viewer import roster_document, selection_for_plan


class RosterWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "profile")
        self.master = MasterData()
        self.master.cards = {100101: {"chara_id": 1001, "default_rarity": 3}}
        self.master.supports = {sid: {"chara_id": 3000 + sid, "rarity": 3} for sid in range(1, 8)}
        self.store.import_bytes("card_data.json", b'[{"card_id":100101,"rarity":3}]')
        self.store.import_bytes("support_card_data.json", json.dumps([
            {"support_card_id": sid, "level": sid + 10} for sid in range(1, 7)]).encode())
        self.store.import_bytes("trained_chara_data.json", b'[{"trained_chara_id":10,"card_id":100201},{"trained_chara_id":11,"card_id":100201}]')
        self.goal = {"role": "TT", "max_attempts": 10, "stop_condition": "Meet targets", "training": {"enabled": False}}

    def tearDown(self):
        self.temp.cleanup()

    def test_six_owned_supports_require_an_explicit_borrowed_slot(self):
        with self.assertRaisesRegex(ValueError, "five owned supports and one borrowed"):
            validate_training_goal({**self.goal, "deck_ids": list(range(1, 7))}, self.store, self.master)
        validate_training_goal({**self.goal, "deck_ids": list(range(1, 7)), "borrowed_support_id": 1}, self.store, self.master)

    def test_search_always_reserves_one_rental_even_when_six_owned_cards_exist(self):
        report = find_setups(self.store, self.master, self.goal, catalog=PlanningCatalog())
        self.assertTrue(report["setups"])
        for setup in report["setups"]:
            self.assertEqual(len(setup["supports"]), 6)
            self.assertEqual(sum(bool(row.get("borrowed")) for row in setup["supports"]), 1)
            self.assertEqual(sum(not row.get("borrowed") for row in setup["supports"]), 5)

    def test_a_rental_copy_of_an_owned_card_is_distinct_from_owned_effects(self):
        report = find_setups(self.store, self.master, {**self.goal, "borrowed_support_id": 1}, catalog=PlanningCatalog())
        for setup in report["setups"]:
            rental = next(row for row in setup["supports"] if row.get("borrowed"))
            self.assertEqual(rental["support_card_id"], 1)
            self.assertNotIn("level", rental)
            self.assertNotIn(1, [row["support_card_id"] for row in setup["supports"] if not row.get("borrowed")])

    def test_rental_frontier_matches_exhaustive_small_collection(self):
        catalog = PlanningCatalog()
        catalog.hint_data_available = True
        for sid in self.master.supports:
            catalog.support_hints[sid] = {100 + sid % 3}
        wanted = [100, 101, 102]
        owned = self.store.entities("supports")
        frontier = _deck_frontier(self.master, catalog, owned, 1001, wanted, (), lambda: None, require_borrowed=True)
        oracle = {}
        for rental in self.master.supports:
            for own in itertools.combinations([row for row in owned if row["support_card_id"] != rental], 5):
                skills = set().union(*(catalog.support_hints[row["support_card_id"]] for row in own), catalog.support_hints[rental])
                mask = sum(1 << index for index, identity in enumerate(wanted) if identity in skills)
                quality = 50 + sum(row["level"] for row in own)
                oracle[mask] = max(oracle.get(mask, 0), quality)
        self.assertEqual({mask: quality for mask, quality, _deck, _pruned in frontier}, oracle)

    def test_removed_completed_prerequisites_still_allow_dependent_plan_to_start(self):
        first = self.store.save_goal("Parent", self.goal, status="Complete")
        second = self.store.save_goal("Runner", {**self.goal, "prerequisites": [first]})
        self.store.remove_goal(first)
        reopened = Store(self.store.directory)
        self.assertEqual([row["id"] for row in reopened.goals(include_removed=False)], [second])
        reopened.change_goal_status(second, "In progress")
        reopened.remove_goal(first, removed=False)
        self.assertEqual(reopened.goals()[0]["status"], "Complete")

    def test_existing_goal_database_migrates_without_losing_plans(self):
        legacy = Path(self.temp.name) / "old"
        legacy.mkdir()
        with closing(sqlite3.connect(legacy / "workbench.sqlite3")) as con:
            with con:
                con.execute("CREATE TABLE goals(id INTEGER PRIMARY KEY,title TEXT,status TEXT,payload TEXT,created_at TEXT)")
                con.execute("INSERT INTO goals VALUES(1,'Older plan','Complete','{}','2026-01-01')")
        self.assertEqual(Store(legacy).goals(include_removed=False)[0]["title"], "Older plan")

    def test_filters_combine_actual_aptitudes_sparks_skills_and_stats(self):
        self.master.factors = {101: {"factor_type": 1, "factor_group_id": 1, "rarity": 1},
            103: {"factor_type": 1, "factor_group_id": 1, "rarity": 3},
            3203: {"factor_type": 2, "factor_group_id": 32, "rarity": 3}}
        self.master.names = {(147, 101): "Speed", (147, 103): "Speed", (147, 3203): "Mile", (47, 200): "Corner Recovery"}
        veteran = {"card_id": 100201, "speed": 900, "proper_distance_mile": 7,
            "skill_array": [{"skill_id": 200}], "factor_info_array": [{"factor_id": 101, "level": 0}],
            "succession_chara_array": [
                {"position_id": 10, "factor_info_array": [{"factor_id": 103}]},
                {"position_id": 20, "factor_info_array": [{"factor_id": 3203}]},
                {"position_id": 11, "factor_info_array": [{"factor_id": 103}]}]}
        row = {"facets": collection_facets(self.master, "veterans", veteran)}
        filters = {"aptitudes": {"proper_distance_mile": 7}, "sparks": [("Blue:1", 3)], "skill": 200, "stats": {"speed": 900}}
        self.assertFalse(matches_filters(row, filters))
        self.assertTrue(matches_filters(row, {**filters, "family": True}))
        self.assertEqual(row["facets"]["family_sparks"]["Blue:1"], 4)
        self.assertFalse(matches_filters(row, {**filters, "family": True, "aptitudes": {"proper_distance_mile": 8}}))
        self.assertFalse(matches_filters(row, {"stats": {"speed": 901}}))
        self.assertEqual(row["facets"]["spark_labels"]["Pink:32"], "Pink · Mile")

    def test_roster_adapter_excludes_account_and_nested_trainer_fields(self):
        data = roster_document([{"card_id": 100101, "viewer_id": 123, "trainer_name": "Private name",
            "succession_chara_array": [{"card_id": 100201, "trainer_id": 456, "factor_info_array": [{"factor_id": 103, "level": 0}]}]}])
        self.assertEqual(data, {"trained_chara_array": [{"card_id": 100101,
            "succession_chara_array": [{"card_id": 100201, "factor_info_array": [{"factor_id": 103, "level": 0}]}]}]})

    def test_viewer_selection_never_guesses_between_owned_veteran_copies(self):
        result = selection_for_plan({"target": 100101, "parents": [{"card_id": 100201}]}, self.store)
        self.assertEqual(result["viewer_parent_candidates"], [[10, 11]])
        self.assertEqual(result["viewer_parent_ids"], [None])
        with self.assertRaisesRegex(ValueError, "not in your imported trainees"):
            selection_for_plan({"target": 100301}, self.store)
