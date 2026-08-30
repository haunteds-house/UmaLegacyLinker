from __future__ import annotations

from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


def test_every_expert_collapsible_section_has_a_stable_store_key() -> None:
    sources = "\n".join(
        (PROJECT_DIR / path).read_text(encoding="utf-8")
        for path in (
            "ui_qt/pages_search.py",
            "ui_qt/pages_weights.py",
            "ui_qt/lineage_settings.py",
        )
    )
    expected = {
        "ui_section_search_objective",
        "ui_section_search_course",
        "ui_section_search_conditions",
        "ui_section_search_retrieval",
        "ui_section_search_online_parent",
        "ui_section_search_online_gp",
        "ui_section_weights_priorities",
        "ui_section_lineage_advanced",
    }
    for key in expected:
        assert f'"{key}"' in sources


def test_result_views_persist_layout_without_reusing_scoring_keys() -> None:
    sources = "\n".join(
        (PROJECT_DIR / path).read_text(encoding="utf-8")
        for path in (
            "ui_qt/pages_transfer.py",
            "ui_qt/pages_weights.py",
            "ui_qt/result_families.py",
            "ui_qt/result_panes.py",
            "ui_qt/view_state.py",
        )
    )
    assert "bind_splitter_state" in sources
    assert "bind_table_view_state" in sources
    assert "ui_search_active_family" in sources
    assert "saveState()" in sources
    assert "restoreState" in sources
    assert "CustomContextMenu" in sources
    assert "setSectionsMovable(True)" in sources

    context_source = (PROJECT_DIR / "ui_qt/context.py").read_text(
        encoding="utf-8"
    )
    transfer_fingerprint = context_source[
        context_source.index("    def transfer_fingerprint(") :
        context_source.index("    def update_online_options(")
    ]
    assert '"ui_' not in transfer_fingerprint
