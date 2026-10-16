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
from uma_workbench.roster_viewer import lineage_preview, selection_for_plan


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

    def test_native_selection_preserves_the_exact_veteran_copy(self):
        result = selection_for_plan({"target": 100101, "parent_ids": [None, 11]}, self.store, self.master)
        self.assertEqual(result, {"card_id": 100101, "lock_trainee": True, "parent_ids": [11]})
        self.assertEqual(selection_for_plan({}, self.store, self.master),
            {"card_id": None, "lock_trainee": False, "parent_ids": []})
        with self.assertRaisesRegex(ValueError, "imported collection"):
            selection_for_plan({"target": 100301}, self.store, self.master)

    def test_native_selection_rejects_duplicate_characters_and_unowned_parents(self):
        for identities, message in (([10, 10], "different parent veterans"),
                ([10, 11], "different characters"), ([99], "own imported collection")):
            with self.subTest(identities=identities), self.assertRaisesRegex(ValueError, message):
                selection_for_plan({"parent_ids": identities}, self.store, self.master)
        self.master.cards[100201] = {"chara_id": 1001}
        with self.assertRaisesRegex(ValueError, "same character as a parent"):
            selection_for_plan({"target": 100101, "parent_ids": [10]}, self.store, self.master)
        self.store.import_bytes("trained_chara_data.json", b'[{"trained_chara_id":12,"card_id":100301,"use_type":1}]')
        with self.assertRaisesRegex(ValueError, "own imported collection"):
            selection_for_plan({"parent_ids": [12]}, self.store, self.master)

    def test_native_lineage_uses_six_spark_members_and_caps_initial_aptitude_at_a(self):
        self.master.factors = {3203: {"factor_type": 2, "factor_group_id": 32, "rarity": 3}}
        self.master.names[(147, 3203)] = "Mile"
        self.master._planning_catalog = PlanningCatalog(rarities={100101: {3: {"proper_distance_mile": 6}}})
        factor = [{"factor_id": 3203}]
        parent = {"card_id": 100201, "factor_info_array": factor,
            "succession_chara_array": [{"position_id": pos, "factor_info_array": factor} for pos in (10, 20, 11, 12)]}
        preview = lineage_preview(self.master, {"card_id": 100101, "rarity": 3}, [parent])
        mile = next(row for row in preview["aptitudes"] if row["label"] == "Mile")
        self.assertEqual((mile["stars"], mile["base"], mile["initial"]), (9, 6, 7))
        self.assertEqual(preview["sparks"], {"Pink:32": 9})
        self.assertIsNone(preview["affinity"])

    def test_native_affinity_keeps_missing_g1_records_unknown(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from uma_legacy_linker.parent_optimizer import AffinityResolver
        from uma_workbench.roster_viewer import affinity_preview
        resolver = object.__new__(AffinityResolver)
        resolver.memberships = {identity: {1} for identity in range(1001, 1008)}
        resolver.relation_points = {1: 2}
        races = SimpleNamespace(resolve_g1_saddles=lambda values: {"names": [str(value) for value in values or []]})
        parents = [{"card_id": card, "win_saddle_id_array": [1], "succession_chara_array": [
            {"position_id": pos, "card_id": gp, "win_saddle_id_array": [1]} for pos, gp in zip((10, 20), grandparents)]}
            for card, grandparents in ((100201, (100401, 100501)), (100301, (100601, 100701)))]
        with patch("uma_workbench.roster_viewer._resolvers", return_value=(races, resolver)):
            preview = affinity_preview(self.master, {"card_id": 100101}, parents)
            self.assertEqual(preview, {"base": 14, "g1_bonus": 15, "total": 29, "complete": True})
            del parents[0]["win_saddle_id_array"]
            preview = affinity_preview(self.master, {"card_id": 100101}, parents)
            self.assertEqual(preview["base"], 14)
            self.assertIsNone(preview["total"])
            self.assertIsNone(preview["g1_bonus"])
