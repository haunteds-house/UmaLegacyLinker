from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from output_history import previous_output_path, write_json_with_history
from simulator_weights import _quantile


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


class QuantileContractTests(unittest.TestCase):
    def test_out_of_range_quantiles_are_clamped(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0]
        self.assertEqual(_quantile(values, -0.5), 1.0)
        self.assertEqual(_quantile(values, 1.5), 4.0)


if __name__ == "__main__":
    unittest.main()
