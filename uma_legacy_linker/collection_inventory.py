from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from uma_legacy_linker.legacy_linker import text_map


UNITY_SKILL_FAMILIES = {
    "ignited spirit: wit",
    "racing spirit: stamina",
}


def normal_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def unity_family(value: object) -> str:
    value = normal_name(value)
    base = re.sub(r"\s*\+$", "", value).strip()
    return base if base in UNITY_SKILL_FAMILIES else value


def find_sibling_export(veterans_path: str | Path, stem: str) -> Path | None:
    """Find the newest umadump sibling such as card_data(1).json.

    Explicit user choices are stored by the UI. This is deliberately only a
    fallback so moving a trained-character export into a new snapshot folder
    automatically discovers the other collection files beside it.
    """
    path = Path(veterans_path).expanduser()
    parent = path.parent if path.parent != Path("") else Path.cwd()
    if not parent.is_dir():
        return None
    candidates = [
        candidate
        for candidate in parent.glob(f"{stem}*.json")
        if candidate.is_file()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate.stat().st_mtime_ns)


def resolve_collection_path(
    configured: str | Path | None,
    veterans_path: str | Path,
    stem: str,
) -> Path | None:
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return candidate.resolve()
    detected = find_sibling_export(veterans_path, stem)
    return detected.resolve() if detected is not None else None


def load_json_rows(path: str | Path | None, keys: Iterable[str] = ()) -> list[dict[str, Any]]:
    if not path:
        return []
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        return []
    try:
        with candidate.open("r", encoding="utf-8-sig") as stream:
            payload = json.load(stream)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = []
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                rows = value
                break
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def collection_file_count(path: str | Path | None, keys: Iterable[str] = ()) -> int | None:
    if not path or not Path(path).expanduser().is_file():
        return None
    rows = load_json_rows(path, keys)
    return len(rows)


@dataclass(frozen=True)
class CollectionPaths:
    trainee_cards: Path | None
    support_cards: Path | None


@dataclass(frozen=True)
class CollectionSummary:
    trainee_cards: int
    support_cards: int
    trainee_path: str
    support_path: str


class CollectionPlanner:
    """Resolve owned trainee/support skill sources against the current master.

    The planner intentionally separates *skill access* from support-card meta
    strength. Owned level/LB/rarity is used as a quality prior, but the output
    calls these deck candidates rather than claiming a full scenario simulator.
    """

    def __init__(
        self,
        master_path: str | Path,
        *,
        trainee_cards_path: str | Path | None,
        support_cards_path: str | Path | None,
    ) -> None:
        self.master_path = Path(master_path).expanduser().resolve()
        self.trainee_path = (
            Path(trainee_cards_path).expanduser().resolve()
            if trainee_cards_path and Path(trainee_cards_path).expanduser().is_file()
            else None
        )
        self.support_path = (
            Path(support_cards_path).expanduser().resolve()
            if support_cards_path and Path(support_cards_path).expanduser().is_file()
            else None
        )
        self.owned_trainees = load_json_rows(
            self.trainee_path,
            ("card_data_array", "cards", "data"),
        )
        self.owned_supports = load_json_rows(
            self.support_path,
            ("support_card_data_array", "supports", "data"),
        )

        self.connection = sqlite3.connect(
            f"file:{self.master_path.as_posix()}?mode=ro", uri=True
        )
        self.connection.row_factory = sqlite3.Row
        self.tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.skill_names = text_map(self.connection, 47) if "text_data" in self.tables else {}
        self.chara_names = text_map(self.connection, 6) if "text_data" in self.tables else {}
        self.card_names = text_map(self.connection, 4) if "text_data" in self.tables else {}
        self.support_names = text_map(self.connection, 75) if "text_data" in self.tables else {}
        self.support_titles = text_map(self.connection, 76) if "text_data" in self.tables else {}

        self.skill_group_by_id: dict[int, int] = {}
        self.skill_ids_by_group: dict[int, set[int]] = {}
        self.skill_ids_by_name: dict[str, set[int]] = {}
        if "skill_data" in self.tables:
            for row in self.connection.execute(
                "SELECT id, group_id FROM skill_data"
            ):
                skill_id = int(row["id"])
                group_id = int(row["group_id"])
                self.skill_group_by_id[skill_id] = group_id
                self.skill_ids_by_group.setdefault(group_id, set()).add(skill_id)
                name = self.skill_names.get(skill_id, "")
                if name:
                    self.skill_ids_by_name.setdefault(normal_name(name), set()).add(skill_id)
                    family = unity_family(name)
                    if family != normal_name(name):
                        self.skill_ids_by_name.setdefault(family, set()).add(skill_id)

        self.card_meta: dict[int, dict[str, Any]] = {}
        if "card_data" in self.tables:
            columns = self._columns("card_data")
            select = ["id", "chara_id"]
            if "available_skill_set_id" in columns:
                select.append("available_skill_set_id")
            for row in self.connection.execute(
                f"SELECT {', '.join(select)} FROM card_data"
            ):
                card_id = int(row["id"])
                self.card_meta[card_id] = {
                    "card_id": card_id,
                    "chara_id": int(row["chara_id"]),
                    "uma_name": self.chara_names.get(int(row["chara_id"]), f"Uma {int(row['chara_id'])}"),
                    "card_name": self.card_names.get(card_id, self.chara_names.get(int(row["chara_id"]), f"Card {card_id}")),
                    "available_skill_set_id": int(row["available_skill_set_id"] or 0)
                    if "available_skill_set_id" in row.keys()
                    else 0,
                }

        self.available_skills: dict[int, list[tuple[int, int]]] = {}
        if "available_skill_set" in self.tables:
            columns = self._columns("available_skill_set")
            if {"available_skill_set_id", "skill_id"}.issubset(columns):
                rank_expr = "need_rank" if "need_rank" in columns else "0 AS need_rank"
                for row in self.connection.execute(
                    f"SELECT available_skill_set_id, skill_id, {rank_expr} FROM available_skill_set"
                ):
                    set_id = int(row["available_skill_set_id"])
                    self.available_skills.setdefault(set_id, []).append(
                        (int(row["skill_id"]), int(row["need_rank"] or 0))
                    )

        self.support_meta: dict[int, dict[str, Any]] = {}
        if "support_card_data" in self.tables:
            columns = self._columns("support_card_data")
            select = ["id", "chara_id"]
            if "rarity" in columns:
                select.append("rarity")
            if "support_card_type" in columns:
                select.append("support_card_type")
            for row in self.connection.execute(
                f"SELECT {', '.join(select)} FROM support_card_data"
            ):
                support_id = int(row["id"])
                title = self.support_titles.get(support_id, "")
                full = self.support_names.get(support_id, "")
                name = full or title or f"Support {support_id}"
                self.support_meta[support_id] = {
                    "support_card_id": support_id,
                    "chara_id": int(row["chara_id"]),
                    "chara_name": self.chara_names.get(int(row["chara_id"]), ""),
                    "name": name,
                    "title": title,
                    "rarity": int(row["rarity"] or 0) if "rarity" in row.keys() else 0,
                    "support_card_type": int(row["support_card_type"] or 0)
                    if "support_card_type" in row.keys()
                    else 0,
                }

        self.support_hint_groups: dict[int, set[int]] = {}
        if "single_mode_hint_gain" in self.tables:
            columns = self._columns("single_mode_hint_gain")
            required = {"support_card_id", "hint_value_1"}
            if required.issubset(columns):
                where = " WHERE hint_gain_type = 0" if "hint_gain_type" in columns else ""
                for row in self.connection.execute(
                    "SELECT support_card_id, hint_value_1 FROM single_mode_hint_gain" + where
                ):
                    support_id = int(row["support_card_id"])
                    skill_id = int(row["hint_value_1"] or 0)
                    group_id = self.skill_group_by_id.get(skill_id)
                    if group_id is not None:
                        self.support_hint_groups.setdefault(support_id, set()).add(group_id)

    def close(self) -> None:
        self.connection.close()

    def _columns(self, table: str) -> set[str]:
        return {
            str(row[1]) for row in self.connection.execute(f"PRAGMA table_info('{table}')")
        }

    def summary(self) -> CollectionSummary:
        return CollectionSummary(
            trainee_cards=len(self.owned_trainees),
            support_cards=len(self.owned_supports),
            trainee_path=str(self.trainee_path or ""),
            support_path=str(self.support_path or ""),
        )

    def target_group_ids(self, target: Any) -> set[int]:
        factor_type = str(getattr(target, "factor_type", "") or "")
        if factor_type not in {"white_skill", "scenario"}:
            return set()
        names = [str(getattr(target, "name", "") or "")]
        names.extend(str(value) for value in (getattr(target, "equivalents", ()) or ()))
        result: set[int] = set()
        for name in names:
            normalized = normal_name(name)
            family = unity_family(name)
            keys = {normalized, family}
            if family in UNITY_SKILL_FAMILIES:
                keys.add(family + "+")
            for key in keys:
                for skill_id in self.skill_ids_by_name.get(normal_name(key), set()):
                    group_id = self.skill_group_by_id.get(skill_id)
                    if group_id is not None:
                        result.add(group_id)
        return result

    def _owned_card_skill_groups(self, row: dict[str, Any]) -> set[int]:
        try:
            card_id = int(row.get("card_id") or 0)
            talent = int(row.get("talent_level") or 0)
        except (TypeError, ValueError):
            return set()
        meta = self.card_meta.get(card_id) or {}
        set_id = int(meta.get("available_skill_set_id") or 0)
        groups: set[int] = set()
        for skill_id, need_rank in self.available_skills.get(set_id, []):
            if need_rank and talent and need_rank > talent:
                continue
            group_id = self.skill_group_by_id.get(skill_id)
            if group_id is not None:
                groups.add(group_id)
        # Player data may also expose unlocked character skills directly.
        for skill in row.get("skill_data_array") or []:
            if not isinstance(skill, dict):
                continue
            try:
                skill_id = int(skill.get("skill_id") or 0)
            except (TypeError, ValueError):
                continue
            group_id = self.skill_group_by_id.get(skill_id)
            if group_id is not None:
                groups.add(group_id)
        return groups

    def native_sources(self, targets: Iterable[Any]) -> dict[int, dict[str, Any]]:
        target_groups = {
            unity_family(getattr(target, "name", "")): self.target_group_ids(target)
            for target in targets
            if str(getattr(target, "factor_type", "")) in {"white_skill", "scenario"}
        }
        result: dict[int, dict[str, Any]] = {}
        for row in self.owned_trainees:
            try:
                card_id = int(row.get("card_id") or 0)
            except (TypeError, ValueError):
                continue
            meta = self.card_meta.get(card_id)
            if not meta:
                continue
            groups = self._owned_card_skill_groups(row)
            skills = [name for name, wanted in target_groups.items() if wanted & groups]
            result[card_id] = {
                **meta,
                "talent_level": int(row.get("talent_level") or 0),
                "rarity": int(row.get("rarity") or 0),
                "requested_skill_families": skills,
            }
        return result

    def _support_quality(self, owned: dict[str, Any], meta: dict[str, Any]) -> float:
        extra = owned.get("extra_data") if isinstance(owned.get("extra_data"), dict) else {}
        try:
            level = int(extra.get("level") or 0)
            max_level = int(extra.get("max_level") or 0)
            lb = int(owned.get("limit_break_count") or 0)
            rarity = int(meta.get("rarity") or 0)
        except (TypeError, ValueError):
            return 0.0
        level_ratio = level / max(1.0, float(max_level or level or 1))
        return 100.0 * (
            0.45 * min(1.0, level_ratio)
            + 0.35 * min(1.0, lb / 4.0)
            + 0.20 * min(1.0, rarity / 3.0)
        )

    def support_sources(
        self,
        targets: Iterable[Any],
        *,
        trainee_chara_id: int = 0,
    ) -> list[dict[str, Any]]:
        target_list = list(targets)
        target_groups = {
            unity_family(getattr(target, "name", "")): self.target_group_ids(target)
            for target in target_list
            if str(getattr(target, "factor_type", "")) in {"white_skill", "scenario"}
        }
        result: list[dict[str, Any]] = []
        for owned in self.owned_supports:
            try:
                support_id = int(owned.get("support_card_id") or owned.get("card_id") or 0)
            except (TypeError, ValueError):
                continue
            meta = self.support_meta.get(support_id)
            if not meta:
                continue
            if trainee_chara_id and int(meta.get("chara_id") or 0) == trainee_chara_id:
                continue
            groups = self.support_hint_groups.get(support_id, set())
            skills = [name for name, wanted in target_groups.items() if wanted & groups]
            if not skills:
                continue
            extra = owned.get("extra_data") if isinstance(owned.get("extra_data"), dict) else {}
            result.append(
                {
                    **meta,
                    "level": int(extra.get("level") or 0),
                    "max_level": int(extra.get("max_level") or 0),
                    "limit_break_count": int(owned.get("limit_break_count") or 0),
                    "requested_skill_families": skills,
                    "quality_prior": round(self._support_quality(owned, meta), 3),
                }
            )
        result.sort(
            key=lambda row: (
                len(row["requested_skill_families"]),
                float(row["quality_prior"]),
                int(row.get("rarity") or 0),
            ),
            reverse=True,
        )
        return result

    def plan_for_result(
        self,
        *,
        result_row: dict[str, Any],
        targets: tuple[Any, ...],
        affinity_resolver: Any,
    ) -> dict[str, Any]:
        target = result_row.get("target") or {}
        target_card_id = int(target.get("card_id") or 0)
        target_chara_id = int(target.get("chara_id") or 0)
        native = self.native_sources(targets)
        target_native = native.get(target_card_id) or {}
        supports = self.support_sources(targets, trainee_chara_id=target_chara_id)
        priority_by_family = {
            unity_family(getattr(item, "name", "")): max(0.0, float(getattr(item, "priority", 0.0)))
            for item in targets
        }
        inherited = {
            unity_family(row.get("name")): float(row.get("probability") or 0.0)
            for row in result_row.get("spark_targets") or []
        }

        # Greedy skill-access deck: first value marginal requested-skill coverage,
        # then prefer cards the player has actually invested in. This is not a
        # replacement for a scenario-specific training simulator.
        chosen: list[dict[str, Any]] = []
        covered: set[str] = set()
        remaining = list(supports)
        while remaining and len(chosen) < 5:
            best = max(
                remaining,
                key=lambda row: (
                    sum(
                        priority_by_family.get(skill, 0.0)
                        for skill in row["requested_skill_families"]
                        if skill not in covered
                    ),
                    float(row["quality_prior"]),
                ),
            )
            marginal = {
                skill for skill in best["requested_skill_families"] if skill not in covered
            }
            if not marginal and len(chosen) >= 2:
                break
            chosen.append(best)
            covered.update(best["requested_skill_families"])
            remaining.remove(best)

        target_native_families = set(target_native.get("requested_skill_families") or [])
        family_rows: list[dict[str, Any]] = []
        for item in targets:
            family = unity_family(getattr(item, "name", ""))
            if not self.target_group_ids(item):
                continue
            support_rows = [
                row for row in supports if family in row["requested_skill_families"]
            ]
            family_rows.append(
                {
                    "name": str(getattr(item, "name", "")),
                    "family": family,
                    "priority": float(getattr(item, "priority", 0.0)),
                    "inherit_probability": round(inherited.get(family, 0.0), 8),
                    "target_native": family in target_native_families,
                    "owned_support_count": len(support_rows),
                    "best_owned_supports": support_rows[:3],
                }
            )

        # Seed-run recommendations identify owned Umas that can naturally learn
        # hard requested skills before the final target. Same skill group means a
        # gold form (e.g. Tail Nine) can secure the corresponding white family.
        seeds: list[dict[str, Any]] = []
        for card_id, source in native.items():
            if int(source.get("chara_id") or 0) == target_chara_id:
                continue
            families = set(source.get("requested_skill_families") or [])
            if not families:
                continue
            weighted = 0.0
            for family in families:
                probability = inherited.get(family, 0.0)
                support_count = next(
                    (
                        row["owned_support_count"]
                        for row in family_rows
                        if row["family"] == family
                    ),
                    0,
                )
                scarcity = 1.0 / (1.0 + support_count)
                weighted += priority_by_family.get(family, 0.0) * (1.0 - probability) * (1.0 + scarcity)
            affinity = int(
                affinity_resolver.pair(
                    int(source.get("chara_id") or 0), target_chara_id
                )
            ) if target_chara_id else 0
            score = weighted + 0.75 * affinity
            seeds.append(
                {
                    **source,
                    "affinity_to_target": affinity,
                    "route_score": round(score, 3),
                }
            )
        seeds.sort(
            key=lambda row: (
                float(row["route_score"]),
                len(row["requested_skill_families"]),
                int(row.get("talent_level") or 0),
            ),
            reverse=True,
        )

        route: list[dict[str, Any]] = []
        secured = set(target_native_families)
        for seed in seeds:
            useful = [
                family
                for family in seed["requested_skill_families"]
                if family not in secured
                and inherited.get(family, 0.0) < 0.65
            ]
            if not useful:
                continue
            route.append({**seed, "route_skill_families": useful})
            secured.update(useful)
            if len(route) >= 3:
                break

        return {
            "collection_available": bool(self.owned_trainees or self.owned_supports),
            "target_native_skill_families": sorted(target_native_families),
            "skill_sources": family_rows,
            "deck_candidates": chosen,
            "seed_candidates": seeds[:8],
            "preparation_route": route,
            "method_note": (
                "Deck candidates maximize requested-skill access using owned hint cards and "
                "current level/LB/rarity as a quality prior; they are not a full scenario-specific support meta simulation."
            ),
        }
