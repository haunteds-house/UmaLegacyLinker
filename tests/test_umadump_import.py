from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from uma_legacy_linker.account_store import AccountStore
from uma_legacy_linker.umadump_import import import_umadump_directory, locate_umadump_root


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class UmadumpImportTests(unittest.TestCase):
    def make_dump(self, root: Path) -> None:
        write_json(
            root / "card_data.json",
            [{"card_id": 100101, "rarity": 3, "talent_level": 4, "skill_data_array": []}],
        )
        write_json(
            root / "support_card_data.json",
            [{
                "support_card_id": 30001,
                "limit_break_count": 4,
                "exp": 100,
                "extra_data": {"level": 50, "max_level": 50},
            }],
        )
        write_json(
            root / "trained_chara_data.json",
            [{"trained_chara_id": 42, "card_id": 100101, "rank_score": 12345}],
        )
        write_json(
            root / "race_replays" / "team_stadium" / "TT-20260101_120000_000.json",
            {
                "support_card_bonus": 12,
                "race_result_array": [
                    {
                        "round": 1,
                        "team_total_score": 5000,
                        "win_type": 1,
                        "chara_result_array": [{"trained_chara_id": 42}],
                        "race_scenario": "abc",
                    }
                ],
            },
        )
        archive = root / "career_data" / "run-1"
        write_json(
            archive / "manifest.json",
            {
                "archive_type": "umadump-career",
                "dumper_version": "2.8.0",
                "identity": {"card_id": 100101, "scenario_id": 2},
            },
        )
        write_json(
            archive / "turns" / "turn_013_002.json",
            {"single_mode_load_common": {"chara_info": {"turn": 13}}},
        )
        write_json(archive / "events.json", {"events": []})
        write_json(root / "trophy_data_limited.json", [{"trophy_id": 1}])

    def test_imports_collection_races_and_career_and_is_incremental(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            outer = Path(temp) / "outer"
            root = outer / "Umadump"
            root.mkdir(parents=True)
            self.make_dump(root)
            db = Path(temp) / "account.sqlite3"

            self.assertEqual(locate_umadump_root(outer), root.resolve())
            first = import_umadump_directory(outer, db)
            assert first.summary is not None
            self.assertEqual(first.summary.trainee_cards, 1)
            self.assertEqual(first.summary.support_cards, 1)
            self.assertEqual(first.summary.active_veterans, 1)
            self.assertEqual(first.summary.team_stadium_captures, 1)
            self.assertEqual(first.summary.career_archives, 1)
            self.assertEqual(first.summary.career_snapshots, 1)
            self.assertEqual(first.summary.documents, 1)
            self.assertEqual(first.failed_files, 0)

            second = import_umadump_directory(outer, db)
            self.assertEqual(second.imported_files, 0)
            self.assertGreater(second.unchanged_files, 0)
            assert second.summary is not None
            self.assertEqual(second.summary.team_stadium_captures, 1)

            with AccountStore(db) as store:
                race_rows = store.connection.execute(
                    "SELECT COUNT(*) FROM team_stadium_races"
                ).fetchone()[0]
                self.assertEqual(race_rows, 1)

    def test_changed_static_export_updates_current_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Umadump"
            root.mkdir(parents=True)
            self.make_dump(root)
            db = Path(temp) / "account.sqlite3"
            import_umadump_directory(root, db)

            write_json(
                root / "support_card_data.json",
                [{
                    "support_card_id": 30001,
                    "limit_break_count": 4,
                    "exp": 200,
                    "extra_data": {"level": 45, "max_level": 50},
                }],
            )
            report = import_umadump_directory(root, db)
            self.assertEqual(report.imported_files, 1)
            with AccountStore(db) as store:
                row = store.connection.execute(
                    "SELECT level, exp FROM owned_supports WHERE support_card_id = 30001"
                ).fetchone()
                self.assertEqual((row[0], row[1]), (45, 200))


if __name__ == "__main__":
    unittest.main()
