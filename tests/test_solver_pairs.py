from copy import deepcopy
import random

import pytest

from tests.test_parent_pair_engine import (
    FakeResolver, ace, member, base_config, add_white, add_race, add_red,
    add_blue, add_scenario,
)
from uma_legacy_linker.parent_optimizer import evaluate_parent_pair, parent_pair_sort_key
from uma_legacy_linker.solver_runtime import SolverRuntime, solver_scope


@pytest.mark.parametrize("seed", range(30))
def test_prepared_pair_preserves_exact_score_and_hydrated_details(seed):
    rng = random.Random(seed)
    resolver, target, config = FakeResolver(), ace(seed % 4 + 4), base_config()
    config["mode_weights"] = {"parent_pair": {
        "white_skill": .37, "pink": .29, "blue": .18, "unique": .16}}
    config["white_inheritance"] = {
        "base_proc_rates": {"1": 0., "2": .06, "3": .9},
        "race_base_proc_rates": {"1": .01, "2": .08, "3": .4},
        "per_event_probability_cap": [0., .5, 1.][seed % 3],
        "inspiration_event_count": seed % 4 + 1,
        "distinct_skill_probability_curve": [[1., .7], [.2, .3], [0., 0.]],
    }
    race_skills = {"Race": ["skill_a", "skill_a", "skill_b", "zero"]}
    weights = {"skill_a": 2.718, "skill_b": .123, "zero": 0., "negative": -1.}
    lookup = lambda key: weights.get(key, 0.)
    members = [member(i + 2, str(i), rng.sample(["A", "B", "C"], rng.randrange(4))) for i in range(6)]
    for m in members:
        for _ in range(8):
            add_white(m, rng.choice(["Skill A", "Skill B", "Zero", "Negative"]), rng.randrange(4))
        add_race(m, "Race", rng.randrange(4))
        add_red(m, rng.choice(["Medium", "Turf", "Pace Chaser"]), rng.randrange(1, 4))
        add_blue(m, "Speed", rng.randrange(1, 4))
        add_scenario(m, "Climax Scenario", 2, "Stamina", "Guts")
    left, right = members[:2]
    left["when_used_as_parent"].update(grandparent_1=members[2], grandparent_2=members[3])
    right["when_used_as_parent"].update(grandparent_1=members[4], grandparent_2=members[5])
    if seed % 2:
        right["when_used_as_parent"]["grandparent_2"] = None
    # The diagnostic parser also sees details; inheritance uses the names list.
    left["g1_wins"]["details"] = [{"name": "Details only"}]
    right["g1_wins"]["details"] = [{"name": "Details only"}]
    kwargs = dict(surface="turf", distance="medium", style="pace_chaser",
                  config=config, race_skills=race_skills, weight_lookup=lookup)
    reference = evaluate_parent_pair(resolver, target, left, right, **kwargs)
    with solver_scope(SolverRuntime(True)):
        for _ in range(2):  # Same call cold and with populated caches.
            fast = evaluate_parent_pair(resolver, target, left, right,
                                        include_details=False, include_g1_schedule=False, **kwargs)
            assert parent_pair_sort_key(fast) == parent_pair_sort_key(reference)
            assert fast["components"] == reference["components"]
            assert fast["affinity"]["inheritance_affinities"]["values"] == reference["affinity"]["inheritance_affinities"]["values"]
        assert evaluate_parent_pair(resolver, target, left, right, **kwargs) == reference
        # Distinct snapshots may have identical trained IDs, including projections.
        changed = deepcopy(left)
        add_white(changed, "Skill B", 3)
        with solver_scope(SolverRuntime(False)):
            expected = evaluate_parent_pair(resolver, target, changed, right, **kwargs)
        actual = evaluate_parent_pair(resolver, target, changed, right,
                                      include_details=False, include_g1_schedule=False, **kwargs)
        assert parent_pair_sort_key(actual) == parent_pair_sort_key(expected)
