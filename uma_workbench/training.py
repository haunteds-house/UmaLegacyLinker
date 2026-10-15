"""Scenario-aware practice estimates from the user's MDB and support levels.

This is an independent implementation of the community-observed training
formula. It predicts practice contributions under stated conditions, not final
career stats. See docs/TRAINING_MODEL.md for formulas, references and limits.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from math import floor, prod
import json


STATS = ("speed", "stamina", "power", "guts", "wiz")
LABELS = ("Speed", "Stamina", "Power", "Guts", "Wit")
OUTPUTS = (*STATS, "skill_points")
COMMANDS = {101: "speed", 105: "stamina", 102: "power", 103: "guts", 106: "wiz"}
SUMMER = {101: 601, 105: 602, 102: 603, 103: 604, 106: 605}
TARGETS = {1: "speed", 2: "stamina", 3: "power", 4: "guts", 5: "wiz", 30: "skill_points", 10: "energy"}
SCENARIOS = {"URA": 1, "Unity Cup": 2, "Our Grand Concert": 3, "Trackblazer": 4}
BONUS_TYPES = {"speed": 3, "stamina": 4, "power": 5, "guts": 6, "wiz": 7, "skill_points": 30}
INITIAL_TYPES = {"speed": 9, "stamina": 10, "power": 11, "guts": 12, "wiz": 13}
DEFAULT_OPTIONS = {"enabled": True, "facility_level": 3, "motivation": 5,
    "friendship_share": 60, "sessions": dict.fromkeys(STATS, 10),
    "borrowed_level": 50, "borrowed_limit_breaks": 4, "later_fans": 100000,
    "energy": 70, "max_energy": 100}
MODEL_VERSION = "practice-1"


def options_for(requirements):
    supplied = requirements.get("training", {})
    result = {**DEFAULT_OPTIONS, **supplied}
    result["sessions"] = {**DEFAULT_OPTIONS["sessions"], **supplied.get("sessions", {})}
    for key, low, high in (("facility_level", 1, 5), ("motivation", 1, 5),
            ("friendship_share", 0, 100), ("borrowed_level", 1, 50), ("borrowed_limit_breaks", 0, 4),
            ("later_fans", 0, 10000000), ("energy", 1, 200), ("max_energy", 100, 200)):
        value = result[key]
        if not isinstance(value, int) or not low <= value <= high:
            raise ValueError("Choose valid practice conditions and borrowed support levels")
    if result["energy"] > result["max_energy"]:
        raise ValueError("Practice energy cannot exceed maximum energy")
    if any(not isinstance(value, int) or not 0 <= value <= 78 for value in result["sessions"].values()):
        raise ValueError("Practice counts must be whole numbers from 0 to 78")
    if set(result["sessions"]) != set(STATS) or sum(result["sessions"].values()) > 78:
        raise ValueError("Use at most 78 planned practices across the five training types")
    if result["enabled"] and not sum(result["sessions"].values()):
        raise ValueError("Plan at least one practice, or turn off training comparison")
    return result


def curve_value(row, level):
    """Interpolate unlocked nonnegative anchors; -1 is absent, not zero."""
    anchors = [(1, row.get("init", -1))] + [(n, row.get(f"limit_lv{n}", -1)) for n in range(5, 51, 5)]
    anchors = [(n, value) for n, value in anchors if value >= 0]
    before = [(n, value) for n, value in anchors if n <= level]
    if not before:
        return 0
    left, value = before[-1]
    right = next(((n, v) for n, v in anchors if n > level), None)
    return floor(value + (right[1] - value) * (level - left) / (right[0] - left) + 1e-9) if right else value


@dataclass
class TrainingData:
    effects: dict = field(default_factory=dict)
    uniques: dict = field(default_factory=dict)
    bases: dict = field(default_factory=dict)
    scenarios: dict = field(default_factory=dict)

    @classmethod
    def load(cls, master):
        result = cls()
        if not master.path:
            return result
        with master.connection() as con:
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "support_card_effect_table" in tables:
                for row in con.execute("SELECT * FROM support_card_effect_table"):
                    result.effects.setdefault(row["id"], []).append(dict(row))
            if "support_card_unique_effect" in tables:
                result.uniques = {row["id"]: dict(row) for row in con.execute("SELECT * FROM support_card_unique_effect")}
            if "single_mode_training_effect" in tables:
                for row in con.execute("SELECT * FROM single_mode_training_effect WHERE result_state=2 AND sub_id=1"):
                    if row["target_type"] in TARGETS:
                        result.bases.setdefault((row["scenario_id"], row["command_id"]), {})[TARGETS[row["target_type"]]] = row["effect_value"]
            if "single_mode_scenario" in tables:
                result.scenarios = {row["id"]: dict(row) for row in con.execute("SELECT * FROM single_mode_scenario")}
        return result

    def available(self, scenario):
        return bool(self.effects) and scenario in (1, 2, 3, 4) and all(
            (scenario, command) in self.bases and (scenario, SUMMER[command]) in self.bases for command in COMMANDS)

    def base(self, scenario, command, level):
        first = self.bases.get((scenario, command), {})
        last = self.bases.get((scenario, SUMMER.get(command)), {})
        if not first or not last or not 1 <= level <= 5:
            raise ValueError("This scenario's practice values are missing from the game data")
        main = COMMANDS[command]
        result = {}
        for stat in (*OUTPUTS, "energy"):
            start, end = first.get(stat, 0), last.get(stat, 0)
            if stat == "energy":
                fraction = (0, 1/6, 2/6, 4/6, 1)[level - 1]
            elif stat == main:
                fraction = ((0, 1/5, 2/5, 4/5, 1) if scenario == 1 and main == "guts"
                    else (0, 1/4, 2/4, 3/4, 1))[level - 1]
            elif main == "guts":
                fraction = ((0, 0, 0, 1, 1) if stat == "speed" and scenario != 1 else (0, 0, 0, 0, 1))[level - 1]
            else:
                fraction = (0, 0, 0, 1/2, 1)[level - 1]
            # Negative energy costs use truncation of their absolute increase.
            change = floor(abs(end - start) * fraction + 1e-9)
            result[stat] = start + (change if end >= start else -change)
        return result


@dataclass
class SupportProfile:
    identity: int
    kind: str
    level: int | None
    base: dict
    unique: dict
    special: list
    notes: list
    initial: dict
    borrowed: bool = False


def support_profile(master, data, row, options):
    identity = int(row["support_card_id"])
    card = master.supports.get(identity, {})
    borrowed = bool(row.get("borrowed"))
    level = options["borrowed_level"] if borrowed else master.support_level(row)
    limit = options["borrowed_limit_breaks"] if borrowed else int(row.get("limit_break_count", 4))
    cap = master.support_limits.get(card.get("rarity"), {}).get(f"limit_{limit}")
    notes = []
    if level is None:
        notes.append("Level unknown: using level 1 effects")
    if level is not None and cap is not None and level > cap:
        notes.append("Effects capped at the exported limit breaks")
        level = cap
    effective = max(1, level or 1)
    effect_id = card.get("effect_table_id", identity)
    if effect_id not in data.effects:
        notes.append("Support effects missing from this game data")
    base = {item["type"]: curve_value(item, effective) for item in data.effects.get(effect_id, [])}
    unique, special = {}, []
    item = data.uniques.get(card.get("unique_effect_id"), {})
    if effective >= item.get("lv", 999):
        for slot in range(2):
            kind = item.get(f"type_{slot}", 0)
            values = [item.get(f"value_{slot}" + (f"_{index}" if index else ""), 0) for index in range(5)]
            if 0 < kind < 100:
                unique[kind] = unique.get(kind, 0) + values[0]
            elif kind:
                special.append((kind, values))
                if kind not in {101, 102, 103, 104, 105, 108, 109, 110, 111, 113, 114, 115}:
                    notes.append("A conditional unique effect is not included")
    kind = COMMANDS.get(card.get("command_id"), "group" if card.get("support_card_type") == 3 else "friend")
    if kind in ("friend", "group"):
        notes.append("Outing rewards and group friendship are not included")
    initial = {stat: base.get(effect, 0) + unique.get(effect, 0) for stat, effect in INITIAL_TYPES.items()}
    return SupportProfile(identity, kind, level, base, unique, special, notes, initial, borrowed)


def conditional_effects(profile, *, bond, training, level, participants, friend, deck_types,
        fans=0, energy=70, max_energy=100, total_bond=0):
    effects = defaultdict(int)
    for kind, value in profile.special:
        a, b, c, d, e = value
        if kind == 101 and bond >= a:
            effects[b] += c
            effects[d] += e
        elif kind == 102 and bond >= a and training != profile.kind:
            effects[8] += b
        elif kind == 103 and len(deck_types) >= a:
            effects[8] += b
        elif kind == 104 and a > 0:
            effects[8] += min(b, fans // a)
        elif kind == 108:
            effects[a] += min(e, int((max_energy - b) * c / 100 + d))
        elif kind == 109 and b > 0:
            effects[a] += total_bond // b
        elif kind == 110:
            effects[a] += participants * b
        elif kind == 111:
            effects[a] += min(5, level) * b
        elif kind == 113 and friend:
            effects[a] += b
        elif kind == 114 and b > 0:
            effects[a] += min(20, c - max(0, (100 - energy) // b))
    return effects


def placement_probability(profile, training):
    if profile.kind in ("friend", "group"):
        return 1 / 6
    specialty = (1 + profile.base.get(19, 0) / 100) * (1 + profile.unique.get(19, 0) / 100)
    return (specialty if profile.kind == training else 1) / (specialty + 4.5)


def session_gains(data, scenario, command, level, profiles, growth, *, motivation=5,
        bonds=None, deck_types=None, total_bond=None, extra_members=0, fans=0,
        energy=70, max_energy=100, current=None):
    """One successful practice with known participants; friendship is per card."""
    base = data.base(scenario, command, level)
    training = COMMANDS[command]
    bonds = bonds or [100] * len(profiles)
    if len(bonds) != len(profiles) or len(profiles) + extra_members > 5:
        raise ValueError("A practice has up to five participants and a bond for each support")
    deck_types = deck_types or Counter(profile.kind for profile in profiles)
    total_bond = sum(bonds) if total_bond is None else total_bond
    friendship = [profile.kind == training and bond >= 80 for profile, bond in zip(profiles, bonds)]
    active = any(friendship)
    special = [conditional_effects(profile, bond=bond, training=training, level=level,
        participants=len(profiles), friend=active, deck_types=deck_types, fans=fans,
        energy=energy, max_energy=max_energy, total_bond=total_bond) for profile, bond in zip(profiles, bonds)]
    def amount(profile, index, kind):
        return profile.base.get(kind, 0) + profile.unique.get(kind, 0) + special[index].get(kind, 0)
    training_factor = 1 + sum(amount(p, i, 8) for i, p in enumerate(profiles)) / 100
    mood_factor = 1 + (motivation - 3) / 10 * (1 + sum(amount(p, i, 2) for i, p in enumerate(profiles)) / 100)
    friends = prod((1 + p.base.get(1, 0) / 100) * (1 + p.unique.get(1, 0) / 100)
        * (1 + special[i].get(1, 0) / 100) for i, p in enumerate(profiles) if friendship[i])
    people_factor = 1 + (len(profiles) + extra_members) * .05
    result = {}
    for stat in OUTPUTS:
        value = base.get(stat, 0)
        if value:
            bonus = sum(amount(p, i, BONUS_TYPES[stat]) + (special[i].get(41, 0) if stat != "skill_points" else 0)
                for i, p in enumerate(profiles))
            value = min(100, (value + bonus) * (1 + growth.get(stat, 0) / 100)
                * training_factor * mood_factor * friends * people_factor)
        gain = floor(value + 1e-8)
        if stat != "skill_points" and current is not None:
            before = current.get(stat, 0)
            gain = gain if before + gain <= 1200 else max(0, 1200 - before) + floor((gain - max(0, 1200 - before)) / 2)
        result[stat] = gain
    if base["energy"] < 0:
        reduction = sum(amount(p, i, 28) for i, p in enumerate(profiles))
        result["energy"] = base["energy"] - int(base["energy"] * min(100, reduction) / 100)
    else:
        result["energy"] = base["energy"] + sum(amount(p, i, 31) for i, p in enumerate(profiles) if friendship[i])
    return result


def participant_distribution(profiles, training):
    """Independent placements, capped at five; six-way stacks drop one uniformly."""
    probabilities = [placement_probability(profile, training) for profile in profiles]
    outcomes = defaultdict(float)
    for mask in range(1 << len(profiles)):
        ids = tuple(i for i in range(len(profiles)) if mask & (1 << i))
        chance = prod(p if mask & (1 << i) else 1 - p for i, p in enumerate(probabilities))
        if len(ids) > 5:
            for subset in combinations(ids, 5):
                outcomes[subset] += chance / 6
        else:
            outcomes[ids] += chance
    return outcomes


class TrainingModel:
    def __init__(self, master, data, requirements):
        self.master, self.data, self.requirements = master, data, requirements
        self.options = options_for(requirements)
        self.scenario = SCENARIOS.get(requirements.get("scenario", "URA"))
        self.available = self.options["enabled"] and data.available(self.scenario)
        self._profiles, self._estimates = {}, {}

    def profile(self, row):
        key = int(row["support_card_id"]), self.master.support_level(row), row.get("limit_break_count"), bool(row.get("borrowed"))
        if key not in self._profiles:
            self._profiles[key] = support_profile(self.master, self.data, row, self.options)
        return self._profiles[key]

    def estimate(self, trainee, deck):
        if not self.available:
            return None
        profiles = [self.profile(row) for row in deck]
        card = self.master.cards.get(int(trainee["card_id"]), {})
        growth = {stat: card.get("talent_" + ("pow" if stat == "power" else stat), 0) for stat in STATS}
        key = tuple((p.identity, p.level, p.borrowed) for p in profiles), tuple(growth.values())
        if key not in self._estimates:
            level = self.options["facility_level"]
            deck_types = Counter(profile.kind for profile in profiles)
            initial = {stat: sum(p.initial[stat] for p in profiles) for stat in STATS}
            for p in profiles:
                for kind, _values in p.special:
                    if kind == 105:
                        for kind2, count in deck_types.items():
                            for stat in STATS:
                                initial[stat] += count * (2 if kind2 in ("friend", "group") else 10 if kind2 == stat else 0)
            practices, gains = [], dict.fromkeys(OUTPUTS, 0.)
            for command, training in COMMANDS.items():
                early, ready = dict.fromkeys((*OUTPUTS, "energy"), 0.), dict.fromkeys((*OUTPUTS, "energy"), 0.)
                for ids, probability in participant_distribution(profiles, training).items():
                    selected = [profiles[i] for i in ids]
                    for built, output in ((False, early), (True, ready)):
                        team_bond = sum(values[1] for p in profiles for kind, values in p.special if kind == 115 and values[0] == 14)
                        initial_bonds = {p.identity: min(79, p.base.get(14, 0) + p.unique.get(14, 0) + team_bond) for p in profiles}
                        bonds = [100 if built else initial_bonds[p.identity] for p in selected]
                        full_bond = 100 * len(profiles) if built else sum(initial_bonds.values())
                        result = session_gains(self.data, self.scenario, command, level, selected, growth,
                            motivation=self.options["motivation"], bonds=bonds, deck_types=deck_types, total_bond=full_bond,
                            fans=self.options["later_fans"] if built else 0, energy=self.options["energy"], max_energy=self.options["max_energy"])
                        for stat in output:
                            output[stat] += probability * result[stat]
                share = self.options["friendship_share"] / 100
                average = {stat: early[stat] * (1 - share) + ready[stat] * share for stat in early}
                count = self.options["sessions"][training]
                for stat in gains:
                    gains[stat] += average[stat] * count
                practices.append({"type": training, "count": count, "early": early, "ready": ready, "average": average})
            self._estimates[key] = {"gains": gains, "initial": initial, "practices": practices}
        result = self._estimates[key]
        rarity_options = getattr(self.master, "_planning_catalog", None)
        start = rarity_options.rarity_row(self.master, trainee) if rarity_options else {}
        baseline = {stat: start.get("pow" if stat == "power" else stat, 0) + result["initial"][stat] for stat in STATS}
        cap = self.data.scenarios.get(self.scenario, {})
        subtotal = {}
        for stat in STATS:
            amount = result["gains"][stat]
            remaining = max(0, 1200 - baseline[stat])
            converted = min(amount, remaining) + max(0, amount - remaining) / 2
            name = "pow" if stat == "power" else stat
            maximum = start.get("max_" + name, 1200) + cap.get("max_" + name, 0)
            subtotal[stat] = min(maximum, baseline[stat] + converted)
        targets = {k: v for k, v in self.requirements.get("stats", {}).items() if v > 0}
        value = (sum(min(subtotal[stat], target) / target for stat, target in targets.items()) / len(targets)
            if targets else sum(subtotal.values()) / 1000)
        gaps = {stat: max(0, target - subtotal[stat]) for stat, target in targets.items()}
        notes = sorted({note for p in profiles for note in p.notes})
        return {**result, "baseline": baseline, "subtotal": subtotal, "target_gaps": gaps,
            "value": value, "skill_points": result["gains"]["skill_points"], "notes": notes,
            "supports": [{"support_card_id": p.identity, "level": p.level, "kind": p.kind,
                "borrowed": p.borrowed, "notes": p.notes} for p in profiles],
            "options": self.options, "scenario": self.scenario, "model_version": MODEL_VERSION}

    def card_scores(self, trainee, supports):
        baseline = self.estimate(trainee, [])
        self._proxy_base = baseline["subtotal"]
        self._proxy_deltas = {}
        for row in supports:
            result = self.estimate(trainee, [row])
            self._proxy_deltas[int(row["support_card_id"])] = tuple(
                result["subtotal"][stat] - baseline["subtotal"][stat] for stat in STATS)
        return {identity: self.proxy_quality((identity,)) for identity in self._proxy_deltas}

    def proxy_quality(self, identities):
        projected = {stat: self._proxy_base[stat] + sum(self._proxy_deltas[identity][i] for identity in identities)
            for i, stat in enumerate(STATS)}
        targets = {k: v for k, v in self.requirements.get("stats", {}).items() if v > 0}
        return (sum(min(projected[stat], target) / target for stat, target in targets.items()) / len(targets)
            if targets else sum(projected.values()) / 1000)


def completed_career_comparison(store, requirements, card_id, deck, *, veterans=None):
    """Historical results are context, not validation of a final-stat forecast."""
    from uma_legacy_linker.legacy_linker import is_borrowed_veteran
    wanted = {int(row["support_card_id"]) for row in deck}
    scenario = SCENARIOS.get(requirements.get("scenario", "URA"))
    rows = []
    for row in store.entities("veterans") if veterans is None else veterans:
        if is_borrowed_veteran(row) or int(row.get("card_id", 0)) != card_id or row.get("scenario_id") != scenario:
            continue
        cards = {int(item["support_card_id"]) for item in row.get("support_card_list", [])}
        overlap = len(cards & wanted)
        rows.append({"stats": {stat: row.get(stat, 0) for stat in STATS}, "matching_supports": overlap,
            "same_deck": len(cards) == len(wanted) == 6 and cards == wanted,
            "rating": row.get("rank_score", 0)})
    rows.sort(key=lambda row: (-row["matching_supports"], -row["rating"]))
    return {"count": len(rows), "rows": rows[:3], "same_deck_count": sum(row["same_deck"] for row in rows)}


def validate_recorded_practices(store, master, data):
    """Compare unique enabled exported previews, skipping unmodelled additions."""
    with store.connection() as con:
        artifacts = [json.loads(row[0]) for row in con.execute("SELECT payload FROM artifacts WHERE kind='career'")]
    seen, checks, skipped = set(), [], Counter()
    options = options_for({})
    for artifact in artifacts:
        common = artifact.get("single_mode_load_common", {}) if isinstance(artifact, dict) else {}
        chara = common.get("chara_info", {})
        scenario = chara.get("scenario_id")
        if not data.available(scenario):
            continue
        cards = chara.get("support_card_array", [])
        profiles = {row.get("position", i + 1): support_profile(master, data, row, options) for i, row in enumerate(cards)}
        bonds = {row.get("training_partner_id", row.get("target_id")): row.get("evaluation", 0) for row in chara.get("evaluation_info_array", [])}
        growth = {stat: master.cards.get(chara.get("card_id"), {}).get("talent_" + ("pow" if stat == "power" else stat), 0) for stat in STATS}
        for command in common.get("home_info", {}).get("command_info_array", []):
            identity = command.get("command_id")
            if identity not in COMMANDS or not command.get("is_enable"):
                continue
            fingerprint = json.dumps([chara.get("card_id"), scenario, chara.get("turn"),
                chara.get("motivation"), chara.get("vital"), chara.get("max_vital"), chara.get("fans"),
                {stat: chara.get(stat, 0) for stat in STATS}, chara.get("chara_effect_id_array"),
                cards, bonds, command], sort_keys=True)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            ids = command.get("training_partner_array", [])
            if any(identity not in profiles for identity in ids):
                skipped["Scenario teammates"] += 1
                continue
            if any(profiles[identity].notes for identity in ids) or chara.get("chara_effect_id_array"):
                skipped["Conditional effects or character conditions"] += 1
                continue
            actual = {TARGETS[row["target_type"]]: row["value"] for row in command.get("params_inc_dec_info_array", []) if row["target_type"] in TARGETS}
            predicted = session_gains(data, scenario, identity, command["level"], [profiles[i] for i in ids], growth,
                motivation=chara.get("motivation", 3), bonds=[bonds.get(i, 0) for i in ids],
                deck_types=Counter(profile.kind for profile in profiles.values()), total_bond=sum(bonds.get(i, 0) for i in profiles),
                fans=chara.get("fans", 0), energy=chara.get("vital", 70), max_energy=chara.get("max_vital", 100), current=chara)
            errors = {stat: predicted.get(stat, 0) - actual.get(stat, 0) for stat in OUTPUTS}
            checks.append({"practice": COMMANDS[identity], "exact": not any(errors.values()), "errors": errors})
    return {"checked": len(checks), "exact": sum(row["exact"] for row in checks),
        "mean_absolute_error": sum(abs(v) for row in checks for v in row["errors"].values()) / (len(checks) * 6) if checks else None,
        "skipped": dict(skipped), "checks": checks, "model_version": MODEL_VERSION}
