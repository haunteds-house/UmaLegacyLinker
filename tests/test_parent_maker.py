from __future__ import annotations

from uma_legacy_linker.legacy_linker import grouped_factors
from uma_legacy_linker.parent_maker import (
    SparkTarget,
    _candidate_pairs,
    _factor_matches_target,
    _score_target_family,
)


def factor(name: str, factor_type: str, stars: int) -> dict[str, object]:
    return {
        "factor_id": 1000 + stars,
        "factor_group_id": 100,
        "name": name,
        "type": factor_type,
        "stars": stars,
    }


def member(
    trained_id: object,
    chara_id: int,
    factors: list[dict[str, object]],
    *,
    origin: str = "local",
) -> dict[str, object]:
    return {
        "trained_chara_id": trained_id,
        "card_id": chara_id * 100 + 1,
        "chara_id": chara_id,
        "uma_name": f"Uma {chara_id}",
        "card_name": f"Card {chara_id}",
        "rank_score": 10000 + chara_id,
        "factors": grouped_factors(factors),
        "g1_wins": {"count": 0, "names": [], "details": []},
        "when_used_as_parent": {"grandparent_1": None, "grandparent_2": None},
        "parent_maker_origin": origin,
        "online": {},
    }


def test_unity_scenario_plus_and_nonplus_are_same_parent_maker_family() -> None:
    target = SparkTarget("scenario", "Ignited Spirit: Wit", 100, 1).normalized()
    assert _factor_matches_target(factor("Ignited Spirit: Wit", "scenario", 2), target)
    assert _factor_matches_target(factor("Ignited Spirit: Wit+", "scenario", 3), target)

    stamina = SparkTarget("scenario", "Racing Spirit: Stamina+", 100, 1).normalized()
    assert _factor_matches_target(factor("Racing Spirit: Stamina", "scenario", 1), stamina)
    assert _factor_matches_target(factor("Racing Spirit: Stamina+", "scenario", 3), stamina)


def test_unrelated_scenario_plus_variant_is_not_collapsed() -> None:
    target = SparkTarget("scenario", "Racing Spirit: Power", 100, 1).normalized()
    assert _factor_matches_target(factor("Racing Spirit: Power", "scenario", 2), target)
    assert not _factor_matches_target(factor("Racing Spirit: Power+", "scenario", 2), target)


def test_white_probability_uses_all_matching_lineage_sources() -> None:
    white = SparkTarget("white_skill", "Groundwork", 100, 1).normalized()
    p1 = member(1, 10, [factor("Groundwork", "white_skill", 1)])
    p2 = member(2, 20, [factor("Groundwork", "white_skill", 3)])
    row = _score_target_family(
        p1,
        p2,
        white,
        {"parent_1": 0.0, "parent_2": 0.0},
    )
    # Two Inspiration events per source: 1-(1-.03)^2(1-.09)^2.
    expected = 1.0 - (1.0 - 0.03) ** 2 * (1.0 - 0.09) ** 2
    assert abs(float(row["probability"]) - expected) < 1e-8
    assert row["copy_count"] == 2
    assert row["direct_copy_count"] == 2
    assert row["total_stars"] == 4


def test_candidate_pairs_never_make_remote_remote_or_same_character_pairs() -> None:
    target = (SparkTarget("white_skill", "Groundwork", 100, 1).normalized(),)
    local_a = member(1, 10, [factor("Groundwork", "white_skill", 1)])
    local_b = member(2, 20, [], origin="local")
    # Same character as local_a must be illegal despite a different copy/origin.
    remote_same = member("remote-a", 10, [factor("Groundwork", "white_skill", 3)], origin="remote")
    remote_c = member("remote-c", 30, [factor("Groundwork", "white_skill", 2)], origin="remote")
    remote_d = member("remote-d", 40, [factor("Groundwork", "white_skill", 2)], origin="remote")

    pairs, evaluated = _candidate_pairs(
        [local_a, local_b],
        [remote_same, remote_c, remote_d],
        target,
        50,
        None,
    )
    identities = {
        frozenset(
            (
                str(left.get("trained_chara_id")),
                str(right.get("trained_chara_id")),
            )
        )
        for _score, left, right in pairs
    }
    assert frozenset(("1", "2")) in identities
    assert frozenset(("1", "remote-a")) not in identities
    assert frozenset(("remote-c", "remote-d")) not in identities
    assert evaluated == len(pairs)
