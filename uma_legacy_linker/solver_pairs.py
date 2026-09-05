"""Prepared numerical inputs for the first pass of parent-pair ranking.

Public details are always hydrated through the canonical evaluator afterward.
Caches retain object identities and are bounded to handle projected GP branches.
"""
from __future__ import annotations

from typing import Any, Callable
from uma_legacy_linker.solver_math import interpolate
from uma_legacy_linker.solver_runtime import current_runtime


def _bounded_put(cache: dict, key: Any, value: Any, limit: int = 2048) -> Any:
    if len(cache) >= limit:
        del cache[next(iter(cache))]
    cache[key] = value
    return value


class PairPreparation:
    def __init__(self, resolver, ace, config, weight_lookup, race_skills):
        self.resolver, self.ace, self.config = resolver, ace, config
        self.lookup, self.race_skills = weight_lookup, race_skills
        cfg = config.get("white_inheritance") or {}
        self.rates = cfg.get("base_proc_rates") or {"1": .03, "2": .06, "3": .09}
        self.race_rates = cfg.get("race_base_proc_rates") or {"1": .01, "2": .02, "3": .03}
        self.events = max(1, int(cfg.get("inspiration_event_count", 2) or 2))
        self.cap = max(0., min(float(cfg.get("per_event_probability_cap", 1.)), 1.))
        curve = cfg.get("distinct_skill_probability_curve") or [[0., 0.], [.10, .10], [.20, .30], [.40, .52], [.60, .64], [.80, .70], [1., .73]]
        self.curve = sorted((float(p[0]), float(p[1])) for p in curve)
        self.skill_ids: dict[str, int] = {}
        self.weights: list[float] = []
        self.sources: dict[int, tuple] = {}
        self.failures: dict[tuple, float] = {}
        self.branches: dict[tuple, tuple] = {}
        self.wins: dict[int, tuple] = {}

    def _failure(self, rate, affinity):
        key = (rate, affinity)
        failure = self.failures.get(key)
        if failure is None:
            probability = min(self.cap, rate * (1. + affinity / 100.))
            failure = (1. - probability) ** self.events
            _bounded_put(self.failures, key, failure, 4096)
        return failure

    def _skill(self, key: str) -> int:
        if key not in self.skill_ids:
            self.skill_ids[key] = len(self.weights)
            self.weights.append(max(0., float(self.lookup(key))))
        return self.skill_ids[key]

    def _sources(self, member: dict, check: Callable) -> tuple:
        from uma_legacy_linker import parent_optimizer as po
        factors = member.get("factors") or {}
        entry = self.sources.get(id(factors))
        if entry is not None and entry[0] is factors:
            return entry[1]
        items = []
        for factor in po._factor_list(member, "white_skill"):
            check()
            skill_id = self._skill(po.slugify(str(factor.get("name") or "")))
            rate = max(0., float(self.rates.get(str(int(factor.get("stars") or 0)), 0.)))
            if self.weights[skill_id] > 0.:
                items.append((skill_id, rate))
        for factor in po._factor_list(member, "white_race"):
            check()
            rate = max(0., float(self.race_rates.get(str(int(factor.get("stars") or 0)), 0.)))
            for key in self.race_skills.get(str(factor.get("name") or ""), []):
                check()
                skill_id = self._skill(key)
                if self.weights[skill_id] > 0.:
                    items.append((skill_id, rate))
        result = tuple(items)
        if factors and member.get("source_role") != "projected_future_parent":
            _bounded_put(self.sources, id(factors), (factors, result))
        return result

    def white_score(self, members, affinities, saturation_key, check):
        from uma_legacy_linker.parent_optimizer import _saturating_score
        grouped = {}
        check()
        for member, _position, role in members:
            check()
            affinity = max(0., float(affinities.get(role, 0.)))
            for skill_id, rate in self._sources(member, check):
                check()
                failure = self._failure(rate, affinity)
                grouped[skill_id] = grouped.get(skill_id, 1.) * failure
        raw = 0.
        for skill_id, failure in grouped.items():
            check()
            # Preserve the canonical insertion and floating point accumulation order.
            raw += self.weights[skill_id] * max(0., float(interpolate(1. - float(failure), self.curve)))
        scale = float((self.config.get("white_saturation") or {}).get(saturation_key, 1.))
        return _saturating_score(raw, scale), {}

    def _g1(self, member):
        from uma_legacy_linker.g1_race_planning import _member_g1_payload
        from uma_legacy_linker.parent_optimizer import _member_g1
        wins = member.get("g1_wins") or {}
        entry = self.wins.get(id(wins))
        if entry is None or entry[0] is not wins:
            # These two parsers intentionally have different legacy semantics.
            entry = (wins, _member_g1(member), _member_g1_payload(member)[0])
            if wins and member.get("source_role") != "projected_future_parent":
                _bounded_put(self.wins, id(wins), entry)
        return entry[1], entry[2]

    def g1_summary(self, left, right, objectives):
        a, b = self._g1(left)[1], self._g1(right)[1]
        return {"common_g1_names": sorted(a & b), "left_only_g1_names": sorted(a - b),
                "right_only_g1_names": sorted(b - a), "common_g1_count": len(a & b),
                "left_only_g1_count": len(a - b), "right_only_g1_count": len(b - a),
                "schedule_computed": False,
                "objective_race_count": sum(isinstance(race, dict) for race in objectives),
                "schedule_variants": {}}

    def _branch(self, member, bonus):
        from uma_legacy_linker.parent_optimizer import _branch_inheritance_affinities
        key = (id(member), bonus)
        entry = self.branches.get(key)
        if entry is None or entry[0] is not member:
            entry = (member, _branch_inheritance_affinities(self.resolver, int(self.ace.get("chara_id") or 0), member, bonus))
            if member.get("source_role") != "projected_future_parent":
                _bounded_put(self.branches, key, entry)
        return entry[1]

    def inheritance(self, left, right, bonus, pair_base):
        extra = pair_base + bonus * len(self._g1(left)[0] & self._g1(right)[0])
        values = {}
        for prefix, member in (("parent_1", left), ("parent_2", right)):
            branch = self._branch(member, bonus)
            values[prefix] = branch["parent"] + extra
            values[prefix + "_grandparent_1"] = branch["grandparent_1"]
            values[prefix + "_grandparent_2"] = branch["grandparent_2"]
        return {"values": values}


def prepared_pair_context(resolver, ace, config, weight_lookup, race_skills) -> PairPreparation:
    runtime = current_runtime()
    assert runtime is not None and runtime.optimized
    cache = runtime.caches.setdefault("pair_contexts", {})
    key = tuple(map(id, (resolver, ace, config, weight_lookup, race_skills)))
    if key not in cache:
        _bounded_put(cache, key, PairPreparation(resolver, ace, config, weight_lookup, race_skills), 16)
    return cache[key]
