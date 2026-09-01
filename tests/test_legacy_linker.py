from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from uma_legacy_linker.legacy_linker import (
    LINK_CACHE_SCHEMA_VERSION,
    LinkerError,
    build_lineage_summary,
    factor_sort_key,
    grouped_factors,
    link_cache_freshness,
    link_veterans,
    normalize_json_root,
    resolve_parent_snapshot,
    sha256_file,
)


def factor(
    factor_id: int,
    name: str,
    factor_type: str,
    stars: int | None,
) -> dict[str, object]:
    return {
        "factor_id": factor_id,
        "name": name,
        "type": factor_type,
        "stars": stars,
        "stars_text": "★" * int(stars or 0),
    }


def lineage_member(
    name: str,
    factors: list[dict[str, object]],
    g1_names: list[str],
) -> dict[str, object]:
    return {
        "uma_name": name,
        "factors": grouped_factors(factors),
        "g1_wins": {
            "count": len(g1_names),
            "names": g1_names,
            "details": [],
        },
    }


class NormalizationContractTests(unittest.TestCase):
    def test_recognized_root_shapes_return_the_veteran_list(self) -> None:
        veterans = [{"trained_chara_id": 1}, {"trained_chara_id": 2}]
        for payload in (
            veterans,
            {"trained_chara_array": veterans},
            {"veterans": veterans},
            {"data": veterans},
        ):
            with self.subTest(payload_type=type(payload).__name__):
                self.assertEqual(normalize_json_root(payload), veterans)

    def test_empty_root_list_is_valid(self) -> None:
        self.assertEqual(normalize_json_root([]), [])

    def test_invalid_roots_raise_clear_linker_errors(self) -> None:
        cases = (
            (None, "liste ou un objet"),
            (42, "liste ou un objet"),
            ("veterans", "liste ou un objet"),
            ({}, "liste de vétérans reconnue"),
            ({"veterans": {}}, "liste de vétérans reconnue"),
        )
        for payload, message in cases:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(LinkerError, message):
                    normalize_json_root(payload)

    def test_non_object_veteran_reports_its_index(self) -> None:
        with self.assertRaisesRegex(LinkerError, r"vétéran #1 invalide"):
            normalize_json_root([{"trained_chara_id": 1}, None])


class FactorContractTests(unittest.TestCase):
    def test_grouped_factors_preserves_all_and_sorts_type_buckets(self) -> None:
        factors = [
            factor(4, "White", "white_skill", 1),
            factor(1, "Speed", "blue_stat", 3),
            factor(2, "Power", "blue_stat", 2),
        ]

        grouped = grouped_factors(factors)

        self.assertIs(grouped["all"], factors)
        self.assertEqual(list(grouped["by_type"]), ["blue_stat", "white_skill"])
        self.assertEqual(
            [item["name"] for item in grouped["by_type"]["blue_stat"]],
            ["Speed", "Power"],
        )

    def test_factor_sort_key_orders_domain_types_then_name_and_id(self) -> None:
        factors = [
            factor(9, "Unknown", "future_type", 1),
            factor(6, "White B", "white_skill", 1),
            factor(5, "White A", "white_skill", 1),
            factor(3, "Scenario", "scenario", 1),
            factor(2, "Turf", "red_aptitude", 1),
            factor(1, "Speed", "blue_stat", 1),
        ]

        ordered = sorted(factors, key=factor_sort_key)

        self.assertEqual(
            [item["factor_id"] for item in ordered],
            [1, 2, 3, 5, 6, 9],
        )

    def test_factor_sort_key_requires_resolved_factor_shape(self) -> None:
        for incomplete in ({}, {"type": "blue_stat"}, {"type": "blue_stat", "name": "Speed"}):
            with self.subTest(incomplete=incomplete):
                with self.assertRaises(KeyError):
                    factor_sort_key(incomplete)


class ParentSnapshotContractTests(unittest.TestCase):
    class Resolver:
        cards = {
            100: {
                "card_id": 100,
                "chara_id": 10,
                "uma_name": "Known Uma",
                "card_name": "Known Costume",
                "costume_name": "Known",
            }
        }

        def resolve_card(self, card_id: int) -> dict[str, object]:
            return dict(
                self.cards.get(
                    card_id,
                    {
                        "card_id": card_id,
                        "chara_id": None,
                        "uma_name": f"Unknown costume {card_id}",
                        "card_name": f"Unknown costume {card_id}",
                        "costume_name": "",
                    },
                )
            )

        def resolve_factors(
            self, raw: object, unresolved: set[int]
        ) -> dict[str, object]:
            values = []
            for item in raw if isinstance(raw, list) else []:
                factor_id = item.get("factor_id")
                if factor_id == 999:
                    unresolved.add(999)
                values.append(factor(int(factor_id), f"Factor {factor_id}", "other", 1))
            return grouped_factors(values)

        def resolve_g1_saddles(self, raw: object) -> dict[str, object]:
            names = [
                f"G1 {value}"
                for value in (raw if isinstance(raw, list) else [])
            ]
            return {"count": len(names), "names": names, "details": []}

    def test_none_or_invalid_snapshot_is_absent(self) -> None:
        resolver = self.Resolver()
        args = (resolver, None, None, set(), set(), set())
        self.assertIsNone(resolve_parent_snapshot(*args))
        self.assertIsNone(
            resolve_parent_snapshot(resolver, {}, None, set(), set(), set())
        )

    def test_snapshot_tracks_origin_presence_and_unresolved_ids(self) -> None:
        resolver = self.Resolver()
        unresolved_factors: set[int] = set()
        unresolved_cards: set[int] = set()
        snapshot = {
            "card_id": 404,
            "owner_viewer_id": 12345,
            "factor_info_array": [{"factor_id": 999}],
            "win_saddle_id_array": [7],
        }

        parent = resolve_parent_snapshot(
            resolver,
            snapshot,
            77,
            {77},
            unresolved_factors,
            unresolved_cards,
        )

        assert parent is not None
        self.assertEqual(parent["local_trained_chara_id"], 77)
        self.assertTrue(parent["present_in_export"])
        self.assertTrue(parent["borrowed_or_external"])
        self.assertEqual(parent["card_name"], "Unknown costume 404")
        self.assertEqual(parent["g1_wins"]["names"], ["G1 7"])
        self.assertEqual(unresolved_factors, {999})
        self.assertEqual(unresolved_cards, {404})

    def test_non_integer_local_id_is_not_considered_present(self) -> None:
        parent = resolve_parent_snapshot(
            self.Resolver(),
            {"card_id": 100},
            "77",
            {77},
            set(),
            set(),
        )

        assert parent is not None
        self.assertIsNone(parent["local_trained_chara_id"])
        self.assertFalse(parent["present_in_export"])


class LineageSummaryContractTests(unittest.TestCase):
    def test_summary_aggregates_sources_stars_and_repeated_g1(self) -> None:
        trainee = lineage_member(
            "Trainee",
            [factor(1, "Speed", "blue_stat", 3), factor(5, "Skill B", "white_skill", 1)],
            ["Shared G1", "Trainee G1"],
        )
        parent_1 = lineage_member(
            "Parent One",
            [factor(2, "Power", "blue_stat", 2), factor(4, "Skill A", "white_skill", 2)],
            ["Shared G1", "Parent G1"],
        )

        summary = build_lineage_summary(trainee, parent_1, None)

        self.assertEqual(summary["members_present"], 2)
        self.assertEqual(
            summary["total_stars_by_type"],
            {"blue_stat": 5, "white_skill": 3},
        )
        self.assertEqual(
            [item["name"] for item in summary["factors_by_type"]["white_skill"]],
            ["Skill A", "Skill B"],
        )
        self.assertEqual(
            [item["source"] for item in summary["factors_by_type"]["white_skill"]],
            ["grandparent_1", "parent"],
        )
        self.assertEqual(summary["g1_union"]["count"], 3)
        self.assertEqual(
            summary["g1_union"]["names"],
            ["Parent G1", "Shared G1", "Trainee G1"],
        )
        self.assertEqual(
            summary["g1_repeated_in_lineage"],
            {"Shared G1": ["parent", "grandparent_1"]},
        )


class LinkVeteransIntegrationTests(unittest.TestCase):
    class FakeResolver:
        last_instance: "LinkVeteransIntegrationTests.FakeResolver | None" = None
        created_count = 0

        cards = {
            100: {
                "card_id": 100,
                "chara_id": 10,
                "uma_name": "Main Uma",
                "card_name": "Main Costume",
                "costume_name": "Main",
            },
            200: {
                "card_id": 200,
                "chara_id": 20,
                "uma_name": "Local Parent",
                "card_name": "Local Parent Costume",
                "costume_name": "Local",
            },
        }
        factor_catalog = {
            1: factor(1, "Speed", "blue_stat", 3),
            2: factor(2, "Turf", "red_aptitude", 2),
            3: factor(3, "Useful Skill", "white_skill", 1),
        }
        saddle_names = {
            10: "Shared G1",
            20: "Own G1",
            30: "External G1",
        }

        def __init__(self, master_path: Path):
            self.master_path = master_path
            self.closed = False
            type(self).last_instance = self
            type(self).created_count += 1

        def close(self) -> None:
            self.closed = True

        def resolve_card(self, card_id: int) -> dict[str, object]:
            return dict(
                self.cards.get(
                    card_id,
                    {
                        "card_id": card_id,
                        "chara_id": None,
                        "uma_name": f"Unknown costume {card_id}",
                        "card_name": f"Unknown costume {card_id}",
                        "costume_name": "",
                    },
                )
            )

        def resolve_factors(
            self, raw: object, unresolved: set[int]
        ) -> dict[str, object]:
            values: list[dict[str, object]] = []
            for item in raw if isinstance(raw, list) else []:
                factor_id = item.get("factor_id")
                resolved = self.factor_catalog.get(factor_id)
                if resolved is None:
                    unresolved.add(int(factor_id))
                    resolved = factor(
                        int(factor_id), f"Unknown factor {factor_id}", "other", None
                    )
                values.append(dict(resolved))
            values.sort(key=factor_sort_key)
            return grouped_factors(values)

        def resolve_g1_saddles(self, raw: object) -> dict[str, object]:
            names = sorted(
                {
                    self.saddle_names[value]
                    for value in (raw if isinstance(raw, list) else [])
                    if value in self.saddle_names
                }
            )
            return {
                "count": len(names),
                "names": names,
                "details": [{"name": name} for name in names],
            }

        def resolve_g1_results(self, raw: object) -> set[str]:
            return {
                str(item["name"])
                for item in (raw if isinstance(raw, list) else [])
                if isinstance(item, dict) and item.get("result_rank") == 1
            }

    @staticmethod
    def fake_catalogs(
        _master: Path,
        destination: Path,
        logger: object | None = None,
    ) -> SimpleNamespace:
        paths = {
            "skills_path": destination / "skill_condition_catalog.json",
            "condition_types_path": destination / "condition_type_catalog.json",
            "weights_template_path": destination / "white_skill_weights_template.json",
            "race_factor_skills_path": destination / "race_factor_skill_catalog.json",
        }
        for path in paths.values():
            path.write_text("{}\n", encoding="utf-8")
        if callable(logger):
            logger("Catalogues de test générés.")
        return SimpleNamespace(**paths)

    def test_linking_generates_complete_artifacts_and_diagnostics(self) -> None:
        self.FakeResolver.created_count = 0
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            master = root / "master.mdb"
            source = root / "trained_chara_data.json"
            output = root / "output"
            master.write_bytes(b"controlled master bytes")
            source.write_text(
                json.dumps(
                    {
                        "trained_chara_array": [
                            {
                                "trained_chara_id": 1,
                                "card_id": 100,
                                "factor_info_array": [
                                    {"factor_id": 1},
                                    {"factor_id": 999},
                                ],
                                "win_saddle_id_array": [10, 20],
                                "race_result_list": [
                                    {"name": "Shared G1", "result_rank": 1},
                                    {"name": "Results G1", "result_rank": 1},
                                ],
                                "succession_trained_chara_id_1": 2,
                                "succession_trained_chara_id_2": 777,
                                "succession_chara_array": [
                                    {
                                        "position_id": 10,
                                        "card_id": 200,
                                        "factor_info_array": [{"factor_id": 2}],
                                        "win_saddle_id_array": [10],
                                    },
                                    {
                                        "position_id": 20,
                                        "card_id": 404,
                                        "owner_viewer_id": 123,
                                        "factor_info_array": [{"factor_id": 3}],
                                        "win_saddle_id_array": [30],
                                    },
                                ],
                                "is_locked": True,
                                "is_saved": True,
                                "icon_type": 2,
                                "memo": "keep",
                                "rank": 8,
                                "rank_score": 12345,
                                "speed": 1200,
                                "stamina": 800,
                                "power": 1000,
                                "guts": 600,
                                "wiz": 900,
                            },
                            {
                                "trained_chara_id": 2,
                                "card_id": 200,
                                "factor_info_array": [{"factor_id": 2}],
                                "win_saddle_id_array": [],
                                "race_result_list": [],
                                "succession_chara_array": [],
                            },
                            {
                                "trained_chara_id": 90,
                                "card_id": 200,
                                "use_type": 1,
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            logs: list[str] = []

            with (
                patch("uma_legacy_linker.legacy_linker.MasterResolver", self.FakeResolver),
                patch("uma_legacy_linker.legacy_linker.generate_skill_catalogs", self.fake_catalogs),
            ):
                result = link_veterans(master, source, output, logger=logs.append)

            self.assertEqual(result.veteran_count, 2)
            self.assertEqual(result.unresolved_factor_ids, (999,))
            self.assertEqual(result.unresolved_card_ids, (404,))
            self.assertEqual(result.g1_validation_mismatch_count, 1)
            self.assertFalse(result.reused)
            self.assertEqual(self.FakeResolver.created_count, 1)
            self.assertTrue(self.FakeResolver.last_instance.closed)
            for path in (
                result.json_path,
                result.csv_path,
                result.report_path,
                result.skills_catalog_path,
                result.condition_types_path,
                result.weights_template_path,
                result.race_factor_skills_path,
                result.manifest_path,
            ):
                self.assertTrue(path.is_file(), path)

            payload = json.loads(result.json_path.read_text(encoding="utf-8"))
            metadata = payload["metadata"]
            self.assertEqual(metadata["format_version"], 2)
            self.assertEqual(metadata["veteran_count"], 2)
            self.assertEqual(metadata["source_master_mdb"]["sha256"], sha256_file(master))
            self.assertEqual(metadata["source_veterans_json"]["sha256"], sha256_file(source))
            self.assertEqual(metadata["direct_parent_snapshots"], 2)
            self.assertEqual(metadata["direct_parents_still_present_in_export"], 1)
            self.assertEqual(metadata["unresolved_factor_ids"], [999])
            self.assertEqual(metadata["unresolved_card_ids"], [404])

            linked = payload["veterans"][0]
            self.assertTrue(linked["is_locked"])
            self.assertTrue(linked["is_saved"])
            self.assertEqual(linked["icon_type"], 2)
            self.assertEqual(linked["memo"], "keep")
            parent_1 = linked["when_used_as_parent"]["grandparent_1"]
            parent_2 = linked["when_used_as_parent"]["grandparent_2"]
            self.assertTrue(parent_1["present_in_export"])
            self.assertFalse(parent_1["borrowed_or_external"])
            self.assertFalse(parent_2["present_in_export"])
            self.assertTrue(parent_2["borrowed_or_external"])
            self.assertEqual(
                linked["when_used_as_parent"]["lineage_summary"][
                    "g1_repeated_in_lineage"
                ],
                {"Shared G1": ["parent", "grandparent_1"]},
            )

            with result.csv_path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter=";"))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["trained_chara_id"], "1")
            self.assertEqual(rows[0]["grandparent_1"], "Local Parent Costume")
            self.assertEqual(rows[0]["lineage_g1_union_count"], "3")

            report = result.report_path.read_text(encoding="utf-8")
            self.assertIn("Vétérans : 2", report)
            self.assertIn("Factor IDs non résolus :\n999", report)
            self.assertIn("Costume IDs non résolus :\n404", report)
            self.assertTrue(
                any("vétéran(s) emprunté(s) écarté(s)" in line for line in logs)
            )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], LINK_CACHE_SCHEMA_VERSION)
            self.assertEqual(manifest["inputs"]["master"]["sha256"], sha256_file(master))
            self.assertEqual(manifest["inputs"]["veterans"]["sha256"], sha256_file(source))
            self.assertEqual(link_cache_freshness(master, source, output).state, "ready")

            with (
                patch("uma_legacy_linker.legacy_linker.MasterResolver", self.FakeResolver),
                patch("uma_legacy_linker.legacy_linker.generate_skill_catalogs", self.fake_catalogs),
            ):
                cached = link_veterans(master, source, output, logger=logs.append)
            self.assertTrue(cached.reused)
            self.assertEqual(self.FakeResolver.created_count, 1)
            self.assertTrue(any("réutilisation" in line for line in logs))

            source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            self.assertEqual(
                link_cache_freshness(master, source, output).state,
                "inputs_changed",
            )
            with (
                patch("uma_legacy_linker.legacy_linker.MasterResolver", self.FakeResolver),
                patch("uma_legacy_linker.legacy_linker.generate_skill_catalogs", self.fake_catalogs),
            ):
                refreshed = link_veterans(master, source, output)
            self.assertFalse(refreshed.reused)
            self.assertEqual(self.FakeResolver.created_count, 2)
            self.assertEqual(link_cache_freshness(master, source, output).state, "ready")

            refreshed.csv_path.unlink()
            self.assertEqual(
                link_cache_freshness(master, source, output).state,
                "not_generated",
            )

            with (
                patch("uma_legacy_linker.legacy_linker.MasterResolver", self.FakeResolver),
                patch("uma_legacy_linker.legacy_linker.generate_skill_catalogs", self.fake_catalogs),
            ):
                valid_again = link_veterans(master, source, output)
            self.assertTrue(valid_again.manifest_path.is_file())
            with patch(
                "uma_legacy_linker.legacy_linker.MasterResolver",
                side_effect=LinkerError("échec contrôlé"),
            ):
                with self.assertRaisesRegex(LinkerError, "échec contrôlé"):
                    link_veterans(master, source, output, force_relink=True)
            self.assertFalse(valid_again.manifest_path.exists())
            self.assertEqual(
                link_cache_freshness(master, source, output).state,
                "not_generated",
            )
            with (
                patch("uma_legacy_linker.legacy_linker.MasterResolver", self.FakeResolver),
                patch("uma_legacy_linker.legacy_linker.generate_skill_catalogs", self.fake_catalogs),
            ):
                repaired = link_veterans(master, source, output)
                forced = link_veterans(
                    master,
                    source,
                    output,
                    force_relink=True,
                )
            self.assertFalse(repaired.reused)
            self.assertFalse(forced.reused)
            self.assertEqual(self.FakeResolver.created_count, 5)

            invalid_manifest = json.loads(
                forced.manifest_path.read_text(encoding="utf-8")
            )
            invalid_manifest["schema_version"] = 0
            forced.manifest_path.write_text(
                json.dumps(invalid_manifest), encoding="utf-8"
            )
            self.assertEqual(
                link_cache_freshness(master, source, output).state,
                "not_generated",
            )

    def test_missing_input_files_fail_before_resolver_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaisesRegex(LinkerError, "MDB introuvable"):
                link_veterans(root / "missing.mdb", root / "missing.json", root)


if __name__ == "__main__":
    unittest.main()
