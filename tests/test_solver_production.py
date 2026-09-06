import json
import pytest
from tests.solver_fixtures import real_file_fixture
from uma_legacy_linker.parent_optimizer import optimize_parents
from uma_legacy_linker.solver_runtime import SolverRuntime, solver_scope, solver_search, current_runtime


def compare_search(operation, args, tmp_path, monkeypatch, workers):
    with solver_scope(SolverRuntime(False)):
        reference = operation(**dict(args, output_dir=tmp_path / "reference"))
    monkeypatch.setenv("ULL_SOLVER_WORKERS", str(workers))
    actual = operation(**dict(args, output_dir=tmp_path / "actual"))
    expected_files = {p.name: p.read_bytes() for p in (tmp_path / "reference").glob("*.csv")}
    actual_files = {p.name: p.read_bytes() for p in (tmp_path / "actual").glob("*.csv")}
    assert expected_files and actual_files == expected_files
    expected = json.loads(reference.rankings_json_path.read_text())
    result = json.loads(actual.rankings_json_path.read_text())
    expected["metadata"].pop("generated_at_utc")
    result["metadata"].pop("generated_at_utc")
    assert result == expected
    assert current_runtime() is None
    assert not list(tmp_path.rglob("request.json"))


@pytest.mark.parametrize("workers", [1, 2, 4, "auto"])
@pytest.mark.parametrize("kind", ["pairs", "branches", "future", "gp", "contextual_gp"])
def test_public_search_matches_canonical(tmp_path, monkeypatch, workers, kind):
    monkeypatch.setenv("ULL_G1_RANKING", "exact")
    args = real_file_fixture(tmp_path, count=8)
    operation = optimize_parents
    if kind in ("gp", "contextual_gp"):
        from uma_legacy_linker.uma_moe import rank_online_grandparent_pairs
        operation = rank_online_grandparent_pairs
        args["manual_weights_path"] = args.pop("simulator_weights_path")
        args.pop("search_kind")
        args.update(target_parent_card_id=200, exhaustive_pairs=True, local_pair_mode=True, top_n=3)
        if kind == "contextual_gp":
            args["opposing_parent"] = json.loads(args["linked_veterans_path"].read_text())["veterans"][0]
    else:
        args["search_kind"] = kind
        if kind == "future":
            args["future_parent_card_id"] = 200
    compare_search(operation, args, tmp_path, monkeypatch, workers)


@pytest.mark.parametrize("workers", [1, 4])
@pytest.mark.parametrize("exhaustive", [False, True])
def test_online_filters_match_canonical(tmp_path, monkeypatch, workers, exhaustive):
    import sqlite3
    from uma_legacy_linker.uma_moe import rank_online_parent_pairs
    args = real_file_fixture(tmp_path, count=8)
    with sqlite3.connect(args["master_path"]) as db:
        db.executescript('''
            CREATE TABLE succession_factor (factor_id, factor_group_id, rarity, factor_type, effect_group_id);
            CREATE TABLE single_mode_wins_saddle (id, win_saddle_type,
                race_instance_id_1, race_instance_id_2, race_instance_id_3, race_instance_id_4,
                race_instance_id_5, race_instance_id_6, race_instance_id_7, race_instance_id_8);
            CREATE TABLE race_instance (id, race_id);
            CREATE TABLE race (id, grade, "group");
            CREATE TABLE single_mode_program (id, race_instance_id);
        ''')
    def online_member(member):
        return {"card_id": member["card_id"], "rank_score": member["rank_score"],
                "factors": member["factors"]["all"], "g1": member["g1_wins"]["names"]}
    veterans = json.loads(args["linked_veterans_path"].read_text())["veterans"]
    records = [dict(online_member(v), friend_code=str(12345678 + i),
                    parents=[online_member(gp) for gp in v["when_used_as_parent"].values()])
               for i, v in enumerate(veterans)]
    args["manual_weights_path"] = args.pop("simulator_weights_path")
    args.pop("search_kind")
    args.update(raw_payload={"items": records}, exhaustive_pairs=exhaustive,
                fixed_parent_trained_id=30, required_parent_card_id=300,
                excluded_parent_card_ids=[1000], top_n=3)
    compare_search(rank_online_parent_pairs, args, tmp_path, monkeypatch, workers)


def test_scope_defaults_nesting_and_exception_cleanup(monkeypatch):
    monkeypatch.delenv("ULL_SOLVER_WORKERS", raising=False)
    @solver_search
    def inner():
        return current_runtime()
    @solver_search
    def outer():
        assert inner() is current_runtime()
        assert current_runtime().optimized and current_runtime().workers == 0
        raise RuntimeError("cancel")
    with pytest.raises(RuntimeError, match="cancel"):
        outer()
    assert current_runtime() is None


@pytest.mark.parametrize("value", ["-1", "bad", "1.5"])
def test_invalid_workers_fail_before_search(monkeypatch, value):
    monkeypatch.setenv("ULL_SOLVER_WORKERS", value)
    @solver_search
    def search():
        pytest.fail("invalid policy reached search")
    with pytest.raises(ValueError, match="ULL_SOLVER_WORKERS"):
        search()
    assert current_runtime() is None
