from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt

from ui_qt.models import Column, ResultTableModel, number


def test_formatted_percentile_column_sorts_by_its_numeric_key() -> None:
    percentile = number("percentile", default=100.0)
    rows = [
        {"id": "twenty", "percentile": "20.5"},
        {"id": "four", "percentile": 4.2},
        {"id": "missing", "percentile": None},
        {"id": "zero", "percentile": 0},
    ]
    model = ResultTableModel(
        rows,
        [
            Column(
                "Rank",
                lambda row: f"top {percentile(row):.1f}%",
                sort_getter=percentile,
            )
        ],
    )

    model.sort(0, Qt.SortOrder.AscendingOrder)

    assert [model.row(index)["id"] for index in range(model.rowCount())] == [
        "zero",
        "four",
        "twenty",
        "missing",
    ]
    assert model.data(model.index(0, 0)) == "top 0.0%"
    assert model.data(model.index(1, 0)) == "top 4.2%"


def test_transfer_rank_columns_use_the_numeric_percentile_sort_keys() -> None:
    source = Path("ui_qt/pages_transfer.py").read_text(encoding="utf-8")

    assert source.count("sort_getter=parent_percentile") == 1
    assert source.count("sort_getter=grandparent_percentile") == 1
