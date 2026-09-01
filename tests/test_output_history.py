from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from uma_legacy_linker.output_history import (
    CURRENT_REVISION,
    PREVIOUS_REVISION,
    available_output_revisions,
    format_output_timestamp,
    output_revision_path,
    previous_output_path,
    read_json_output_revision,
    write_json_with_history,
)
from uma_legacy_linker.simulator_weights import _quantile


class OutputHistoryTests(unittest.TestCase):
    def test_json_writer_retains_exactly_one_previous_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            current = Path(temp_dir) / "rankings.json"
            previous = previous_output_path(current)

            write_json_with_history(current, {"generation": 1})
            self.assertFalse(previous.exists())
            write_json_with_history(current, {"generation": 2})
            self.assertEqual(json.loads(previous.read_text()), {"generation": 1})
            write_json_with_history(current, {"generation": 3})

            self.assertEqual(json.loads(current.read_text()), {"generation": 3})
            self.assertEqual(json.loads(previous.read_text()), {"generation": 2})
            self.assertEqual(list(Path(temp_dir).glob("*.prev.json")), [previous])

    def test_available_revisions_are_current_then_previous_with_dates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            current = Path(temp_dir) / "rankings.json"
            write_json_with_history(current, {"generation": 1})
            os.utime(current, (1_700_000_000, 1_700_000_000))
            write_json_with_history(current, {"generation": 2})

            revisions = available_output_revisions(current)

            self.assertEqual(
                [revision.key for revision in revisions],
                [CURRENT_REVISION, PREVIOUS_REVISION],
            )
            self.assertEqual(revisions[0].path, current)
            self.assertEqual(revisions[1].path, previous_output_path(current))
            self.assertTrue(format_output_timestamp(revisions[1].modified_at_utc))

    def test_read_revision_extracts_schema_source_and_input_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            current = Path(temp_dir) / "report.json"
            write_json_with_history(
                current,
                {
                    "metadata": {
                        "format_version": 5,
                        "generated_at_utc": "2026-08-30T09:15:00+00:00",
                        "purpose": "Transfer analysis",
                        "source_veterans": {
                            "filename": "veterans.json",
                            "sha256": "abc123",
                        },
                        "source_course_weights": None,
                    },
                    "records": [],
                },
            )

            payload, provenance = read_json_output_revision(current)

            self.assertEqual(payload["records"], [])
            self.assertEqual(provenance.revision.key, CURRENT_REVISION)
            self.assertEqual(provenance.schema_version, "5")
            self.assertEqual(provenance.source, "Transfer analysis")
            self.assertEqual(provenance.sources[0].role, "veterans")
            self.assertEqual(provenance.sources[0].sha256, "abc123")

    def test_revision_path_rejects_unknown_generations(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown output revision"):
            output_revision_path("rankings.json", "arbitrary")


class QuantileContractTests(unittest.TestCase):
    def test_out_of_range_quantiles_are_clamped(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0]
        self.assertEqual(_quantile(values, -0.5), 1.0)
        self.assertEqual(_quantile(values, 1.5), 4.0)


if __name__ == "__main__":
    unittest.main()
