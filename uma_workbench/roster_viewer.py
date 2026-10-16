"""Local roster and lineage previews. No website, scripts or account uploads."""
from collections import Counter
from contextlib import closing
import sqlite3

from uma_legacy_linker.legacy_linker import MasterResolver, LinkerError, is_borrowed_veteran
from uma_legacy_linker.parent_optimizer import (
    AffinityResolver, OptimizerError, _branch_affinity, _initial_aptitude_rank,
)
from uma_workbench.collection import collection_facets
from uma_workbench.planning import APTITUDES, _branch_evidence, catalog_for


def immediate_ancestors(veteran):
    """The two snapshots that become grandparents when this veteran is a parent."""
    by_position = {row.get("position_id"): row for row in veteran.get("succession_chara_array", [])}
    return [by_position.get(10), by_position.get(20)]


def owned_veterans(store):
    return [row for row in store.entities("veterans") if not is_borrowed_veteran(row)]


def selection_for_plan(selection, store, master):
    """Resolve exact veteran copies and enforce character-level parent rules."""
    target = selection.get("target")
    target = int(target) if target is not None else None
    trainees = {int(row["card_id"]): row for row in store.entities("trainees")}
    if target is not None and target not in trainees:
        raise ValueError("Choose a trainee from your imported collection.")
    identities = [int(identity) for identity in selection.get("parent_ids", []) if identity is not None]
    if len(identities) > 2 or len(set(identities)) != len(identities):
        raise ValueError("Choose two different parent veterans.")
    veterans = {int(row["trained_chara_id"]): row for row in owned_veterans(store)}
    if any(identity not in veterans for identity in identities):
        raise ValueError("Choose parent veterans from your own imported collection.")
    characters = [master.character_id(veterans[identity]["card_id"]) for identity in identities]
    if len(set(characters)) != len(characters):
        raise ValueError("The parents must be different characters, including across outfits.")
    if target is not None and master.character_id(target) in characters:
        raise ValueError("A trainee cannot use the same character as a parent, including another outfit.")
    return {"card_id": target, "lock_trainee": target is not None, "parent_ids": identities}


def _resolvers(master):
    if not master.path:
        return None
    key = (str(master.path), master.sha256)
    cached = getattr(master, "_roster_resolvers", None)
    if cached is None or cached[0] != key:
        try:
            # These previews only need the in-memory relationship and saddle maps.
            with closing(MasterResolver(master.path)) as races:
                with closing(AffinityResolver(master.path)) as affinity:
                    cached = (key, races, affinity)
        except (sqlite3.Error, LinkerError, OptimizerError):
            cached = (key, None, None)
        master._roster_resolvers = cached
    return cached[1:]


def affinity_preview(master, trainee, parents):
    if not trainee or not parents:
        return None
    resolved = _resolvers(master)
    if not resolved or not all(resolved):
        return None
    races, resolver = resolved
    def member(row):
        return {"chara_id": master.character_id(row["card_id"]),
            "g1_wins": races.resolve_g1_saddles(row.get("win_saddle_id_array"))} if row else None
    branches, enriched = [], []
    known_races, complete = True, len(parents) == 2
    for parent in parents:
        grandparents = immediate_ancestors(parent)
        complete &= all(row is not None for row in grandparents)
        known_races &= all(row is not None and "win_saddle_id_array" in row for row in [parent, *grandparents])
        row = member(parent)
        row["when_used_as_parent"] = {f"grandparent_{i + 1}": member(gp) for i, gp in enumerate(grandparents)}
        enriched.append(row)
        branches.append(_branch_affinity(resolver, master.character_id(trainee["card_id"]), row, 3))
    pair_base, pair_g1 = 0, 0
    if len(enriched) == 2:
        pair_base = resolver.pair(enriched[0]["chara_id"], enriched[1]["chara_id"])
        pair_g1 = 3 * len(set(enriched[0]["g1_wins"]["names"]) & set(enriched[1]["g1_wins"]["names"]))
    base = sum(row["base"] for row in branches) + pair_base
    bonus = sum(row["g1_bonus"] for row in branches) + pair_g1
    return {"base": base, "g1_bonus": bonus if known_races else None,
        "total": base + bonus if known_races else None, "complete": bool(complete)}


def lineage_preview(master, trainee, parents):
    """Six-member spark totals and guaranteed starting aptitude changes."""
    catalog = catalog_for(master)
    sparks, labels, red, skills = Counter(), {}, Counter(), set()
    for parent in parents:
        facets = collection_facets(master, "veterans", parent)
        sparks.update({key: value for key, value in facets["family_sparks"].items() if not key.startswith("color:")})
        labels.update(facets["spark_labels"])
        branch_red, branch_skills = _branch_evidence(master, catalog, parent)
        red.update(branch_red)
        skills.update(branch_skills)
    base = catalog.rarity_row(master, trainee) if trainee else {}
    aptitudes = [{"label": label, "base": base.get(key), "stars": red.get(group, 0),
        "initial": _initial_aptitude_rank(base[key], red.get(group, 0)) if base.get(key) else None}
        for key, label, group in APTITUDES]
    return {"sparks": dict(sparks), "spark_labels": labels, "aptitudes": aptitudes,
        "skills": sorted(skills), "affinity": affinity_preview(master, trainee, parents)}
