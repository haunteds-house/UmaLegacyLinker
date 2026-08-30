from __future__ import annotations

from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


def test_every_dense_numeric_table_enables_tabular_figures() -> None:
    expected_calls = {
        "ui_qt/pages_transfer.py": 1,
        "ui_qt/result_panes.py": 2,
        "ui_qt/curve_editor.py": 1,
    }
    for relative_path, expected_count in expected_calls.items():
        source = (PROJECT_DIR / relative_path).read_text(encoding="utf-8")
        assert source.count("enable_tabular_numbers(self.table)") == expected_count


def test_tabular_figures_keep_the_application_typeface() -> None:
    source = (PROJECT_DIR / "ui_qt/table_typography.py").read_text(
        encoding="utf-8"
    )
    assert 'TABULAR_NUMBERS_FEATURE = "tnum"' in source
    assert "font.setFeature(TABULAR_NUMBERS_FEATURE, 1)" in source
    assert "widget.setFont(font)" in source
    assert "setFamily(" not in source
    assert "setFixedPitch(" not in source
