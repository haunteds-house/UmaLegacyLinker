"""Collection constraints shared by the training-goal editor and importers."""
from __future__ import annotations


def validate_training_goal(payload, store, master):
    from uma_workbench.planning import APTITUDES
    from uma_workbench.training import options_for
    options_for(payload)
    card_id = int(payload["card_id"]) if payload.get("card_id") is not None else None
    if card_id is not None and card_id not in {int(row["card_id"]) for row in store.entities("trainees")}:
        raise ValueError("The target trainee is not in your imported collection")
    if payload.get("role") not in {"TT", "CM", "Parent", "Grandparent"}:
        raise ValueError("Choose a supported training role")
    stats = payload.get("stats", {})
    if stats and (set(stats) != {"speed", "stamina", "power", "guts", "wiz"} or min(stats.values()) < 0):
        raise ValueError("Use five nonnegative stat targets, or leave them blank")
    columns = {row[0] for row in APTITUDES}
    if any(key not in columns or not isinstance(value, int) or value not in range(9)
            for key, value in payload.get("aptitudes", {}).items()):
        raise ValueError("Choose aptitude targets between G and S")
    deck = payload.get("deck_ids", [])
    if len(deck) > 6 or len(set(deck)) != len(deck):
        raise ValueError("Choose up to six different support cards")
    owned = {int(row["support_card_id"]) for row in store.entities("supports")}
    if sum(identity not in owned for identity in deck) > 1:
        raise ValueError("A deck may use at most one borrowed support")
    target = master.character_id(card_id) if card_id is not None else None
    characters = [master.supports[identity]["chara_id"] for identity in deck if identity in master.supports]
    if (target is not None and target in characters) or len(characters) != len(set(characters)):
        raise ValueError("Support characters must be distinct and different from the target trainee")
    parents = payload.get("parent_ids", [])
    veterans = {int(row["trained_chara_id"]): row for row in store.entities("veterans")}
    if len(parents) > 2 or any(identity not in veterans for identity in parents):
        raise ValueError("Choose up to two parent veterans from your collection")
    from uma_legacy_linker.legacy_linker import is_borrowed_veteran
    if any(is_borrowed_veteran(veterans[identity]) for identity in parents):
        raise ValueError("A borrowed veteran cannot be used as one of your owned parents")
    characters = [master.character_id(veterans[identity]["card_id"]) for identity in parents]
    if (target is not None and target in characters) or len(characters) != len(set(characters)):
        raise ValueError("Direct parents must be distinct characters and different from the target trainee")
    if int(payload.get("max_attempts", 0)) < 1:
        raise ValueError("Maximum attempts must be positive")
    if payload.get("distance") is not None and payload["distance"] <= 0:
        raise ValueError("Distance must be positive")
    if payload.get("distance"):
        from uma_workbench.planning import distance_group
        group = distance_group(payload)
        if payload.get("distance_type") not in (None, "Any distance", group):
            raise ValueError(f"The exact distance belongs to {group}. Change the distance group or clear the exact distance.")
    if not payload.get("stop_condition", "").strip():
        raise ValueError("Describe the result that lets you stop or move to the next stage")
