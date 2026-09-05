from copy import deepcopy
import random
import pytest

from uma_legacy_linker.g1_race_planning import optimize_race_schedule
from uma_legacy_linker.parent_optimizer import _piecewise_score
from uma_legacy_linker.solver_runtime import SolverRuntime, solver_scope


def test_compiled_curves_preserve_interpolation_and_scope():
    curves = [[], [[2, 3], [0, 1], [1, 2]], [[0, 0], [1, 2], [1, 4]], [[-2, 4], [4, -2]]]
    reference = [[_piecewise_score(x, curve) for x in (-3, 0, .2, 1, 1.5, 9)] for curve in curves]
    with solver_scope(SolverRuntime(True)):
        actual = [[_piecewise_score(x, curve) for x in (-3, 0, .2, 1, 1.5, 9)] for curve in curves]
        assert actual == reference
        for i in range(1000):
            _piecewise_score(.3, [[0, i], [1, i + 1]])
    # Editing a config between searches must never reuse a stale curve.
    curves[1][0][1] = 20
    expected = _piecewise_score(2, curves[1])
    with solver_scope(SolverRuntime(True)):
        assert _piecewise_score(2, curves[1]) == expected


@pytest.mark.parametrize("seed", range(60))
def test_cached_g1_transitions_keep_entire_canonical_plan(seed):
    randomizer = random.Random(seed)
    races = []
    for i in range(8 + seed % 18):
        phase = randomizer.randrange(4, 24)
        years = [2, 3] if i % 3 else [randomizer.choice((1, 2, 3))]
        races.append({"name": str(i), "affinity_bonus": randomizer.choice((3, 6)),
            "independent_training_base_win_probability": randomizer.choice((.7, .8, 1.1)),
            "independent_training_win_probability_cutoff": .6,
            "schedule_slots": [{"year": y, "month": phase // 2 + 1, "half": phase % 2 + 1} for y in years]})
    if seed % 4 == 0:
        races.append({"name": "Goal", "mandatory_objective": True, "affinity_bonus": 0,
                      "schedule_slots": [{"year": 1, "month": 2, "half": 1}]})
    budget = None if seed % 2 else seed % 16
    reference = optimize_race_schedule(deepcopy(races), max_affinity_races=budget)
    with solver_scope(SolverRuntime(True)):
        actual = optimize_race_schedule(deepcopy(races), max_affinity_races=budget)
    assert actual == reference


def test_fast_g1_retains_cooperative_cancellation():
    class Cancelled(Exception):
        pass
    def cancel():
        raise Cancelled()
    with solver_scope(SolverRuntime(True)), pytest.raises(Cancelled):
        optimize_race_schedule([], checkpoint=cancel)
