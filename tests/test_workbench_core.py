import base64
import gzip
import itertools
import json
import random
import struct
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from uma_workbench.core import MasterData, Store, base_score, decode_skill_events, measured_roster, wilson_interval
from uma_workbench.sync import ExportWatcher


def replay(skill=200001, version=100000002):
    # One horse, no frames, one result and one activation event.
    header = struct.pack("<iifiiiiii", 4, version, 0.0, 1, 12, 31, 0, 0, 16)
    result = bytes(31)
    event = struct.pack("<HfBBii", 14, 1.5, 3, 2, 0, skill)
    raw = header + struct.pack("<i", 0) + result + struct.pack("<ii", 0, 1) + event
    return base64.b64encode(gzip.compress(raw, mtime=0)).decode()


def capture(seed=7, style=1, scenario=None):
    horse = {"frame_order": 1, "trained_chara_id": 42, "card_id": 100101,
             "running_style": style, "skill_array": [{"skill_id": 200001}]}
    scores = [{"score": 1600, "bonus_array": [{"bonus_score": 1000}, {"bonus_score": 100}]}]
    return {"race_start_params_array": [{"round": 1, "race_instance_id": 100,
             "random_seed": seed, "race_horse_data_array": [horse]}],
            "race_result_array": [{"round": 1, "distance_type": 1,
             "race_scenario": scenario if scenario is not None else replay(),
             "chara_result_array": [{"frame_order": 1, "trained_chara_id": 42,
                                     "finish_order": 1, "score_array": scores}]}]}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "profile")

    def tearDown(self):
        self.temp.cleanup()

    def load(self, filename, data):
        return self.store.import_bytes(filename, json.dumps(data).encode())

    def test_snapshot_replacement_validation_and_reactivation(self):
        first = [{"card_id": 100101, "talent_level": 1}]
        second = [{"card_id": 100201, "talent_level": 2}]
        self.load("card_data.json", first)
        self.load("card_data.json", second)
        with self.assertRaises(ValueError):
            self.load("card_data.json", [{"unexpected": 3}])
        self.assertEqual(self.store.entities("trainees"), second)
        self.load("card_data.json", first)
        self.assertEqual(self.store.entities("trainees"), first)
        self.assertEqual(self.load("card_data.json", first)[0], "unchanged")

    def test_duplicate_ids_do_not_replace_collection(self):
        first = [{"card_id": 1, "talent_level": 1}]
        self.load("card_data.json", first)
        with self.assertRaises(ValueError):
            self.load("card_data.json", first * 2)
        self.assertEqual(self.store.entities("trainees"), first)

    def test_account_separation(self):
        self.load("support_card_data.json", [{"support_card_id": 1, "viewer_id": 123}])
        with self.assertRaises(ValueError):
            self.load("trained_chara_data.json", [{"trained_chara_id": 1, "viewer_id": 456}])
        self.assertEqual(self.store.entities("veterans"), [])

    def test_capture_envelope_and_deduplication(self):
        d = capture()
        self.load("one.json", {"data": d})
        self.load("two.json", d)
        # Additional capture metadata must not duplicate the race.
        self.load("three.json", {**d, "last_checked_round": 5})
        self.assertEqual(self.store.counts()["races"], 1)
        self.assertEqual(self.store.counts()["captures"], 2)
        self.assertEqual(self.store.metrics()[0]["mean"], 500)
        self.assertEqual(self.store.skill_metrics()[0]["rate"], 1)

    def test_different_styles_form_separate_cohorts(self):
        self.load("one.json", capture(seed=1))
        self.load("two.json", capture(seed=2, style=2))
        self.assertEqual(len(self.store.cohorts()), 2)
        self.assertEqual(len(self.store.metrics()), 2)

    def test_bad_replay_does_not_create_false_skill_failure(self):
        _, warnings = self.load("bad.json", capture(scenario=replay(version=999)))
        self.assertTrue(warnings)
        self.assertEqual(self.store.metrics()[0]["mean"], 500)
        self.assertEqual(self.store.metrics()[0]["decoded_races"], 0)
        self.assertEqual(self.store.skill_metrics(), [])

    def test_zip_reads_json_without_extracting_executables_or_paths(self):
        path = Path(self.temp.name) / "dump.zip"
        with ZipFile(path, "w") as archive:
            archive.writestr("../card_data.json", json.dumps([{"card_id": 1}]))
            archive.writestr("umadump.exe", b"do not execute")
        report = self.store.import_path(path)
        self.assertEqual(report["imported"], 1)
        self.assertFalse((Path(self.temp.name) / "card_data.json").exists())
        self.assertFalse((Path(self.temp.name) / "umadump.exe").exists())

    def test_watcher_retries_partial_write_and_skips_unchanged(self):
        folder = Path(self.temp.name) / "exports"
        folder.mkdir()
        path = folder / "card_data.json"
        path.write_text('[{"card_id":')
        watcher = ExportWatcher(self.store, folder, lambda result: None)
        self.assertTrue(watcher.poll_once()["errors"])
        path.write_text('[{"card_id": 123}]')
        self.assertEqual(watcher.poll_once()["imported"], 1)
        self.assertEqual(watcher.poll_once()["imported"], 0)
        self.assertEqual(self.store.entities("trainees")[0]["card_id"], 123)

    def test_goal_prerequisites_and_resource_calculation(self):
        parent = self.store.save_goal("Build parent", {"prerequisites": []})
        ace = self.store.save_goal("Train ace", {"prerequisites": [parent]})
        with self.assertRaises(ValueError):
            self.store.change_goal_status(ace, "In progress")
        self.store.change_goal_status(parent, "Complete")
        self.store.change_goal_status(ace, "In progress")
        with self.assertRaises(ValueError):
            self.store.save_goal("Invalid", {"prerequisites": [99]})
        self.store.save_resource("Star Pieces", 121, 150, 3)
        self.assertEqual(self.store.resources()[0]["runs"], 10)
        with self.assertRaises(ValueError):
            self.store.save_resource("Invalid", "nan", 150, 3)

    def test_handoff_keeps_original_file_unchanged(self):
        original = Path(self.temp.name) / "trained_chara_data.json"
        original.write_text('[{"trained_chara_id": 42, "factor_info_array": []}]')
        before = original.read_bytes()
        self.store.import_path(original)
        handoff = self.store.lineage_export()
        self.assertEqual(original.read_bytes(), before)
        self.assertNotEqual(original, handoff)
        self.assertEqual(json.loads(handoff.read_text())[0]["trained_chara_id"], 42)


class MathTests(unittest.TestCase):
    def test_exact_bonus_subtraction_with_negative_penalties(self):
        self.assertEqual(base_score([{"score": 20420, "bonus_array": [{"bonus_score": 11652}, {"bonus_score": 1268}]},
                                     {"score": -500, "bonus_array": []}]), 7000)

    def test_replay_event_and_corruption(self):
        self.assertEqual(decode_skill_events(replay())[0][0]["skill_id"], 200001)
        with self.assertRaises(ValueError):
            decode_skill_events(replay(version=999))
        with self.assertRaises((ValueError, EOFError, OSError)):
            decode_skill_events("AAAA")

    def test_wilson_interval_conveys_small_sample_uncertainty(self):
        low, high = wilson_interval(3, 6)
        self.assertAlmostEqual(low, 0.187616, places=5)
        self.assertAlmostEqual(high, 0.812384, places=5)
        self.assertEqual(wilson_interval(0, 0), (0, 1))

    def test_assignment_matches_exhaustive_oracle(self):
        rng = random.Random(12)
        for _ in range(12):
            metrics, branches = [], []
            for chara in range(1, 6):
                options = [None]
                for division in (1, 2):
                    style = rng.choice((1, 2, 3))
                    r = {"veteran_id": str(chara), "card_id": chara * 100 + 1,
                         "division": division, "style": style, "races": 5,
                         "mean": 100, "lower_score": rng.randrange(1, 100)}
                    metrics.append(r)
                    options.append(r)
                branches.append(options)
            class FakeStore:
                def entities(self, kind):
                    return [{"trained_chara_id": x} for x in range(1, 6)]
                def metrics(self):
                    return metrics
            result = measured_roster(FakeStore(), MasterData(), distinct_styles=True)
            best = (0, 0)
            for product in itertools.product(*branches):
                chosen = [r for r in product if r]
                roles = [(r["division"], r["style"]) for r in chosen]
                if len(set(roles)) != len(roles):
                    continue
                if any(sum(r["division"] == d for r in chosen) > 3 for d in (1, 2)):
                    continue
                best = max(best, (len(chosen), sum(r["lower_score"] for r in chosen)))
            self.assertEqual((len(result["selected"]), result["objective"]), best)


class SupportLevelTests(unittest.TestCase):
    def test_level_uses_rarity_experience_thresholds_and_limit_break_cap(self):
        master = MasterData()
        master.supports = {1: {"rarity": 1}}
        master.support_levels = [
            {"rarity": 1, "level": 1, "total_exp": 0},
            {"rarity": 1, "level": 2, "total_exp": 5},
            {"rarity": 1, "level": 3, "total_exp": 15},
            {"rarity": 2, "level": 10, "total_exp": 5},
        ]
        master.support_limits = {1: {"limit_0": 2, "limit_1": 3}}
        self.assertEqual(master.support_level({"support_card_id": 1, "exp": 10}), 2)
        self.assertEqual(master.support_level({"support_card_id": 1, "exp": 50}), 2)
        self.assertEqual(master.support_level({"support_card_id": 1, "exp": 50, "limit_break_count": 1}), 3)
        self.assertIsNone(master.support_level({"support_card_id": 99, "exp": 50}))


if __name__ == "__main__":
    unittest.main()
