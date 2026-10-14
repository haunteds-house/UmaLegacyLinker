"""Qt-free contracts for side-by-side result comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from uma_legacy_linker.output_history import OutputProvenance
from uma_legacy_linker.veteran_identity import canonical_veteran_label


Getter = Callable[[dict[str, Any]], object]


@dataclass(frozen=True)
class ComparisonMetric:
    label: str
    getter: Getter
    digits: int = 2
    suffix: str = ""


@dataclass(frozen=True)
class ComparisonItem:
    key: str
    label: str
    row: dict[str, Any]


@dataclass(frozen=True)
class ComparisonDataset:
    title: str
    items: tuple[ComparisonItem, ...]
    profile: dict[str, Any] = field(default_factory=dict)
    mode: str = ""
    provenance: OutputProvenance | None = None

    def item(self, key: str) -> ComparisonItem | None:
        return next((item for item in self.items if item.key == key), None)


def _nested(*keys: str, scale: float = 1.0) -> Getter:
    def read(row: dict[str, Any]) -> object:
        value: object = row
        for key in keys:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value) * scale
        return value

    return read


SEARCH_METRICS = (
    ComparisonMetric('rank', _nested("_rank"), digits=0),
    ComparisonMetric("Score", _nested("score")),
    ComparisonMetric(
        "P(S)",
        _nested("distance_s_summary", "probability_reach_s", scale=100.0),
        suffix="%",
    ),
    ComparisonMetric('Affinity', _nested("affinity", "total")),
    ComparisonMetric('Blue Sparks', _nested("components", "blue")),
    ComparisonMetric('Pink Sparks', _nested("components", "pink")),
    ComparisonMetric("Whites", _nested("components", "white_skill")),
    ComparisonMetric("G1", _nested("components", "race")),
    ComparisonMetric("Unique", _nested("components", "unique")),
)

TRANSFER_METRICS = (
    ComparisonMetric("Verdict", _nested("status")),
    ComparisonMetric('Evaluation score', _nested("rank_score"), digits=0),
    ComparisonMetric('Best parent', _nested("best_parent_score")),
    ComparisonMetric('Parent rank', _nested("best_parent_percentile"), suffix="%"),
    ComparisonMetric('Best GP', _nested("best_grandparent_score")),
    ComparisonMetric('GP rank', _nested("best_grandparent_percentile"), suffix="%"),
    ComparisonMetric(
        'Competitive parent contexts',
        _nested("parent_evidence", "competitive_context_count"),
        digits=0,
    ),
    ComparisonMetric(
        'Competitive GP contexts',
        _nested("grandparent_evidence", "competitive_context_count"),
        digits=0,
    ),
    ComparisonMetric('Speed', _nested("stats", "speed"), digits=0),
    ComparisonMetric('Stamina', _nested("stats", "stamina"), digits=0),
    ComparisonMetric('Power', _nested("stats", "power"), digits=0),
    ComparisonMetric('Guts', _nested("stats", "guts"), digits=0),
    ComparisonMetric('Wit', _nested("stats", "wiz"), digits=0),
)


def format_metric_value(value: object, metric: ComparisonMetric) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        rendered = f"{float(value):.{metric.digits}f}"
        return rendered + metric.suffix
    return str(value)


def format_metric_delta(
    left: object,
    right: object,
    metric: ComparisonMetric,
) -> str:
    if (
        not isinstance(left, (int, float))
        or isinstance(left, bool)
        or not isinstance(right, (int, float))
        or isinstance(right, bool)
    ):
        return "—"
    delta = float(right) - float(left)
    rendered = f"{delta:+.{metric.digits}f}"
    return rendered + metric.suffix


def ranked_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        copy = dict(row)
        copy.setdefault("_rank", index)
        ranked.append(copy)
    return ranked


def search_payload_rows(family: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    key = {
        "pairs": "top_parent_pairs",
        "branches": "top_parent_candidates",
        "future": "top_future_grandparents",
        "online_parent": "results",
        "online_gp": "results",
    }.get(family)
    rows = payload.get(key) if key else None
    return ranked_rows(row for row in (rows or []) if isinstance(row, dict))


def _stable_technical_key(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    online = value.get("online") if isinstance(value.get("online"), dict) else {}
    for candidate in (
        value.get("trained_chara_id"),
        value.get("id"),
        online.get("friend_code"),
    ):
        if candidate not in {None, ""}:
            return str(candidate)
    return None


def _unstable_key(family: str, label: str) -> str:
    """Keep a row selectable without treating its display label as identity."""
    return f"unstable:{family}:{label.casefold()}"


def _search_item_identity(family: str, row: dict[str, Any]) -> tuple[str, str]:
    if family == "pairs":
        parents = (row.get("parent_1"), row.get("parent_2"))
        labels = [canonical_veteran_label(item) for item in parents]
        label = " × ".join(labels)
        keys = [_stable_technical_key(item) for item in parents]
        if any(key is None for key in keys):
            return _unstable_key(family, label), label
        return "pair:" + "|".join(sorted(str(key) for key in keys)), label
    if family == "branches":
        label = canonical_veteran_label(row)
        key = _stable_technical_key(row)
        return ("branch:" + key if key else _unstable_key(family, label)), label
    if family == "future":
        label = canonical_veteran_label(row)
        key = _stable_technical_key(row)
        return ("future:" + key if key else _unstable_key(family, label)), label
    fixed_key = "fixed_parent" if family == "online_parent" else "fixed_grandparent"
    fixed = row.get(fixed_key)
    candidate = row.get("candidate")
    label = f"{canonical_veteran_label(fixed)} × {canonical_veteran_label(candidate)}"
    fixed_id = _stable_technical_key(fixed)
    candidate_id = _stable_technical_key(candidate)
    key = (
        f"{family}:{fixed_id}|{candidate_id}"
        if fixed_id and candidate_id
        else _unstable_key(family, label)
    )
    return key, label


def search_comparison_dataset(
    family: str,
    rows: Iterable[dict[str, Any]],
    *,
    title: str,
    profile: dict[str, Any] | None = None,
    provenance: OutputProvenance | None = None,
) -> ComparisonDataset:
    items: list[ComparisonItem] = []
    occurrences: dict[str, int] = {}
    for row in ranked_rows(rows):
        key, label = _search_item_identity(family, row)
        occurrence = occurrences.get(key, 0) + 1
        occurrences[key] = occurrence
        unique_key = key if occurrence == 1 else f"{key}#{occurrence}"
        rank = row.get("_rank")
        display = f"#{rank} · {label}" if rank is not None else label
        items.append(ComparisonItem(unique_key, display, row))
    mode = "parent" if family == "online_parent" else "grandparent"
    return ComparisonDataset(
        title=title,
        items=tuple(items),
        profile=dict(profile or {}),
        mode=mode,
        provenance=provenance,
    )


def transfer_comparison_dataset(
    records: Iterable[dict[str, Any]],
    *,
    title: str,
    provenance: OutputProvenance | None = None,
) -> ComparisonDataset:
    items: list[ComparisonItem] = []
    occurrences: dict[str, int] = {}
    for record in records:
        row = dict(record)
        label = canonical_veteran_label(row)
        technical_id = _stable_technical_key(row)
        key = (
            "trained:" + technical_id
            if technical_id
            else _unstable_key("transfer", label)
        )
        occurrence = occurrences.get(key, 0) + 1
        occurrences[key] = occurrence
        unique_key = key if occurrence == 1 else f"{key}#{occurrence}"
        items.append(
            ComparisonItem(unique_key, label, row)
        )
    return ComparisonDataset(title, tuple(items), provenance=provenance)


def matching_index(
    dataset: ComparisonDataset,
    key: str,
    *,
    fallback: int = 0,
) -> int:
    for index, item in enumerate(dataset.items):
        if item.key == key:
            return index
    return fallback if dataset.items else -1


def intersect_datasets(
    left: ComparisonDataset,
    right: ComparisonDataset,
) -> tuple[ComparisonDataset, ComparisonDataset]:
    """Keep only stable identities present in both executions."""
    common = {
        item.key
        for item in left.items
        if not item.key.startswith("unstable:")
    } & {
        item.key
        for item in right.items
        if not item.key.startswith("unstable:")
    }
    return (
        ComparisonDataset(
            left.title,
            tuple(item for item in left.items if item.key in common),
            profile=left.profile,
            mode=left.mode,
            provenance=left.provenance,
        ),
        ComparisonDataset(
            right.title,
            tuple(item for item in right.items if item.key in common),
            profile=right.profile,
            mode=right.mode,
            provenance=right.provenance,
        ),
    )
