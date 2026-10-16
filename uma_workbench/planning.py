"""Collection setup search, with explicit aptitude and skill-source evidence.

This searches ways to build a runner. It does not forecast training stats,
event rolls or race scores. Large support searches retain a bounded frontier.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import chain, combinations
import json
from pathlib import Path
import sys

from uma_legacy_linker.legacy_linker import is_borrowed_veteran
from uma_legacy_linker.parent_optimizer import _initial_aptitude_rank
from uma_legacy_linker.skill_catalog import parse_condition
from uma_workbench.training import TrainingData, TrainingModel, completed_career_comparison, validate_recorded_practices


APTITUDES = (
    ("proper_ground_turf", "Turf", 11), ("proper_ground_dirt", "Dirt", 12),
    ("proper_distance_short", "Sprint", 31), ("proper_distance_mile", "Mile", 32),
    ("proper_distance_middle", "Medium", 33), ("proper_distance_long", "Long", 34),
    ("proper_running_style_nige", "Front Runner", 21),
    ("proper_running_style_senko", "Pace Chaser", 22),
    ("proper_running_style_sashi", "Late Surger", 23),
    ("proper_running_style_oikomi", "End Closer", 24),
)
GRADE_LABELS = {0: "Any", 1: "G", 2: "F", 3: "E", 4: "D", 5: "C", 6: "B", 7: "A", 8: "S"}
STAT_KEYS = ("speed", "stamina", "power", "guts", "wiz")
DISTANCE_NAMES = {"Sprint": 1, "Mile": 2, "Medium": 3, "Long": 4}
STYLE_NAMES = {"Front Runner": 1, "Pace Chaser": 2, "Late Surger": 3, "End Closer": 4}


def distance_group(requirements):
    exact = requirements.get("distance")
    if exact:
        return "Sprint" if exact <= 1400 else "Mile" if exact <= 1800 else "Medium" if exact <= 2400 else "Long"
    return requirements.get("distance_type", "Any distance")


@dataclass
class PlanningCatalog:
    rarities: dict = field(default_factory=dict)
    available_skills: dict = field(default_factory=dict)
    skill_sets: dict = field(default_factory=dict)
    support_hints: dict = field(default_factory=dict)
    support_events: dict = field(default_factory=dict)
    skills: dict = field(default_factory=dict)
    costs: dict = field(default_factory=dict)
    factor_effects: dict = field(default_factory=dict)
    upgrades: list = field(default_factory=list)
    songs: list = field(default_factory=list)
    texts: dict = field(default_factory=dict)
    hint_data_available: bool = False
    event_data_available: bool = False
    training_data: TrainingData = field(default_factory=TrainingData)
    _lower_map: dict | None = field(default=None, repr=False)
    _hint_cache: dict = field(default_factory=dict, repr=False)
    _event_cache: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, master):
        result = cls()
        if not master.path:
            return result
        with master.connection() as con:
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            def rows(table):
                return [dict(row) for row in con.execute(f'SELECT * FROM "{table}"')] if table in tables else []
            for row in rows("card_rarity_data"):
                result.rarities.setdefault(row["card_id"], {})[row["rarity"]] = row
            for row in rows("available_skill_set"):
                result.available_skills.setdefault(row["available_skill_set_id"], {})[row["skill_id"]] = row["need_rank"]
            for row in rows("skill_set"):
                result.skill_sets[row["id"]] = {int(row[f"skill_id{i}"]) for i in range(1, 21) if row.get(f"skill_id{i}")}
            result.hint_data_available = "single_mode_hint_gain" in tables
            for row in rows("single_mode_hint_gain"):
                if row.get("hint_gain_type") == 0 and row.get("support_card_id") and row.get("hint_value_1"):
                    result.support_hints.setdefault(row["support_card_id"], set()).add(row["hint_value_1"])
            result.skills = {row["id"]: row for row in rows("skill_data")}
            result.costs = {row["id"]: row["need_skill_point"] for row in rows("single_mode_skill_need_point")}
            for row in rows("succession_factor_effect"):
                result.factor_effects.setdefault((row["factor_group_id"], row["effect_id"]), []).append(row)
            result.upgrades = rows("card_talent_upgrade")
            result.texts = {(row["category"], row["index"]): row["text"] for row in con.execute(
                'SELECT category,"index",text FROM text_data WHERE category IN (23,207,209)')} if "text_data" in tables else {}
            result.songs = [row for row in rows("single_mode_live_square") if row.get("square_type") == 4]
        resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        event_path = resource_root / "resources" / "support_event_hints.json"
        if event_path.is_file():
            data = json.loads(event_path.read_text(encoding="utf-8"))
            result.support_events = {int(sid): {int(skill) for skill in skills if int(skill) in result.skills}
                for sid, skills in data.get("skill_ids_by_support", {}).items() if int(sid) in master.supports}
            result.event_data_available = bool(result.support_events)
        result.training_data = TrainingData.load(master)
        return result

    def lower_skills(self, identities):
        """A skill source also unlocks positive prerequisite steps in its family."""
        answer = {int(identity) for identity in identities}
        if self._lower_map is None:
            groups = defaultdict(list)
            for identity, row in self.skills.items():
                if row.get("group_rate", 0) > 0:
                    groups[row.get("group_id")].append((identity, row.get("group_rate", 0)))
            self._lower_map = {identity: {sid for sid, rate in groups[row.get("group_id")]
                if 0 < rate < row.get("group_rate", 0)} for identity, row in self.skills.items()}
        for identity in tuple(answer):
            answer.update(self._lower_map.get(identity, ()))
        return answer

    def base_skills(self, master, trainee):
        card = master.cards.get(int(trainee["card_id"]), {})
        available = self.available_skills.get(card.get("available_skill_set_id"), {})
        result = {sid for sid, level in available.items() if level <= int(trainee.get("talent_level", 1))}
        rarity = self.rarity_row(master, trainee)
        result.update(self.skill_sets.get(rarity.get("skill_set"), set()))
        return self.lower_skills(result)

    def rarity_row(self, master, trainee):
        identity = int(trainee["card_id"])
        owned_rarity = int(trainee.get("rarity", master.cards.get(identity, {}).get("default_rarity", 1)))
        options = self.rarities.get(identity, {})
        known = [rarity for rarity in options if rarity <= owned_rarity]
        return options[max(known)] if known else {}

    def hint_skills(self, master, support_id):
        if support_id in self._hint_cache:
            return self._hint_cache[support_id]
        pool = self.support_hints.get(support_id)
        if pool is None and not self.hint_data_available:
            pool = self.skill_sets.get(master.supports.get(support_id, {}).get("skill_set_id"), set())
        self._hint_cache[support_id] = self.lower_skills(pool or ())
        return self._hint_cache[support_id]

    def event_skills(self, support_id):
        if support_id not in self._event_cache:
            self._event_cache[support_id] = self.lower_skills(self.support_events.get(support_id, ()))
        return self._event_cache[support_id]


def catalog_for(master):
    cached = getattr(master, "_planning_catalog", None)
    if cached is None:
        cached = master._planning_catalog = PlanningCatalog.load(master)
    return cached


def requirements_aptitudes(requirements):
    targets = {key: int(value) for key, value in requirements.get("aptitudes", {}).items() if int(value)}
    default = int(requirements.get("minimum_aptitude", 7))
    if requirements.get("surface") in ("Turf", "Dirt"):
        targets.setdefault("proper_ground_" + requirements["surface"].lower(), default)
    distance = distance_group(requirements)
    if distance in DISTANCE_NAMES:
        targets.setdefault("proper_distance_" + {"Sprint": "short", "Mile": "mile", "Medium": "middle", "Long": "long"}[distance], default)
    style = requirements.get("style")
    if style in STYLE_NAMES:
        targets.setdefault(APTITUDES[5 + STYLE_NAMES[style]][0], default)
    return {key: value for key, value in targets.items() if value}


def _skill_incompatible(skill, requirements):
    profile = {"ground_type": {"Turf": 1, "Dirt": 2}.get(requirements.get("surface")),
        "distance_type": DISTANCE_NAMES.get(distance_group(requirements)),
        "running_style": STYLE_NAMES.get(requirements.get("style"))}
    operations = {"==": lambda a, b: a == b, "!=": lambda a, b: a != b,
        ">": lambda a, b: a > b, "<": lambda a, b: a < b,
        ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b}
    slots = []
    for slot in (1, 2):
        expressions = [skill.get(f"{prefix}_{slot}", "") for prefix in ("precondition", "condition")]
        if not any(expressions):
            continue
        possible = True
        for expression in expressions:
            parsed = parse_condition(expression)
            if not parsed["or_groups"]:
                continue
            possible &= any(not any(atom.get("parsed") and profile.get(atom.get("variable")) is not None
                and not operations[atom["operator"]](profile[atom["variable"]], atom["value"])
                for atom in group) for group in parsed["or_groups"])
        slots.append(possible)
    return bool(slots) and not any(slots)


def _branch_evidence(master, catalog, veteran):
    stars = defaultdict(int)
    skills = set()
    members = [veteran] + [row for row in veteran.get("succession_chara_array", []) if int(row.get("position_id", 0)) in (10, 20)]
    for member in members:
        for item in member.get("factor_info_array", []):
            factor = master.factors.get(int(item.get("factor_id", 0)), {})
            kind, group = factor.get("factor_type"), factor.get("factor_group_id")
            if kind == 2:
                stars[group] += int(factor.get("rarity", 0))
            elif kind == 4:
                skills.update(identity for identity, skill in catalog.skills.items()
                    if skill.get("group_id") == group and skill.get("group_rate") == 1)
            elif kind == 3:
                for effect in catalog.factor_effects.get((group, factor.get("rarity")), []):
                    if effect.get("target_type") == 41:
                        skills.add(int(effect["value_1"]))
    return dict(stars), catalog.lower_skills(skills)


def _deck_frontier(master, catalog, supports, target_character, wanted, pinned, checkpoint, *, training_scores=None, training_quality=None, require_borrowed=False, borrowed_id=None):
    # Signed keys distinguish a rental copy from the player's version of a card.
    by_id = {int(row["support_card_id"]): {**row, "borrowed": False} for row in supports}
    if require_borrowed:
        for identity in ([borrowed_id] if borrowed_id is not None else master.supports):
            if identity in master.supports:
                by_id[-identity] = {"support_card_id": identity, "borrowed": True}
        pinned = tuple(pinned) + ((-borrowed_id,) if borrowed_id is not None else ())
    else:
        for identity in pinned:
            if identity not in by_id and identity in master.supports:
                by_id[identity] = {"support_card_id": identity, "borrowed": True}
    if any(identity not in by_id for identity in pinned):
        raise ValueError("A chosen support is missing from your collection and game data")
    def character(key):
        identity = int(by_id[key]["support_card_id"])
        return master.supports.get(identity, {}).get("chara_id", -identity)
    chars = [character(key) for key in pinned]
    if len(pinned) > 6 or len(set(chars)) != len(chars) or target_character in chars or (require_borrowed and sum(key > 0 for key in pinned) > 5):
        return []
    groups = defaultdict(list)
    masks, levels = {}, {}
    for key, row in by_id.items():
        identity = int(row["support_card_id"])
        chara = character(key)
        if chara == target_character:
            continue
        hints = catalog.hint_skills(master, identity) | catalog.event_skills(identity)
        masks[key] = sum(1 << index for index, skill in enumerate(wanted) if skill in hints)
        levels[key] = training_scores.get(key, 0) if training_scores is not None else (50 if row.get("borrowed") else (master.support_level(row) or 0))
        if key not in pinned and chara not in chars:
            groups[chara].append(key)
    initial_mask = 0
    for key in pinned:
        initial_mask |= masks[key]
    def signature(ids):
        return tuple(sorted(Counter(master.supports.get(abs(key), {}).get("command_id", 0) for key in ids).items())) if training_scores is not None else ()
    states = {(len(pinned), sum(key < 0 for key in pinned), initial_mask, signature(pinned)): (
        training_quality(pinned) if training_quality else sum(levels[key] for key in pinned), tuple(pinned))}
    truncated = False
    for chara in sorted(groups):
        checkpoint()
        updated = dict(states)
        for (count, rentals, mask, _composition), (quality, ids) in states.items():
            if count >= 6:
                continue
            for key in sorted(groups[chara]):
                next_rentals = rentals + int(key < 0)
                if require_borrowed and (next_rentals > 1 or count + 1 - next_rentals > 5):
                    continue
                chosen = tuple(sorted((*ids, key), key=lambda value: (value < 0, abs(value))))
                state_key = count + 1, next_rentals, mask | masks[key], signature(chosen)
                value = (training_quality(chosen) if training_quality else quality + levels[key]), chosen
                previous = updated.get(state_key)
                if previous is None or value[0] > previous[0] or (value[0] == previous[0] and value[1] < previous[1]):
                    updated[state_key] = value
        states = {}
        for count in range(7):
            for rentals in range(2):
                entries = [(key, value) for key, value in updated.items() if key[:2] == (count, rentals)]
                entries.sort(key=lambda item: (-item[0][2].bit_count(), -item[1][0], item[1][1]))
                truncated |= len(entries) > 256
                states.update(entries[:256])
    legal = {key: value for key, value in states.items() if not require_borrowed or key[1] == 1}
    largest = max((key[0] for key in legal), default=0)
    return [(mask, quality, [by_id[key] for key in ids], truncated)
        for (count, _rentals, mask, _composition), (quality, ids) in legal.items() if count == largest]


def find_setups(store, master, requirements, *, catalog=None, limit=24, checkpoint=None, progress=None, logger=None):
    """Rank owned-trainee setups by unmet aptitudes, missing skills, then level.

    Every legal local parent pair is screened. Up to 80 survive to a joint
    comparison with each trainee's support frontier. This is a shortlist
    search, and never claims a global race-performance optimum.
    """
    checkpoint = checkpoint or (lambda: None)
    progress = progress or (lambda *_: None)
    catalog = catalog or catalog_for(master)
    training = TrainingModel(master, catalog.training_data, requirements)
    validation = validate_recorded_practices(store, master, catalog.training_data) if training.available else None
    training_restriction = None
    if validation and validation["exact"] < validation["checked"]:
        training.available = False
        training_restriction = "Practice estimates were left out because exported practice previews disagreed with the formula."
    elif training.options["enabled"] and not training.available:
        training_restriction = "Practice estimates are unavailable for this game database or scenario."
    targets = requirements_aptitudes(requirements)
    wanted = sorted(set(int(identity) for identity in requirements.get("skill_ids", [])))
    blocked = {identity for identity in wanted if _skill_incompatible(catalog.skills.get(identity, {}), requirements)}
    all_mask = (1 << len(wanted)) - 1
    allowed_mask = sum(1 << index for index, skill in enumerate(wanted) if skill not in blocked)
    def mask(skills):
        return sum(1 << index for index, skill in enumerate(wanted) if skill in skills) & allowed_mask
    trainees = store.entities("trainees")
    pinned_card = requirements.get("card_id")
    if pinned_card is not None:
        trainees = [row for row in trainees if int(row["card_id"]) == int(pinned_card)]
    supports = store.entities("supports")
    parents = [row for row in store.entities("veterans") if not is_borrowed_veteran(row)]
    fixed_parents = {int(identity) for identity in requirements.get("parent_ids", [])}
    if not fixed_parents.issubset({int(row["trained_chara_id"]) for row in parents}):
        raise ValueError("Choose parent veterans from your own imported collection")
    if len(fixed_parents) > 2:
        raise ValueError("Choose at most two parents")
    branches = {}
    for parent in parents:
        stars, skills = _branch_evidence(master, catalog, parent)
        branches[int(parent["trained_chara_id"])] = stars, skills, mask(skills)
    pair_rows = []
    pool = chain(combinations(parents, 2), ((parent,) for parent in parents), [()])
    for pair in pool:
        checkpoint()
        if not fixed_parents.issubset({int(row["trained_chara_id"]) for row in pair}):
            continue
        characters = tuple(master.character_id(row["card_id"]) for row in pair)
        if len(set(characters)) != len(characters):
            continue
        stars, combined_mask = defaultdict(int), 0
        for row in pair:
            branch_stars, _skills, branch_mask = branches[int(row["trained_chara_id"])]
            for group, amount in branch_stars.items():
                stars[group] += amount
            combined_mask |= branch_mask
        pair_rows.append((pair, characters, dict(stars), combined_mask))
    results = []
    examined_pairs, used_shortlist = 0, False
    for index, trainee in enumerate(trainees):
        checkpoint()
        identity = int(trainee["card_id"])
        character = master.character_id(identity)
        from uma_workbench.goals import support_slots
        pinned_deck, borrowed_id = support_slots(requirements, {int(row["support_card_id"]) for row in supports})
        training_scores = None
        if training.available:
            available = [*supports, *({"support_card_id": sid, "borrowed": True} for sid in
                ([borrowed_id] if borrowed_id is not None else master.supports))]
            training_scores = training.card_scores(trainee, available)
        decks = _deck_frontier(master, catalog, supports, character, wanted,
            pinned_deck, checkpoint, training_scores=training_scores, training_quality=training.proxy_quality if training.available else None,
            require_borrowed=True, borrowed_id=borrowed_id)
        if not decks:
            continue
        estimates = {}
        if training.available:
            grouped = defaultdict(list)
            for deck in decks:
                grouped[deck[0]].append(deck)
            used_shortlist |= any(len(group) > 3 for group in grouped.values())
            decks = [deck for group in grouped.values() for deck in sorted(group, key=lambda row: (-row[1], tuple(s["support_card_id"] for s in row[2])))[:3]]
            for deck in decks:
                checkpoint()
                estimates[tuple((row["support_card_id"], bool(row.get("borrowed"))) for row in deck[2])] = training.estimate(trainee, deck[2])
        base_skills = catalog.base_skills(master, trainee)
        base_mask = mask(base_skills)
        support_union = 0
        for deck_mask, *_ in decks:
            support_union |= deck_mask & allowed_mask
        base = catalog.rarity_row(master, trainee)
        candidates = []
        for pair, characters, stars, parent_mask in pair_rows:
            if character in characters:
                continue
            aptitude_rows, gap = [], 0
            for column, label, group in APTITUDES:
                if column not in targets:
                    continue
                initial = _initial_aptitude_rank(base[column], stars.get(group, 0)) if base.get(column) else None
                target = targets[column]
                deficit = max(0, min(target, 7) - initial) if initial is not None else min(target, 7)
                s_roll = target == 8
                if s_roll and not stars.get(group):
                    deficit += 1
                gap += deficit
                aptitude_rows.append({"column": column, "label": label, "base": base.get(column),
                    "initial": initial, "target": target, "stars": stars.get(group, 0),
                    "needs_s_roll": s_roll, "gap": deficit})
            key = (gap, len(wanted) - ((base_mask | parent_mask | support_union) & allowed_mask).bit_count(),
                2 - len(pair), -parent_mask.bit_count(), tuple(int(row["trained_chara_id"]) for row in pair))
            candidates.append((key, pair, parent_mask, aptitude_rows))
        candidates.sort(key=lambda row: row[0])
        used_shortlist |= len(candidates) > 80
        examined_pairs += len(candidates)
        trainee_results = []
        for parent_key, pair, parent_mask, aptitudes in candidates[:80]:
            checkpoint()
            best = min(decks, key=lambda row: (
                len(wanted) - ((base_mask | parent_mask | row[0]) & allowed_mask).bit_count(),
                -(estimates[tuple((s["support_card_id"], bool(s.get("borrowed"))) for s in row[2])]["value"]) if training.available else 0,
                -(estimates[tuple((s["support_card_id"], bool(s.get("borrowed"))) for s in row[2])]["skill_points"]) if training.available else 0,
                -(row[0] & ~base_mask & ~parent_mask).bit_count(), -row[1],
                tuple(int(s["support_card_id"]) for s in row[2])))
            deck_mask, deck_level, deck, truncated = best
            estimate = estimates.get(tuple((s["support_card_id"], bool(s.get("borrowed"))) for s in deck))
            deck_level = sum(master.support_level(s) or 0 for s in deck)
            covered = (base_mask | parent_mask | deck_mask) & allowed_mask
            missing = [skill for bit, skill in enumerate(wanted) if not (covered & (1 << bit))]
            slot_gap = (2 - len(pair)) + (6 - len(deck))
            conditional = sum(row["needs_s_roll"] for row in aptitudes)
            growth = sum(master.cards.get(identity, {}).get("talent_" + ("pow" if stat == "power" else stat), 0)
                for stat, target in requirements.get("stats", {}).items() if target)
            rank = (parent_key[0], len(missing), slot_gap, conditional,
                -(estimate["value"] if estimate else 0), -(estimate["skill_points"] if estimate else 0),
                -base_mask.bit_count(), -growth, -deck_level,
                identity, tuple(int(row["trained_chara_id"]) for row in pair))
            row = {"card_id": identity, "trainee": dict(trainee), "parents": list(pair), "supports": deck,
                "aptitudes": aptitudes, "missing_skills": missing,
                "aptitude_gap": parent_key[0], "slot_gap": slot_gap,
                "requires_s_roll": bool(conditional), "support_level_total": deck_level,
                "growth_alignment": growth, "frontier_pruned": truncated,
                "training": estimate,
                "requirements": dict(requirements), "rank_key": rank}
            trainee_results.append(row)
        trainee_results.sort(key=lambda row: row["rank_key"])
        for row in trainee_results[:2]:
            routes = []
            for skill in wanted:
                providers = []
                if skill in base_skills:
                    providers.append({"kind": "trainee", "card_id": identity})
                for support in row["supports"]:
                    sid = int(support["support_card_id"])
                    if skill in catalog.hint_skills(master, sid):
                        providers.append({"kind": "support_hint", "support_card_id": sid})
                    if skill in catalog.event_skills(sid):
                        providers.append({"kind": "support_event", "support_card_id": sid})
                for parent in row["parents"]:
                    if skill in branches[int(parent["trained_chara_id"])][1]:
                        providers.append({"kind": "inheritance", "trained_chara_id": int(parent["trained_chara_id"]),
                            "card_id": int(parent["card_id"])})
                routes.append({"skill_id": skill, "sources": providers, "incompatible": skill in blocked})
            row["skills"] = routes
            row["career_comparison"] = completed_career_comparison(store, requirements, identity, row["supports"], veterans=parents)
            results.append(row)
        progress(int(100 * (index + 1) / max(1, len(trainees))), "Comparing trainees, inheritance and support training…")
    results.sort(key=lambda row: row["rank_key"])
    return {"setups": results[:limit], "trainees_examined": len(trainees), "parent_pairs_examined": examined_pairs,
        "shortlisted": used_shortlist or any(row["frontier_pruned"] for row in results),
        "blocked_skills": sorted(blocked), "event_data_available": catalog.event_data_available,
        "training_enabled": training.available,
        "training_validation": validation, "training_restriction": training_restriction,
        "notes": ["Every suggested support deck reserves one borrowed slot and at most five owned slots. Check the suggested rental is available from your friends.", "Ranked by aptitude gaps, missing skill sources and complete lineups, with practice output considered when enabled.",
            "Practice subtotals use the saved comparison conditions; they do not forecast a complete career. Hints, events and inheritance still depend on the career.",
            "Support-event sources are individual possibilities. Event choices and chain endings can conflict; check the listed routes."]}


def matching_veterans(store, master, requirements, *, catalog=None):
    catalog = catalog or catalog_for(master)
    targets = requirements_aptitudes(requirements)
    wanted = {int(identity) for identity in requirements.get("skill_ids", [])}
    result = []
    for row in store.entities("veterans"):
        if is_borrowed_veteran(row):
            continue
        if requirements.get("card_id") and int(row["card_id"]) != int(requirements["card_id"]):
            continue
        if any(int(row.get(key, 0)) < target for key, target in targets.items()):
            continue
        if any(int(row.get(key, 0)) < target for key, target in requirements.get("stats", {}).items()):
            continue
        learned = catalog.lower_skills(int(skill["skill_id"]) for skill in row.get("skill_array", []))
        if wanted.issubset(learned):
            result.append(row)
    return result
