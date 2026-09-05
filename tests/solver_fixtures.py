from pathlib import Path
import json
from tests.test_local_gp_pairs import _build_fake_master, _complete_veteran, _factor

def real_file_fixture(root: Path, count: int = 6) -> dict:
    """A real SQLite resolver and files, usable unchanged by spawned workers."""
    ids = list(range(3, count + 3))
    master = root / "master.mdb"
    _build_fake_master(master, sorted({1, 2, *ids, *(i + 50 for i in ids), *(i + 60 for i in ids)}), 100)
    vets = [_complete_veteran(i, f"Veteran {i}", factors=[
        _factor("blue_stat", "Speed", i % 3 + 1),
        _factor("red_aptitude", "Medium", i % 3 + 1),
        _factor("white_skill", "Skill A", i % 3 + 1),
        _factor("white_skill", "Skill B", 2),
        _factor("white_race", "Race Spark", 2),
        _factor("unique", "Unique", 3),
    ], g1=["Shared", f"Race {i % 2}"]) for i in ids]
    for v in vets:
        v["g1_wins"]["details"] = [
            {"name": name, "schedule_slots": [{"year": 2, "month": j + 4, "half": 1}],
             "surface": "turf", "distance_type": "medium"}
            for j, name in enumerate(v["g1_wins"]["names"])]
    files = {"linked.json": {"veterans": vets},
             "weights.json": {"skills": {k: {"weight_matrix": {"turf": {"medium": {"pace_chaser": {"weight": w}}}}} for k, w in [("skill_a", 2.5), ("skill_b", 0.0)]}},
             "races.json": {"race_factors": []}, "skills.json": {"skills": []}}
    for name, payload in files.items():
        (root / name).write_text(json.dumps(payload), encoding="utf-8")
    return dict(master_path=master, linked_veterans_path=root / "linked.json",
                simulator_weights_path=root / "weights.json", race_factor_catalog_path=root / "races.json",
                skill_catalog_path=root / "skills.json", output_dir=root / "out", ace_card_id=100,
                surface="turf", distance="medium", style="pace_chaser", search_kind="pairs", top_n=2)
