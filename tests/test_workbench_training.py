import json
from pathlib import Path
import tempfile
import unittest

from uma_workbench.core import MasterData, Store
from uma_workbench.training import (
    COMMANDS, DEFAULT_OPTIONS, SCENARIOS, STATS, SUMMER, SupportProfile, TrainingData,
    TrainingModel, completed_career_comparison, curve_value, options_for,
    participant_distribution, session_gains, support_profile, validate_recorded_practices,
)


def training_data():
    data = TrainingData()
    early = {
        101: {"speed": 11, "power": 6, "skill_points": 4, "energy": -21},
        105: {"stamina": 10, "guts": 6, "skill_points": 4, "energy": -19},
        102: {"stamina": 6, "power": 9, "skill_points": 4, "energy": -20},
        103: {"speed": 5, "power": 5, "guts": 8, "skill_points": 4, "energy": -22},
        106: {"speed": 2, "wiz": 10, "skill_points": 5, "energy": 5},
    }
    late = {
        101: {"speed": 15, "power": 8, "skill_points": 4, "energy": -27},
        105: {"stamina": 14, "guts": 8, "skill_points": 4, "energy": -25},
        102: {"stamina": 8, "power": 13, "skill_points": 4, "energy": -26},
        103: {"speed": 6, "power": 5, "guts": 13, "skill_points": 4, "energy": -28},
        106: {"speed": 4, "wiz": 14, "skill_points": 5, "energy": 5},
    }
    for command in COMMANDS:
        data.bases[1, command] = early[command]
        data.bases[1, SUMMER[command]] = late[command]
    data.effects = {1: [{"type": 8, "init": 0}]}
    return data


def profile(identity=1, kind="speed", base=None, unique=None, special=None):
    return SupportProfile(identity, kind, 50, base or {}, unique or {}, special or [], [], dict.fromkeys(STATS, 0))


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.data = training_data()
        self.master = MasterData()
        self.master.supports = {1: {"rarity": 3, "effect_table_id": 1, "unique_effect_id": 1, "command_id": 101}}
        self.master.support_limits = {3: {"limit_0": 30, "limit_1": 35, "limit_2": 40, "limit_3": 45, "limit_4": 50}}

    def test_unlocked_curves_interpolate_and_unavailable_anchors_are_not_zero(self):
        self.assertEqual(curve_value({"init": -1, "limit_lv35": 1, "limit_lv50": 2}, 34), 0)
        self.assertEqual(curve_value({"init": -1, "limit_lv35": 1, "limit_lv50": 2}, 35), 1)
        self.assertEqual(curve_value({"init": 10, "limit_lv5": -1, "limit_lv15": 20}, 8), 15)
        self.assertEqual(curve_value({"init": 10, "limit_lv15": 20}, 50), 20)

    def test_effects_use_owned_level_and_limit_breaks_and_unlock_unique(self):
        self.data.effects[1] = [{"type": 8, "init": 0, "limit_lv30": 5, "limit_lv50": 15}]
        self.data.uniques[1] = {"lv": 35, "type_0": 8, "value_0": 5}
        low = support_profile(self.master, self.data, {"support_card_id": 1, "level": 50, "limit_break_count": 0}, DEFAULT_OPTIONS)
        high = support_profile(self.master, self.data, {"support_card_id": 1, "level": 50, "limit_break_count": 4}, DEFAULT_OPTIONS)
        self.assertEqual((low.level, low.base[8], low.unique), (30, 5, {}))
        self.assertEqual((high.level, high.base[8], high.unique[8]), (50, 15, 5))
        self.assertIn("Effects capped", low.notes[0])

    def test_borrowed_levels_are_explicit_and_unknown_owned_levels_stay_unknown(self):
        opts = {**DEFAULT_OPTIONS, "borrowed_level": 50, "borrowed_limit_breaks": 0}
        borrowed = support_profile(self.master, self.data, {"support_card_id": 1, "borrowed": True}, opts)
        unknown = support_profile(self.master, self.data, {"support_card_id": 1}, DEFAULT_OPTIONS)
        self.assertEqual(borrowed.level, 30)
        self.assertIsNone(unknown.level)
        self.assertTrue(any("Level unknown" in text for text in unknown.notes))

    def test_facility_values_follow_scenario_endpoints_and_known_intermediate_steps(self):
        self.assertEqual(self.data.base(1, 101, 3), {"speed": 13, "stamina": 0, "power": 6, "guts": 0, "wiz": 0, "skill_points": 4, "energy": -23})
        self.assertEqual(self.data.base(1, 103, 4)["guts"], 12)
        self.assertEqual(self.data.base(1, 103, 4)["speed"], 5)
        self.assertEqual(self.data.base(1, 106, 4)["speed"], 3)
        self.assertEqual(SCENARIOS["Our Grand Concert"], 3)
        self.assertEqual(SCENARIOS["Trackblazer"], 4)
        with self.assertRaises(ValueError):
            self.data.base(5, 101, 1)

    def test_single_practice_matches_independently_calculated_compound_bonuses(self):
        cards = [profile(1, base={1: 25, 2: 30, 3: 1, 8: 10}, unique={1: 10}),
            profile(2, base={1: 15, 2: 20, 8: 15})]
        result = session_gains(self.data, 1, 101, 3, cards, {"speed": 20}, bonds=[80, 100])
        # Speed: 14 × 1.2 × 1.3 × 1.25 × 1.25 × 1.10 × 1.15 × 1.10.
        self.assertEqual(result["speed"], 47)
        self.assertEqual(result["power"], 16)
        self.assertEqual(result["skill_points"], 11)
        self.assertEqual(result["stamina"], 0)

    def test_friendship_requires_matching_type_and_bond_and_does_not_add_bonus_to_zero_base(self):
        card = profile(base={1: 50, 4: 20})
        before = session_gains(self.data, 1, 101, 1, [card], {}, motivation=3, bonds=[79])
        after = session_gains(self.data, 1, 101, 1, [card], {}, motivation=3, bonds=[80])
        wrong = session_gains(self.data, 1, 105, 1, [card], {}, motivation=3, bonds=[100])
        self.assertEqual((before["speed"], after["speed"]), (11, 17))
        self.assertEqual(wrong["stamina"], 31)
        self.assertEqual(after["stamina"], 0)

    def test_conditional_uniques_obey_bond_and_off_specialty_rules(self):
        card = profile(special=[(101, [80, 8, 10, 3, 1]), (102, [80, 20, 0, 0, 0])])
        low = session_gains(self.data, 1, 101, 1, [card], {}, motivation=3, bonds=[79])
        high = session_gains(self.data, 1, 101, 1, [card], {}, motivation=3, bonds=[80])
        off = session_gains(self.data, 1, 105, 1, [card], {}, motivation=3, bonds=[80])
        self.assertEqual((low["speed"], high["speed"], off["stamina"]), (11, 13, 13))

    def test_wit_friendship_recovers_energy_and_energy_cost_reduction_is_additive(self):
        wit = session_gains(self.data, 1, 106, 1, [profile(kind="wiz", base={31: 5})], {}, bonds=[80])
        speed = session_gains(self.data, 1, 101, 1, [profile(base={28: 10}), profile(2, base={28: 10})], {})
        self.assertEqual(wit["energy"], 10)
        self.assertEqual(speed["energy"], -17)

    def test_session_and_post_1200_caps_apply_at_the_gain_boundary(self):
        large = session_gains(self.data, 1, 101, 5, [profile(base={3: 200})], {}, current={"speed": 1190})
        self.assertEqual(large["speed"], 55)
        above = session_gains(self.data, 1, 101, 1, [], {}, motivation=3, current={"speed": 1201})
        self.assertEqual(above["speed"], 5)

    def test_placement_distribution_is_normalized_and_never_exceeds_five_members(self):
        cards = [profile(i, base={19: 80}, unique={19: 20}) for i in range(6)]
        outcomes = participant_distribution(cards, "speed")
        self.assertAlmostEqual(sum(outcomes.values()), 1)
        self.assertTrue(all(len(ids) <= 5 for ids in outcomes))
        expected_presence = (2.16 / 6.66) * 6
        # Six simultaneous arrivals lose one support.
        self.assertAlmostEqual(sum(len(ids) * probability for ids, probability in outcomes.items()), expected_presence - (2.16 / 6.66) ** 6)

    def test_disabled_or_unavailable_models_do_not_claim_estimates(self):
        model = TrainingModel(self.master, TrainingData(), {})
        self.assertFalse(model.available)
        self.assertIsNone(model.estimate({"card_id": 1}, []))
        self.assertFalse(TrainingModel(self.master, self.data, {"training": {"enabled": False}}).available)

    def test_practice_counts_reject_impossible_or_fractional_plans(self):
        for sessions in ({"speed": 79}, {"speed": .5}, dict.fromkeys(STATS, 0), dict.fromkeys(STATS, 20)):
            with self.assertRaises(ValueError):
                options_for({"training": {"sessions": sessions}})
        self.assertEqual(sum(options_for({})["sessions"].values()), 50)

    def test_search_can_prefer_lower_level_card_when_its_training_output_is_better(self):
        from tests.test_workbench_planning import PlanningTests
        from uma_workbench.planning import find_setups
        fixture = PlanningTests("test_requirements_search_compares_trainees_without_choosing_one")
        fixture.setUp()
        try:
            fixture.catalog.training_data = self.data
            for identity, card in fixture.master.supports.items():
                card.update(command_id=101, effect_table_id=identity)
                self.data.effects[identity] = [{"type": 8, "init": 0}]
            self.data.effects[37] = [{"type": 8, "init": 40}]
            fixture.load("support_card_data.json", [{"support_card_id": identity, "level": 30 if identity == 37 else 50} for identity in range(31, 38)])
            result = find_setups(fixture.store, fixture.master, {**fixture.requirements, "card_id": 100201,
                "skill_ids": [], "scenario": "URA"}, catalog=fixture.catalog)
            self.assertTrue(result["training_enabled"])
            chosen = {row["support_card_id"] for row in result["setups"][0]["supports"]}
            self.assertIn(37, chosen)
            self.assertNotIn(31, chosen)
        finally:
            fixture.tearDown()

    def test_recorded_preview_check_deduplicates_and_skips_disabled_or_npc_practices(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp))
            self.master.cards = {100101: {"talent_speed": 20}}
            snapshot = {"single_mode_load_common": {"chara_info": {"card_id": 100101,
                "scenario_id": 1, "turn": 10, "motivation": 4}, "home_info": {"command_info_array": [
                    {"command_id": 101, "level": 3, "is_enable": 1, "training_partner_array": [],
                    "params_inc_dec_info_array": [{"target_type": 1, "value": 17}, {"target_type": 3, "value": 6}, {"target_type": 30, "value": 4}]},
                    {"command_id": 106, "level": 1, "is_enable": 0},
                    {"command_id": 105, "level": 1, "is_enable": 1, "training_partner_array": [1001]}]}}}
            store.import_bytes("turn_010.json", json.dumps(snapshot).encode())
            snapshot["ignored_server_field"] = 2
            store.import_bytes("turn_010_repeat.json", json.dumps(snapshot).encode())
            report = validate_recorded_practices(store, self.master, self.data)
            self.assertEqual((report["checked"], report["exact"]), (1, 1))
            self.assertEqual(report["skipped"], {"Scenario teammates": 1})
            from uma_workbench.planning import PlanningCatalog, find_setups
            # A later import contradicts the model. Search remains usable while
            # refusing to rank decks with the disputed practice estimate.
            snapshot["single_mode_load_common"]["chara_info"]["turn"] = 11
            snapshot["single_mode_load_common"]["home_info"]["command_info_array"][0]["params_inc_dec_info_array"][0]["value"] = 99
            store.import_bytes("turn_011.json", json.dumps(snapshot).encode())
            store.import_bytes("card_data.json", json.dumps([{"card_id": 100101, "talent_level": 1}]).encode())
            catalog = PlanningCatalog(training_data=self.data)
            result = find_setups(store, self.master, {"scenario": "URA"}, catalog=catalog)
            self.assertFalse(result["training_enabled"])
            self.assertIn("disagreed", result["training_restriction"])
            self.assertTrue(result["setups"])

    def test_history_is_scoped_to_character_scenario_and_owned_veterans(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp))
            rows = [{"trained_chara_id": identity, "card_id": 100101, "factor_info_array": [],
                "scenario_id": 1 if identity != 2 else 2, "use_type": int(identity == 3),
                "support_card_list": [{"support_card_id": i} for i in range(1, 7)], "speed": 1100}
                for identity in range(1, 4)]
            store.import_bytes("trained_chara_data.json", json.dumps(rows).encode())
            report = completed_career_comparison(store, {"scenario": "URA"}, 100101, [{"support_card_id": i} for i in range(1, 7)])
            self.assertEqual((report["count"], report["same_deck_count"]), (1, 1))
            self.assertEqual(report["rows"][0]["stats"]["speed"], 1100)
