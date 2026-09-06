import csv
import json

import pytest

from tests.solver_fixtures import real_file_fixture
from uma_legacy_linker.g1_race_planning import estimate_race_schedule
from uma_legacy_linker.solver_runtime import SolverRuntime, solver_scope
from uma_legacy_linker.uma_moe import rank_online_grandparent_pairs


def race(name, bonus, *years, month=5, **extra):
    return dict(name=name, affinity_bonus=bonus,
                schedule_slots=[dict(year=y, month=month, half=1) for y in years], **extra)


def test_e2_reserves_objectives_and_prefers_restricted_calendar():
    races = [race('objective', 0, 1, mandatory_objective=True),
             race('blocked', 6, 1), race('flexible', 6, 2, 3),
             race('restricted', 6, 2),
             race('bad aptitude', 6, 2, month=6, independent_training_base_cutoff_passed=False),
             race('missing', 3)]
    result = estimate_race_schedule(races, max_affinity_races=2)
    assert {r['name'] for r in result['scheduled_races']} == {'objective', 'flexible', 'restricted'}
    assert result['optimal_bonus'] == 12
    assert [r['name'] for r in result['missing_calendar_races']] == ['missing']
    assert races[2]['planned_slot']['year'] == 3


@pytest.mark.parametrize('workers', [1, 2, 4, 0])
@pytest.mark.parametrize('top_n', [1, 3, 60])
def test_two_pass_matches_oracle_and_exports_only_exact_finalists(tmp_path, monkeypatch, workers, top_n):
    args = real_file_fixture(tmp_path, count=8)
    args['manual_weights_path'] = args.pop('simulator_weights_path')
    args.pop('search_kind')
    args.update(target_parent_card_id=200, exhaustive_pairs=True, local_pair_mode=True, top_n=top_n)
    monkeypatch.setenv('ULL_G1_RANKING', 'exact')
    with solver_scope(SolverRuntime(True)):
        reference = rank_online_grandparent_pairs(**dict(args, output_dir=tmp_path / 'exact'))
    monkeypatch.setenv('ULL_G1_RANKING', 'e2')
    runtime = SolverRuntime(True, workers=workers)
    with solver_scope(runtime):
        result = rank_online_grandparent_pairs(**dict(args, output_dir=tmp_path / 'e2'))
    assert result.top_results == reference.top_results
    assert result.evaluated_pair_count == reference.evaluated_pair_count
    stats = runtime.stats['g1_ranking']
    assert stats['exact_shortlist_pairs'] == min(2 * top_n, result.evaluated_pair_count)
    assert runtime.stats['g1_estimator_calls'] == result.evaluated_pair_count
    assert runtime.stats['g1_solver_calls'] == stats['exact_shortlist_pairs'] + 2 * len(result.top_results)
    with result.rankings_csv_path.open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream, delimiter=';'))
    with reference.rankings_csv_path.open(encoding='utf-8-sig') as stream:
        oracle = list(csv.DictReader(stream, delimiter=';'))
    assert rows == oracle[:len(result.top_results)]
    assert result.result_count == len(rows)
    assert json.loads(result.rankings_json_path.read_text())['metadata']['g1_ranking']['csv_scope'] == 'exact_final_top'


def test_estimator_cooperates_with_cancellation():
    def cancel():
        raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError, match='cancelled'):
        estimate_race_schedule([race('race', 6, 2)], checkpoint=cancel)


def test_rerank_reverses_approximate_order_and_preserves_exact_ties(tmp_path, monkeypatch):
    from uma_legacy_linker import uma_moe
    args = real_file_fixture(tmp_path, count=8)
    args['manual_weights_path'] = args.pop('simulator_weights_path')
    args.pop('search_kind')
    args.update(target_parent_card_id=200, exhaustive_pairs=True, local_pair_mode=True)
    monkeypatch.setenv('ULL_G1_RANKING', 'exact')
    with solver_scope(SolverRuntime(True)):
        oracle = rank_online_grandparent_pairs(**dict(args, top_n=60, output_dir=tmp_path / 'oracle'))
    def identity(row):
        return (row['_gp1']['trained_chara_id'], row['_gp2']['trained_chara_id'])
    positions = {identity(row): i for i, row in enumerate(oracle.top_results)}
    evaluate = uma_moe._evaluate_gp_pair
    def disturbed(context, gp1, gp2, *, detailed):
        row = evaluate(context, gp1, gp2, detailed=detailed)
        if context.get('g1_ranking_mode') == 'e2':
            rank = positions[identity(row)]
            # The true winner is now sixth: outside top 3, inside top 2X.
            row['score'] = 100 + rank if rank < 6 else -rank
        return row
    monkeypatch.setattr(uma_moe, '_evaluate_gp_pair', disturbed)
    monkeypatch.setenv('ULL_G1_RANKING', 'e2')
    with solver_scope(SolverRuntime(True)):
        result = rank_online_grandparent_pairs(**dict(args, top_n=3, output_dir=tmp_path / 'reranked'))
    assert result.top_results == oracle.top_results[:3]
