"""Small data adapter for the live Uma.guide roster viewer, without account data."""

ROSTER_URL = "https://uma.guide/roster-viewer/"
VETERAN_FIELDS = frozenset((
    "trained_chara_id", "card_id", "rarity", "rank_score", "rank", "speed", "stamina",
    "power", "guts", "wiz", "skill_array", "factor_info_array", "succession_chara_array",
    "win_saddle_id_array", "win_race_id_array", "race_result_array", "support_card_list",
    "scenario_id", "create_time", "is_locked", "proper_ground_turf", "proper_ground_dirt",
    "proper_distance_short", "proper_distance_mile", "proper_distance_middle", "proper_distance_long",
    "proper_running_style_nige", "proper_running_style_senko", "proper_running_style_sashi",
    "proper_running_style_oikomi", "position_id", "chara_id", "factor_id", "level",
    "skill_id", "saddle_id", "race_id", "talent_level", "factor_extend_array",
    "succession_trained_chara_id_1", "succession_trained_chara_id_2", "support_card_id", "exp", "limit_break_count",
))


def roster_document(veterans):
    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if key in VETERAN_FIELDS}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    from uma_legacy_linker.legacy_linker import is_borrowed_veteran
    return {"trained_chara_array": [clean(row) for row in veterans if not is_borrowed_veteran(row)]}


def selection_for_plan(selection, store):
    """Only map visible selections to actual owned records; never guess a copy."""
    owned = {int(row["card_id"]) for row in store.entities("trainees")}
    try:
        card_id = int(selection.get("target"))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Choose a target in the viewer's Lineage Planner first.") from None
    if card_id not in owned:
        raise ValueError("That target is not in your imported trainees. Choose an owned trainee, or use New plan to compare your collection.")
    veterans = store.entities("veterans")
    candidates, parents = [], []
    from uma_legacy_linker.legacy_linker import is_borrowed_veteran
    for item in selection.get("parents", [])[:2]:
        identity = item.get("card_id") if isinstance(item, dict) else None
        rows = [row for row in veterans if row.get("card_id") == identity and not is_borrowed_veteran(row)]
        # Filled cards with placeholder/borrowed markers are not owned lineages.
        if item.get("borrowed") or item.get("placeholder"):
            rows = []
        ids = [int(row["trained_chara_id"]) for row in rows]
        candidates.append(ids)
        parents.append(ids[0] if len(ids) == 1 else None)
    return {"card_id": card_id, "lock_trainee": True, "viewer_parent_ids": parents,
        "viewer_parent_candidates": candidates}
