from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uma_legacy_linker.account_store import AccountStore, decompress_payload


class AccountStoreTests(unittest.TestCase):
    def test_manual_value_overrides_automatic_without_destroying_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "account.sqlite3"
            with AccountStore(db) as store:
                store.set_automatic_value("goddess_statues", 120, source="umadump")
                store.set_manual_value("goddess_statues", 135, unit="statues")
                store.commit()
                value = store.get_value("goddess_statues")
                assert value is not None
                self.assertEqual(value["value"], 135)
                self.assertEqual(value["source"], "manual")
                self.assertEqual(value["automatic_value"], 120)

                store.set_manual_value("goddess_statues", None)
                store.commit()
                fallback = store.get_value("goddess_statues")
                assert fallback is not None
                self.assertEqual(fallback["value"], 120)
                self.assertEqual(fallback["source"], "umadump")

    def test_veterans_become_historical_instead_of_being_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "account.sqlite3"
            source = Path(temp) / "trained_chara_data.json"
            source.write_text("[]", encoding="utf-8")
            with AccountStore(db) as store:
                source_id = store.record_source(
                    source,
                    source_root=temp,
                    kind="veterans",
                    sha256="a" * 64,
                    size_bytes=2,
                    mtime_ns=1,
                )
                store.replace_veterans(
                    [{"trained_chara_id": 10, "card_id": 100101, "rank_score": 9000}],
                    source_file_id=source_id,
                )
                store.replace_veterans([], source_file_id=source_id)
                store.commit()
                summary = store.summary()
                self.assertEqual(summary.active_veterans, 0)
                self.assertEqual(summary.historical_veterans, 1)

    def test_race_capture_is_deduplicated_by_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "account.sqlite3"
            source = Path(temp) / "TT.json"
            source.write_text("{}", encoding="utf-8")
            payload = {
                "race_result_array": [
                    {"round": 1, "team_total_score": 123, "win_type": 1, "chara_result_array": []}
                ]
            }
            with AccountStore(db) as store:
                source_id = store.record_source(
                    source,
                    source_root=temp,
                    kind="race:team_stadium",
                    sha256="b" * 64,
                    size_bytes=2,
                    mtime_ns=1,
                )
                first_id, first_created = store.store_race_capture(
                    capture_kind="team_stadium",
                    source_file_id=source_id,
                    payload=payload,
                    observed_at="2026-01-01T00:00:00+00:00",
                )
                second_id, second_created = store.store_race_capture(
                    capture_kind="team_stadium",
                    source_file_id=source_id,
                    payload=payload,
                    observed_at="2026-01-01T00:00:01+00:00",
                )
                self.assertTrue(first_created)
                self.assertFalse(second_created)
                self.assertEqual(first_id, second_id)
                blob = store.connection.execute(
                    "SELECT payload_gzip FROM race_captures WHERE id = ?", (first_id,)
                ).fetchone()[0]
                self.assertEqual(decompress_payload(blob), payload)


if __name__ == "__main__":
    unittest.main()
