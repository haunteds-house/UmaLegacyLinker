"""Offline calculations based on the selected game data and entered balances."""
from __future__ import annotations

from collections import defaultdict
from math import ceil, isfinite
import re

from uma_workbench.planning import catalog_for

PERFORMANCE = ("Dance", "Passion", "Vocal", "Visual", "Composure")


def skill_budget(catalog, selected, *, learned=(), paid_prices=None, budget=0):
    """Include positive prerequisite steps once; never buy negative variants.

    A learned higher tier covers its lower tiers. Prices are incremental MDB
    prices, or the user-entered discounted in-game price for each step.
    """
    if not isfinite(float(budget)) or budget < 0:
        raise ValueError("Enter a nonnegative skill-point balance")
    paid_prices = paid_prices or {}
    learned = catalog.lower_skills(learned)
    needed = catalog.lower_skills(selected) - learned
    rows = []
    unknown = []
    for identity in sorted(needed, key=lambda sid: (catalog.skills.get(sid, {}).get("group_id", sid),
            catalog.skills.get(sid, {}).get("group_rate", 0), sid)):
        price = paid_prices.get(identity, catalog.costs.get(identity))
        if price is not None and (not isfinite(float(price)) or price < 0):
            raise ValueError("Skill prices must be nonnegative")
        if price is None:
            unknown.append(identity)
        rows.append({"skill_id": identity, "cost": price, "prerequisite": identity not in selected})
    total = sum(row["cost"] for row in rows if row["cost"] is not None)
    return {"rows": rows, "total": total, "unknown": unknown,
        "remaining": budget - total if not unknown else None,
        "missing": max(0, total - budget) if not unknown else None}


def awakening_costs(master, card_id, current, target):
    if not 1 <= int(current) <= int(target) <= 5:
        raise ValueError("Choose awakening levels from 1 to 5, with the target at or above the current level")
    catalog = catalog_for(master)
    group = master.cards.get(int(card_id), {}).get("talent_group_id")
    costs = defaultdict(int)
    levels = set()
    for row in catalog.upgrades:
        if row.get("talent_group_id") != group or not current < row["talent_level"] <= target:
            continue
        levels.add(row["talent_level"])
        for slot in range(1, 7):
            identity, amount = row.get(f"item_id_{slot}", 0), row.get(f"item_num_{slot}", 0)
            if identity and amount:
                costs[identity] += amount
    missing_levels = sorted(set(range(current + 1, target + 1)) - levels)
    return {"items": [{"item_id": identity, "name": catalog.texts.get((23, identity), "Material name unavailable"), "needed": amount}
        for identity, amount in sorted(costs.items())], "missing_levels": missing_levels}


def material_budget(items, balances, per_run):
    result = []
    for row in items:
        balance, income = float(balances.get(row["item_id"], 0)), float(per_run.get(row["item_id"], 0))
        if not all(isfinite(value) and value >= 0 for value in (balance, income)):
            raise ValueError("Enter nonnegative balances and earnings")
        missing = max(0, row["needed"] - balance)
        result.append({**row, "balance": balance, "missing": missing,
            "runs": 0 if missing == 0 else (ceil(missing / income) if income else None)})
    return result


def concert_songs(master):
    catalog = catalog_for(master)
    songs = []
    for row in catalog.songs:
        costs = [0] * 5
        for slot in range(1, 6):
            kind = row.get(f"perf_type_{slot}", 0)
            if 1 <= kind <= 5:
                costs[kind - 1] += row.get(f"perf_value_{slot}", 0)
        title_id = row.get("square_title_text_id")
        name = catalog.texts.get((209, title_id), "Song name unavailable")
        effect = re.sub(r"<[^>]+>", "", catalog.texts.get((207, row.get("square_content_text_id")), ""))
        songs.append({"id": row["id"], "name": name, "costs": costs, "effect": effect})
    return sorted(songs, key=lambda row: row["name"].casefold())


def concert_budget(songs, wanted, bought, balances):
    if len(balances) != 5 or any(not isfinite(float(value)) or value < 0 for value in balances):
        raise ValueError("Enter five nonnegative performance-point balances")
    wanted, bought = set(wanted), set(bought)
    costs = [sum(song["costs"][index] for song in songs if song["id"] in wanted - bought) for index in range(5)]
    return {"costs": costs, "remaining": [balance - cost for balance, cost in zip(balances, costs)],
        "missing": [max(0, cost - balance) for balance, cost in zip(balances, costs)],
        "songs_to_buy": sum(song["id"] in wanted - bought for song in songs)}
