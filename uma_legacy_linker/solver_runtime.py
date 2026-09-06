"""Search-local numerical caches and worker policy, shared by CLI and backend."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
import inspect
import os
from typing import Any, Callable, Iterator


@dataclass
class SolverRuntime:
    optimized: bool
    workers: int = 1
    checkpoint: Callable[[], None] | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    caches: dict[str, Any] = field(default_factory=dict)


_CURRENT: ContextVar[SolverRuntime | None] = ContextVar("solver_runtime", default=None)


def current_runtime() -> SolverRuntime | None:
    return _CURRENT.get()


def optimized_solver() -> bool:
    runtime = current_runtime()
    return runtime is not None and runtime.optimized


@contextmanager
def solver_scope(runtime: SolverRuntime) -> Iterator[SolverRuntime]:
    token = _CURRENT.set(runtime)
    try:
        yield runtime
    finally:
        _CURRENT.reset(token)


def configured_workers() -> int:
    value = os.environ.get("ULL_SOLVER_WORKERS", "auto").strip().lower()
    if value == "auto":
        return 0
    try:
        count = int(value)
    except ValueError:
        raise ValueError("ULL_SOLVER_WORKERS must be auto or a non-negative integer.") from None
    if count < 0:
        raise ValueError("ULL_SOLVER_WORKERS must be auto or a non-negative integer.")
    return count


def solver_search(function: Callable) -> Callable:
    """Create one optimized scope per public search, respecting an existing scope.

    Explicit scopes also let regression tests run the canonical path. Workers
    install their own sequential scope; a nested call never starts a new pool.
    """
    signature = inspect.signature(function)

    @wraps(function)
    def wrapped(*args, **kwargs):
        if current_runtime() is not None:
            return function(*args, **kwargs)
        arguments = signature.bind(*args, **kwargs).arguments
        runtime = SolverRuntime(True, workers=configured_workers(),
                                checkpoint=arguments.get("checkpoint"))
        with solver_scope(runtime):
            return function(*args, **kwargs)

    return wrapped


def configured_g1_ranking() -> str:
    """Explicit exact oracle remains available without disabling other caches."""
    mode = os.environ.get("ULL_G1_RANKING", "e2").strip().lower()
    if mode not in {"e2", "exact"}:
        raise ValueError("ULL_G1_RANKING must be e2 or exact.")
    return mode
