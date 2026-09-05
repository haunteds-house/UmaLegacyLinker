"""Spawn targets kept importable without pytest or Qt, including on Windows."""
import json
from pathlib import Path

from uma_legacy_linker import parent_optimizer as po
from uma_legacy_linker.solver_runtime import SolverRuntime, solver_scope


def pair_job(arguments):
    resolver = po.AffinityResolver(Path(arguments["master_path"]))
    members = json.loads(Path(arguments["linked_veterans_path"]).read_text())["veterans"]
    target = resolver.ace_details(arguments["ace_card_id"], "turf", "medium", "pace_chaser")
    config = po._read_json(po.resource_base_dir() / "default_parent_scoring.json")
    payload = po._read_json(Path(arguments["simulator_weights_path"]))
    lookup, _, _ = po._selected_weight_lookup(payload, None, {}, "turf", "medium", "pace_chaser", None, {}, .12, {}, {})
    kwargs = dict(surface="turf", distance="medium", style="pace_chaser", weight_lookup=lookup, race_skills={}, config=config)
    branches = [po.evaluate_parent_branch(resolver, target, member, **kwargs) for member in members]
    context = dict(kwargs, resolver=resolver, ace=target, g1_bonus_value=3,
                   pair_thresholds=config["affinity"]["parent_pair_thresholds"],
                   pair_objective_races=resolver.objective_races(target["chara_id"]),
                   left_branches=branches, right_branches=branches)
    pairs = [(i, j) for i in range(len(members)) for j in range(i + 1, len(members))]
    return resolver, context, members, pairs


def nested_search(arguments, connection, hold_owner=False):
    import sys
    runtime = SolverRuntime(True, workers=2)
    announced = False

    def checkpoint():
        nonlocal announced
        stats = runtime.stats.get("parallel", {}).get("local_parent", {})
        if len(stats.get("child_pids", [])) == 2 and not announced:
            announced = True
            connection.send(("children", stats["child_pids"]))
            if hold_owner:
                # Let the supervisor terminate this backend while children live.
                connection.recv()

    try:
        with solver_scope(runtime):
            result = po.optimize_parents(**arguments, checkpoint=checkpoint)
        connection.send(("done", runtime.stats, str(result.rankings_json_path),
                         [name for name in sys.modules if name.startswith(("PySide6", "ui_qt"))]))
    finally:
        connection.close()
