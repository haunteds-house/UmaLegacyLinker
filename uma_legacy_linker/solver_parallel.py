"""Bounded, ordered pair batches in Windows-compatible spawn processes.

Each child receives one immutable job snapshot, then only pair indices. A private
pipe watches the owning backend: even if Qt terminates that backend abruptly,
EOF makes its solver children exit. No Qt, SQLite connections or closures cross
the process boundary. No global pool survives a search.
"""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from itertools import chain
import math
import multiprocessing as mp
from multiprocessing.connection import wait
import os
import threading
import time
import traceback

from uma_legacy_linker.solver_runtime import SolverRuntime, current_runtime, solver_scope


@dataclass
class AffinitySnapshot:
    memberships: dict
    relation_points: dict
    objectives: dict

    def pair(self, a, b):
        from uma_legacy_linker.parent_optimizer import AffinityResolver
        return AffinityResolver.pair(self, a, b)

    def triple(self, a, b, c):
        from uma_legacy_linker.parent_optimizer import AffinityResolver
        return AffinityResolver.triple(self, a, b, c)

    def objective_races(self, chara):
        return deepcopy(self.objectives[chara])


@dataclass
class WeightSnapshot:
    values: dict

    def __call__(self, key):
        # Fail loudly if an evaluator starts consuming a new source of skills.
        return self.values[key]


def _snapshot(context, left, right):
    from uma_legacy_linker.parent_optimizer import _factor_list, _lineage_members, slugify
    result = dict(context)
    resolver = context["resolver"]
    charas = {int(context["ace"].get("chara_id") or 0)}
    if "target_parent_chara" in context:
        charas.add(context["target_parent_chara"])
    result["resolver"] = AffinitySnapshot(
        resolver.memberships, resolver.relation_points,
        {c: resolver.objective_races(c) for c in charas},
    )
    keys = {}  # Preserve first occurrence order, including lookup diagnostics.
    extra = [context["contextual_opposing_parent"]] if context.get("contextual_opposing_parent") else []
    for veteran in chain(left, right, extra):
        for member, _, _ in _lineage_members(veteran):
            for factor in _factor_list(member, "white_skill"):
                keys[slugify(str(factor.get("name") or ""))] = None
            for factor in _factor_list(member, "white_race"):
                for key in context["race_skills"].get(str(factor.get("name") or ""), []):
                    keys[key] = None
    result["weight_lookup"] = WeightSnapshot({key: context["weight_lookup"](key) for key in keys})
    return result


def _exit_with_owner(owner):
    try:
        owner.recv_bytes()
    except (EOFError, OSError):
        pass
    # The owner never sends data; losing this pipe always ends the worker.
    os._exit(70)


def _evaluate(kind, context, left, right, i, j):
    if kind == "gp":
        from uma_legacy_linker.uma_moe import _evaluate_gp_pair
        return _evaluate_gp_pair(context, left[i], right[j], detailed=False)
    if kind == "online_parent":
        from uma_legacy_linker.uma_moe import _evaluate_online_parent_pair
        return _evaluate_online_parent_pair(
            context, left[i], right[j], detailed=False,
            local_branch=context["left_branches"][i], remote_branch=context["right_branches"][j],
        )
    from uma_legacy_linker.parent_optimizer import evaluate_parent_pair
    return evaluate_parent_pair(
        context["resolver"], context["ace"], left[i], right[j],
        surface=context["surface"], distance=context["distance"], style=context["style"],
        weight_lookup=context["weight_lookup"], race_skills=context["race_skills"], config=context["config"],
        parent_1_branch=context["left_branches"][i], parent_2_branch=context["right_branches"][j],
        g1_bonus_value=context["g1_bonus_value"], affinity_thresholds=context["pair_thresholds"],
        g1_objective_races=context["pair_objective_races"],
        include_details=False, include_g1_schedule=False,
    )


def _worker(connection, owner, kind, context, left, right):
    threading.Thread(target=_exit_with_owner, args=(owner,), daemon=True).start()
    runtime = SolverRuntime(True)
    try:
        with solver_scope(runtime):
            while True:
                task = connection.recv()
                if task is None:
                    return
                number, indices = task
                rows = []
                before = {key: runtime.stats.get(key, 0) for key in ("g1_solver_calls", "g1_estimator_calls")}
                for i, j in indices:
                    row = _evaluate(kind, context, left, right, i, j)
                    # Reattach original objects in the coordinator, not once per pair in IPC.
                    for key in ("_gp1", "_gp2", "_local_parent", "_remote_parent"):
                        row.pop(key, None)
                    rows.append(row)
                connection.send(("result", number, rows, {key: runtime.stats.get(key, 0) - value for key, value in before.items()}))
    except (EOFError, BrokenPipeError):
        return
    except BaseException as exc:
        connection.send(("error", type(exc).__name__, str(exc), traceback.format_exc()))
    finally:
        connection.close()


def parallel_requested():
    runtime = current_runtime()
    return runtime is not None and runtime.optimized and runtime.workers != 1


def parallel_pair_rows(kind, context, left, right, pairs, *, checkpoint, logger):
    """Return ordered rows, or None when this job should run in the caller.

    Explicit worker counts also apply to small pools. Auto=0 uses conservative
    thresholds to avoid process startup overhead on short searches.
    """
    runtime = current_runtime()
    if not parallel_requested():
        return None
    pairs = list(pairs)
    threshold = 200 if kind == "gp" else 2000
    requested = runtime.workers
    workers = min(requested or min(4, os.cpu_count() or 1), len(pairs))
    if requested == 0 and len(pairs) < threshold:
        workers = 1
    stats = {"requested": requested, "effective": max(1, workers), "pairs": len(pairs),
             "auto_threshold": threshold, "start_method": "spawn", "child_pids": []}
    runtime.stats.setdefault("parallel", {})[kind] = stats
    if workers < 2:
        return None
    checkpoint()
    started = time.perf_counter()
    snapshot = _snapshot(context, left, right)
    chunk_size = min(32 if kind == "gp" else 128, max(1, math.ceil(len(pairs) / (4 * workers))))
    chunks = [pairs[start:start + chunk_size] for start in range(0, len(pairs), chunk_size)]
    stats.update(chunk_size=chunk_size, chunks=len(chunks))
    spawn = mp.get_context("spawn")
    processes, connections, owners = [], [], []
    active, buffered, rows = {}, {}, []
    next_send = next_read = 0
    success = False
    try:
        for _ in range(workers):
            checkpoint()
            parent, child = spawn.Pipe()
            watch, owner = spawn.Pipe(duplex=False)
            process = spawn.Process(target=_worker, args=(child, watch, kind, snapshot, left, right),
                                    name="ULL-solver", daemon=True)
            connections.append(parent)
            owners.append(owner)
            try:
                process.start()
                processes.append(process)
                stats["child_pids"].append(process.pid)
            finally:
                child.close()
                watch.close()
        while next_read < len(chunks):
            checkpoint()
            for connection in connections:
                if connection not in active and next_send < len(chunks) and next_send - next_read < 2 * workers:
                    try:
                        connection.send((next_send, chunks[next_send]))
                    except (OSError, EOFError) as exc:
                        raise RuntimeError("Un processus solver s'est arrêté pendant l'envoi d'un lot.") from exc
                    active[connection] = next_send
                    next_send += 1
            ready = wait(list(active), timeout=.05)
            for connection in ready:
                try:
                    message = connection.recv()
                except (EOFError, OSError) as exc:
                    raise RuntimeError("Un processus solver s'est arrêté sans résultat.") from exc
                if message[0] == "error":
                    raise RuntimeError(f"Processus solver : {message[1]} : {message[2]}\n{message[3]}")
                _, number, values, g1_calls = message
                if number != active.pop(connection) or len(values) != len(chunks[number]):
                    raise RuntimeError("Lot solver incomplet ou reçu dans un ordre inattendu.")
                buffered[number] = values
                for key, count in g1_calls.items():
                    runtime.stats[key] = runtime.stats.get(key, 0) + count
            if any(p.exitcode is not None for p in processes):
                raise RuntimeError("Un processus solver s'est arrêté avant la fin du calcul.")
            while next_read in buffered:
                values = buffered.pop(next_read)
                for (i, j), row in zip(chunks[next_read], values):
                    if kind == "gp":
                        row.update(_gp1=left[i], _gp2=right[j])
                    elif kind == "online_parent":
                        row.update(_local_parent=left[i], _remote_parent=right[j])
                    rows.append(row)
                next_read += 1
                if next_read % 8 == 0 or next_read == len(chunks):
                    logger(f"Paires calculées : {len(rows)}/{len(pairs)}")
        success = True
        return rows
    finally:
        # Never rely on Executor internals or garbage collection to reap children.
        if success:
            for connection in connections:
                try:
                    connection.send(None)
                except (OSError, EOFError):
                    pass
        else:
            for process in processes:
                if process.is_alive():
                    process.terminate()
        deadline = time.monotonic() + 1.
        for process in processes:
            process.join(max(0., deadline - time.monotonic()))
        for process in processes:
            if process.is_alive():
                process.kill()
            process.join()
        stats.update(seconds_including_startup=time.perf_counter() - started,
                     exit_codes=[p.exitcode for p in processes], reaped=all(not p.is_alive() for p in processes))
        for connection in chain(connections, owners):
            connection.close()
        for process in processes:
            process.close()
