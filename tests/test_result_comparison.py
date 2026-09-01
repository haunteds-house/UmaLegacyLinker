from __future__ import annotations

import unittest

from uma_legacy_linker.result_comparison import (
    SEARCH_METRICS,
    TRANSFER_METRICS,
    format_metric_delta,
    intersect_datasets,
    matching_index,
    search_comparison_dataset,
    search_payload_rows,
    transfer_comparison_dataset,
)


class ResultComparisonTests(unittest.TestCase):
    def test_pair_identity_matches_across_rank_changes(self) -> None:
        pair = {
            "parent_1": {"trained_chara_id": 10, "card_name": "Left"},
            "parent_2": {"trained_chara_id": 20, "card_name": "Right"},
            "score": 42.0,
        }
        current = search_comparison_dataset(
            "pairs", [{**pair, "_rank": 1}], title="Current"
        )
        previous = search_comparison_dataset(
            "pairs", [{**pair, "_rank": 7}], title="Previous"
        )

        self.assertEqual(current.items[0].key, previous.items[0].key)
        self.assertEqual(matching_index(previous, current.items[0].key), 0)

    def test_online_identity_keeps_fixed_and_remote_roles(self) -> None:
        rows = [
            {
                "fixed_parent": {"trained_chara_id": 10, "card_name": "Local"},
                "candidate": {
                    "card_id": 20,
                    "card_name": "Remote",
                    "online": {"friend_code": "123"},
                },
            }
        ]
        dataset = search_comparison_dataset(
            "online_parent", rows, title="Current"
        )

        self.assertEqual(dataset.items[0].key, "online_parent:10|123")
        self.assertIn("Local", dataset.items[0].label)
        self.assertIn("Remote", dataset.items[0].label)

    def test_payload_rows_are_scoped_to_the_requested_family(self) -> None:
        payload = {
            "top_parent_pairs": [{"score": 1}],
            "top_parent_candidates": [{"score": 2}],
        }

        rows = search_payload_rows("branches", payload)

        self.assertEqual([row["score"] for row in rows], [2])
        self.assertEqual(rows[0]["_rank"], 1)

    def test_transfer_identity_uses_training_id(self) -> None:
        dataset = transfer_comparison_dataset(
            [{"trained_chara_id": 99, "card_name": "Veteran"}],
            title="Report",
        )

        self.assertEqual(dataset.items[0].key, "trained:99")

    def test_numeric_delta_is_right_minus_left(self) -> None:
        score = SEARCH_METRICS[1]

        self.assertEqual(format_metric_delta(10.0, 12.5, score), "+2.50")
        self.assertEqual(format_metric_delta("keep", "review", score), "—")

    def test_transfer_wisdom_metric_reads_the_exported_wiz_field(self) -> None:
        wisdom = next(
            metric for metric in TRANSFER_METRICS if metric.label == "Intelligence"
        )

        self.assertEqual(wisdom.getter({"stats": {"wiz": 901}}), 901.0)

    def test_history_intersection_excludes_unmatched_candidates(self) -> None:
        left = transfer_comparison_dataset(
            [
                {"trained_chara_id": 1, "card_name": "Shared"},
                {"trained_chara_id": 2, "card_name": "New"},
            ],
            title="Current",
        )
        right = transfer_comparison_dataset(
            [
                {"trained_chara_id": 1, "card_name": "Shared"},
                {"trained_chara_id": 3, "card_name": "Removed"},
            ],
            title="Previous",
        )

        matched_left, matched_right = intersect_datasets(left, right)

        self.assertEqual([item.key for item in matched_left.items], ["trained:1"])
        self.assertEqual([item.key for item in matched_right.items], ["trained:1"])

    def test_history_intersection_never_matches_display_labels_without_ids(self) -> None:
        left = transfer_comparison_dataset(
            [{"card_name": "Same label", "rank_score": 10}],
            title="Current",
        )
        right = transfer_comparison_dataset(
            [{"card_name": "Same label", "rank_score": 12}],
            title="Previous",
        )

        matched_left, matched_right = intersect_datasets(left, right)

        self.assertFalse(matched_left.items)
        self.assertFalse(matched_right.items)


if __name__ == "__main__":
    unittest.main()
