"""Collection constraints shared by the training-goal editor and importers."""
from __future__ import annotations


def validate_training_goal(payload, store, master):
    card_id = int(payload["card_id"])
    if card_id not in {int(row["card_id"]) for row in store.entities("trainees")}:
        raise ValueError("The target trainee is not in your imported collection")
    if payload.get("role") not in {"TT", "CM", "Parent", "Grandparent"}:
        raise ValueError("Choose a supported training role")
    stats = payload.get("stats", {})
    if stats and (set(stats) != {"speed", "stamina", "power", "guts", "wiz"} or min(stats.values()) < 0):
        raise ValueError("Use five nonnegative stat targets, or leave them blank")
    deck = payload.get("deck_ids", [])
    if len(deck) > 6 or len(set(deck)) != len(deck):
        raise ValueError("Enter up to six distinct support IDs")
    owned = {int(row["support_card_id"]) for row in store.entities("supports")}
    if sum(identity not in owned for identity in deck) > 1:
        raise ValueError("A deck may use at most one borrowed support")
    target = master.character_id(card_id)
    characters = [master.supports[identity]["chara_id"] for identity in deck if identity in master.supports]
    if target in characters or len(characters) != len(set(characters)):
        raise ValueError("Support characters must be distinct and different from the target trainee")
    parents = payload.get("parent_ids", [])
    veterans = {int(row["trained_chara_id"]): row for row in store.entities("veterans")}
    if len(parents) > 2 or any(identity not in veterans for identity in parents):
        raise ValueError("Choose up to two parent veterans from your collection")
    characters = [master.character_id(veterans[identity]["card_id"]) for identity in parents]
    if target in characters or len(characters) != len(set(characters)):
        raise ValueError("Direct parents must be distinct characters and different from the target trainee")
    if int(payload.get("max_attempts", 0)) < 1:
        raise ValueError("Maximum attempts must be positive")
    if payload.get("distance") is not None and payload["distance"] <= 0:
        raise ValueError("Distance must be positive")
    if not payload.get("stop_condition", "").strip():
        raise ValueError("Describe the result that lets you stop or move to the next stage")
