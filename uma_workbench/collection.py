"""Named collection facets shared by the roster and every card picker."""
from collections import defaultdict

from uma_workbench.planning import APTITUDES, catalog_for

SUPPORT_TYPES = {101: "Speed", 105: "Stamina", 102: "Power", 103: "Guts", 106: "Wit"}
SPARK_TYPES = {1: "Blue", 2: "Pink", 3: "Green", 4: "Skill", 5: "Race", 6: "Scenario"}


def collection_facets(master, kind, row):
    catalog = catalog_for(master)
    identity = int(row.get("support_card_id", row.get("card_id", 0)))
    if kind == "supports":
        base = master.supports.get(identity, {})
        skills = catalog.hint_skills(master, identity) | catalog.event_skills(identity)
        support_type = SUPPORT_TYPES.get(base.get("command_id"), "Group" if base.get("support_card_type") == 3 else "Pal")
    elif kind == "trainees":
        base = catalog.rarity_row(master, row)
        skills = catalog.base_skills(master, row)
        support_type = None
    else:
        base = row
        skills = catalog.lower_skills(int(item["skill_id"]) for item in row.get("skill_array", []))
        support_type = None
    own, family, labels = defaultdict(int), defaultdict(int), {}
    def add(factors, destination):
        for item in factors:
            factor_id = int(item.get("factor_id", 0))
            data = master.factors.get(factor_id, {})
            color = SPARK_TYPES.get(data.get("factor_type"), "Other")
            key = f"{color}:{data.get('factor_group_id', factor_id)}"
            stars = int(data.get("rarity", item.get("level", 0)))
            name = master.names.get((147, factor_id), "Unknown spark")
            labels[key] = f"{color} · {name}"
            destination[key] += stars
            destination["color:" + color] += stars
    add(row.get("factor_info_array", []), own)
    family.update(own)
    for parent in row.get("succession_chara_array", []):
        if parent.get("position_id") in (10, 20):
            add(parent.get("factor_info_array", []), family)
    return {"rarity": base.get("rarity", row.get("rarity")), "support_type": support_type,
        "level": master.support_level(row) if kind == "supports" else None,
        "limit_breaks": row.get("limit_break_count", 0), "locked": bool(row.get("is_locked")),
        "aptitudes": {key: base.get(key, 0) for key, _label, _group in APTITUDES},
        "skills": {identity: master.names.get((47, identity), "Unknown skill") for identity in skills},
        "sparks": dict(own), "family_sparks": dict(family), "spark_labels": labels,
        "stats": {key: row.get(key, 0) for key in ("speed", "stamina", "power", "guts", "wiz")}}


def matches_filters(row, filters):
    facets = row.get("facets", {})
    if filters.get("rarity") and facets.get("rarity") != filters["rarity"]:
        return False
    if filters.get("support_type") and facets.get("support_type") != filters["support_type"]:
        return False
    if facets.get("level", 0) is None and filters.get("level"):
        return False
    if (facets.get("level") or 0) < filters.get("level", 0) or facets.get("limit_breaks", 0) < filters.get("limit_breaks", 0):
        return False
    if filters.get("locked") and not facets.get("locked"):
        return False
    if any(facets.get("aptitudes", {}).get(key, 0) < value for key, value in filters.get("aptitudes", {}).items()):
        return False
    if any(facets.get("stats", {}).get(key, 0) < value for key, value in filters.get("stats", {}).items()):
        return False
    if filters.get("skill") and filters["skill"] not in facets.get("skills", {}):
        return False
    sparks = facets.get("family_sparks" if filters.get("family") else "sparks", {})
    return all(sparks.get(key, 0) >= stars for key, stars in filters.get("sparks", []) if key)
