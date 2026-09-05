"""Evaluation-scoped compiled curves; the canonical floating point order stays intact."""
from __future__ import annotations

from typing import Iterable
from uma_legacy_linker.solver_runtime import current_runtime


def interpolate(raw: float, ordered: list[tuple[float, float]]) -> float:
    if not ordered:
        return 0.0
    if raw <= ordered[0][0]:
        return ordered[0][1]
    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:]):
        if raw <= x1:
            if x1 == x0:
                return y1
            return y0 + (raw - x0) / (x1 - x0) * (y1 - y0)
    return ordered[-1][1]


def compiled_piecewise(raw: float, points: Iterable[Iterable[float]]) -> float:
    runtime = current_runtime()
    if runtime is None or not isinstance(points, (list, tuple)):
        return interpolate(raw, sorted((float(p[0]), float(p[1])) for p in points))
    # Strong identity guards, bounded even when callers create fallback curves.
    # Configuration is immutable for the duration of one solver scope.
    cache = runtime.caches.setdefault("curves", {})
    entry = cache.get(id(points))
    if entry is None or entry[0] is not points:
        ordered = sorted((float(p[0]), float(p[1])) for p in points)
        if len(cache) >= 128:
            del cache[next(iter(cache))]
        entry = cache[id(points)] = (points, ordered)
        runtime.stats["curves_compiled"] = runtime.stats.get("curves_compiled", 0) + 1
    return interpolate(raw, entry[1])
