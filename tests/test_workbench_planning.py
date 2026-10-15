import itertools
import json
from pathlib import Path
import random
import tempfile
import unittest

from uma_workbench.core import MasterData, Store
from uma_workbench.goals import validate_training_goal
from uma_workbench.planning import PlanningCatalog, _deck_frontier, find_setups, matching_veterans
from uma_workbench.calculators import awakening_costs, concert_budget, material_budget, skill_budget


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.master = MasterData()
        self.master.cards = {identity: {"chara_id": identity // 100, "default_rarity": 3,
            "available_skill_set_id": identity, "talent_group_id": identity}
            for identity in (100101, 100201, 100301, 100401, 100501)}
        self.master.supports = {identity: {"chara_id": 3000 + index, "rarity": 3}
            for index, identity in enumerate(range(31, 37))}
        self.master.supports[37] = {"chara_id": 3000, "rarity": 3}
        self.master.factors = {3201: {"factor_type": 2, "factor_group_id": 32, "rarity": 1},
            3203: {"factor_type": 2, "factor_group_id": 32, "rarity": 3},
            1103: {"factor_type": 2, "factor_group_id": 11, "rarity": 3},
            10101: {"factor_type": 4, "factor_group_id": 1, "rarity": 1}}
        self.catalog = PlanningCatalog()
        self.catalog.skills = {101: {"group_id": 1, "group_rate": 1, "rarity": 1},
            102: {"group_id": 1, "group_rate": 2, "rarity": 2},
            103: {"group_id": 1, "group_rate": -1, "rarity": 1},
            201: {"group_id": 2, "group_rate": 1, "rarity": 1, "condition_1": "running_style==4"}}
        self.catalog.costs = {101: 100, 102: 200, 103: 50}
        self.catalog.available_skills = {100101: {101: 0, 102: 3}}
        self.catalog.support_events = {31: {102}}
        self.catalog.support_hints = {32: {101}, 33: {201}}
        self.catalog.hint_data_available = True
        self.catalog.rarities = {100101: {3: {"proper_ground_turf": 7, "proper_distance_mile": 6,
            "proper_running_style_senko": 7}}, 100201: {3: {"proper_ground_turf": 7,
            "proper_distance_mile": 7, "proper_running_style_senko": 7}}}
        self.master._planning_catalog = self.catalog
        for name, rows in (
            ("card_data.json", [{"card_id": 100101, "rarity": 3, "talent_level": 3},
                {"card_id": 100201, "rarity": 3, "talent_level": 1}]),
            ("support_card_data.json", [{"support_card_id": identity, "level": 40 if identity == 31 else 50} for identity in range(31, 38)]),
            ("trained_chara_data.json", [
                {"trained_chara_id": 10, "card_id": 100201, "factor_info_array": [{"factor_id": 3201}, {"factor_id": 10101}]},
                {"trained_chara_id": 11, "card_id": 100301, "factor_info_array": []},
                {"trained_chara_id": 12, "card_id": 100401, "use_type": 1, "factor_info_array": [{"factor_id": 3203}]},
                {"trained_chara_id": 13, "card_id": 100501, "factor_info_array": []}]),
        ):
            self.load(name, rows)
        self.requirements = {"role": "TT", "card_id": None, "surface": "Turf", "distance_type": "Mile",
            "style": "Pace Chaser", "minimum_aptitude": 7, "aptitudes": {}, "skill_ids": [102],
            "stats": {}, "deck_ids": [], "parent_ids": [], "max_attempts": 10, "stop_condition": "Reach targets"}

    def tearDown(self):
        self.temp.cleanup()

    def load(self, name, data):
        return self.store.import_bytes(name, json.dumps(data).encode())

    def search(self, **changes):
        return find_setups(self.store, self.master, {**self.requirements, **changes}, catalog=self.catalog)

    def test_requirements_search_compares_trainees_without_choosing_one(self):
        validate_training_goal(self.requirements, self.store, self.master)
        result = self.search()
        self.assertEqual(result["trainees_examined"], 2)
        self.assertEqual({row["card_id"] for row in result["setups"]}, {100101, 100201})
        first = result["setups"][0]
        self.assertEqual(first["card_id"], 100101)
        self.assertEqual(first["missing_skills"], [])
        self.assertEqual(first["aptitude_gap"], 0)
        self.assertEqual(first["slot_gap"], 0)

    def test_decks_and_parents_obey_character_and_ownership_constraints(self):
        for row in self.search()["setups"]:
            characters = [self.master.supports[support["support_card_id"]]["chara_id"] for support in row["supports"]]
            self.assertEqual(len(characters), len(set(characters)))
            self.assertNotIn(self.master.character_id(row["card_id"]), characters)
            parents = row["parents"]
            self.assertNotIn(12, [parent["trained_chara_id"] for parent in parents])
            parent_characters = [self.master.character_id(parent["card_id"]) for parent in parents]
            self.assertEqual(len(parent_characters), len(set(parent_characters)))
            self.assertNotIn(self.master.character_id(row["card_id"]), parent_characters)

    def test_white_skill_hint_and_learned_parent_skill_do_not_unlock_gold(self):
        self.catalog.support_events.clear()
        self.catalog._event_cache.clear()
        row = self.search(card_id=100201)["setups"][0]
        self.assertIn(102, row["missing_skills"])
        self.assertEqual(row["skills"][0]["sources"], [])

    def test_awakening_level_limits_trainee_skill_access(self):
        self.assertIn(102, self.catalog.base_skills(self.master, {"card_id": 100101, "talent_level": 3, "rarity": 3}))
        self.assertNotIn(102, self.catalog.base_skills(self.master, {"card_id": 100101, "talent_level": 1, "rarity": 3}))

    def test_exact_distance_sets_the_aptitude_group_and_conflicts_are_rejected(self):
        from uma_workbench.planning import distance_group, requirements_aptitudes
        for distance, group in ((1400, "Sprint"), (1401, "Mile"), (1800, "Mile"), (1801, "Medium"), (2400, "Medium"), (2401, "Long")):
            self.assertEqual(distance_group({"distance": distance}), group)
        targets = requirements_aptitudes({**self.requirements, "distance": 1600, "distance_type": "Any distance"})
        self.assertEqual(targets["proper_distance_mile"], 7)
        with self.assertRaisesRegex(ValueError, "belongs to Mile"):
            validate_training_goal({**self.requirements, "distance": 1600, "distance_type": "Long"}, self.store, self.master)

    def test_fixed_choices_are_respected_and_incompatible_ones_do_not_sneak_in(self):
        result = self.search(card_id=100101, parent_ids=[10], deck_ids=[31])
        self.assertTrue(result["setups"])
        for row in result["setups"]:
            self.assertEqual(row["card_id"], 100101)
            self.assertIn(10, [parent["trained_chara_id"] for parent in row["parents"]])
            self.assertIn(31, [support["support_card_id"] for support in row["supports"]])
        self.assertEqual(self.search(card_id=100101, deck_ids=[31, 37])["setups"], [])

    def test_inheritance_counts_two_grandparents_and_caps_the_starting_gain(self):
        self.catalog.rarities[100101][3]["proper_ground_turf"] = 1
        veterans = self.store.entities("veterans")
        for row in veterans:
            row["factor_info_array"] = [{"factor_id": 1103}]
            row["succession_chara_array"] = [{"position_id": position, "factor_info_array": [{"factor_id": 1103}]} for position in (10, 20, 11)]
        self.load("trained_chara_data.json", veterans)
        result = self.search(card_id=100101, skill_ids=[])["setups"][0]
        turf = next(row for row in result["aptitudes"] if row["label"] == "Turf")
        self.assertEqual(turf["stars"], 18)
        self.assertEqual(turf["initial"], 5)
        self.assertEqual(turf["gap"], 2)

    def test_s_target_is_conditional_and_needs_a_matching_spark(self):
        row = self.search(card_id=100101, aptitudes={"proper_distance_mile": 8})["setups"][0]
        mile = next(row for row in row["aptitudes"] if row["label"] == "Mile")
        self.assertTrue(mile["needs_s_roll"])
        self.assertEqual(mile["initial"], 7)
        self.assertEqual(mile["gap"], 0)

    def test_profile_incompatible_skills_are_reported_even_if_a_hint_exists(self):
        result = self.search(skill_ids=[201])
        self.assertEqual(result["blocked_skills"], [201])
        for row in result["setups"]:
            self.assertIn(201, row["missing_skills"])
            self.assertTrue(row["skills"][0]["incompatible"])

    def test_support_frontier_matches_exhaustive_small_collection_oracle(self):
        rng = random.Random(17)
        for _ in range(15):
            wanted = [101, 201, 301]
            catalog = PlanningCatalog()
            catalog.hint_data_available = True
            ids = [31, 32, 33, 37]
            for sid in ids:
                catalog.support_hints[sid] = {skill for skill in wanted if rng.randrange(2)}
            supports = [{"support_card_id": sid, "level": rng.randrange(1, 51)} for sid in ids]
            frontier = _deck_frontier(self.master, catalog, supports, 9000, wanted, (), lambda: None)
            oracle = {}
            for combination in itertools.combinations(supports, 3):
                chars = [self.master.supports[row["support_card_id"]]["chara_id"] for row in combination]
                if len(set(chars)) != len(chars):
                    continue
                skills = set().union(*(catalog.support_hints[row["support_card_id"]] for row in combination))
                mask = sum(1 << index for index, sid in enumerate(wanted) if sid in skills)
                oracle[mask] = max(oracle.get(mask, 0), sum(row["level"] for row in combination))
            self.assertEqual({mask: quality for mask, quality, _rows, _pruned in frontier}, oracle)

    def test_collection_checker_accepts_upgraded_skills_and_excludes_borrowed(self):
        self.load("trained_chara_data.json", [
            {"trained_chara_id": identity, "card_id": 100101, "speed": 1000,
                "proper_ground_turf": 7, "proper_distance_mile": 7, "proper_running_style_senko": 7,
                "skill_array": [{"skill_id": 102}], "use_type": int(identity == 2)} for identity in (1, 2)])
        rows = matching_veterans(self.store, self.master, {**self.requirements, "skill_ids": [101], "stats": {"speed": 900}})
        self.assertEqual([row["trained_chara_id"] for row in rows], [1])

    def test_editing_a_requirement_plan_keeps_identity_and_rejects_cycles(self):
        first = self.store.save_goal("Requirements", self.requirements)
        second = self.store.save_goal("Dependent", {**self.requirements, "prerequisites": [first]})
        self.store.update_goal(first, "A chosen setup", {**self.requirements, "card_id": 100101})
        self.assertEqual(self.store.goals()[0]["id"], first)
        self.assertEqual(self.store.goals()[0]["details"]["card_id"], 100101)
        with self.assertRaisesRegex(ValueError, "circular"):
            self.store.update_goal(first, "Cycle", {**self.requirements, "prerequisites": [second]})


class CalculatorTests(unittest.TestCase):
    def setUp(self):
        self.catalog = PlanningCatalog()
        self.catalog.skills = {1: {"group_id": 1, "group_rate": 1},
            2: {"group_id": 1, "group_rate": 2}, 3: {"group_id": 1, "group_rate": -1}}
        self.catalog.costs = {1: 100, 2: 180, 3: 50}

    def test_skill_budget_counts_prerequisites_once_and_removes_learned_steps(self):
        result = skill_budget(self.catalog, {1, 2}, budget=300)
        self.assertEqual(result["total"], 280)
        self.assertEqual(result["remaining"], 20)
        self.assertNotIn(3, [row["skill_id"] for row in result["rows"]])
        self.assertEqual(skill_budget(self.catalog, {2}, learned={1})["total"], 180)
        self.assertEqual(skill_budget(self.catalog, {2}, learned={2})["total"], 0)

    def test_skill_budget_uses_entered_prices_and_does_not_assume_unknown_is_free(self):
        self.assertEqual(skill_budget(self.catalog, {2}, paid_prices={1: 0, 2: 120})["total"], 120)
        result = skill_budget(self.catalog, {999}, budget=100)
        self.assertEqual(result["unknown"], [999])
        self.assertIsNone(result["remaining"])
        with self.assertRaises(ValueError):
            skill_budget(self.catalog, {2}, paid_prices={2: -1})

    def test_awakening_costs_use_current_level_and_report_missing_data(self):
        master = MasterData()
        master.cards = {100101: {"talent_group_id": 1}}
        self.catalog.upgrades = [{"talent_group_id": 1, "talent_level": level, "item_id_1": 10, "item_num_1": level * 5}
            for level in (2, 3, 5)]
        self.catalog.texts[(23, 10)] = "Racing shoes"
        master._planning_catalog = self.catalog
        result = awakening_costs(master, 100101, 2, 5)
        self.assertEqual(result["items"][0]["needed"], 40)
        self.assertEqual(result["items"][0]["name"], "Racing shoes")
        self.assertEqual(result["missing_levels"], [4])
        with self.assertRaises(ValueError):
            awakening_costs(master, 100101, 5, 2)

    def test_material_runs_round_up_and_already_covered_items_need_zero_runs(self):
        result = material_budget([{"item_id": 1, "needed": 10}, {"item_id": 2, "needed": 5}], {1: 7, 2: 5}, {1: 2})
        self.assertEqual(result[0]["runs"], 2)
        self.assertEqual(result[1]["runs"], 0)
        self.assertIsNone(material_budget([{"item_id": 1, "needed": 2}], {}, {})[0]["runs"])

    def test_concert_costs_are_separate_currencies_and_bought_songs_are_removed(self):
        songs = [{"id": 1, "costs": [5, 0, 10, 0, 2]}, {"id": 2, "costs": [0, 3, 0, 4, 0]}]
        result = concert_budget(songs, {1, 2}, {1}, [1, 2, 3, 6, 8])
        self.assertEqual(result["costs"], [0, 3, 0, 4, 0])
        self.assertEqual(result["missing"], [0, 1, 0, 0, 0])
        self.assertEqual(result["songs_to_buy"], 1)
        with self.assertRaises(ValueError):
            concert_budget(songs, {1}, set(), [0, -1, 0, 0, 0])
