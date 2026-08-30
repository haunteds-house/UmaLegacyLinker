from __future__ import annotations

import unittest

from ui_qt.lineage_nodes import build_result_lineage_nodes
from ui_qt.presentation import online_detail_html, result_detail_html


class DiagnosticPresentationTests(unittest.TestCase):
    def test_transfer_diagnostic_exposes_verdict_and_replacement_evidence(self) -> None:
        from ui_qt.presentation import transfer_detail_html

        protected = {
            "present": True,
            "carrier_count": 2,
            "total_stars": 5,
            "neutral_probability": 0.267,
        }
        row = {
            "card_name": "Candidate",
            "rank_score": 9000,
            "status": "safe_transfer",
            "reason_code": "strictly_dominated_same_card",
            "sparks": {
                "all": [
                    {"type": "blue_stat", "name": "Speed", "stars": 3},
                    {"type": "white_skill", "name": "Nimble Navigator", "stars": 2},
                ]
            },
            "parent_evidence": {
                "elite": True,
                "repeated": True,
                "competitive_context_count": 7,
                "competitive_distinct_profile_count": 3,
                "elite_context_count": 2,
                "evaluated_context_count": 21,
                "evaluated_distinct_profile_count": 7,
            },
            "grandparent_evidence": {
                "elite": False,
                "repeated": False,
                "competitive_context_count": 1,
                "competitive_distinct_profile_count": 1,
                "elite_context_count": 0,
                "evaluated_context_count": 21,
                "evaluated_distinct_profile_count": 7,
            },
            "dominated_by": {
                "card_name": "Replacement",
                "rank_score": 10000,
                "rank": "UG5",
                "stats": {
                    "speed": 1200,
                    "stamina": 800,
                    "power": 1000,
                    "guts": 600,
                    "wiz": 900,
                },
                "grandparent_1": "GP One",
                "grandparent_2": "GP Two",
                "sparks": {
                    "all": [
                        {"type": "blue_stat", "name": "Speed", "stars": 2},
                        {"type": "white_skill", "name": "Corner Adept", "stars": 3},
                    ]
                },
                "mean_score_lead": 2.5,
                "worst_context_delta": 0.5,
                "best_context_delta": 4.25,
                "viable_parent_comparisons": 21,
                "viable_grandparent_comparisons": 14,
            },
            "spark_protection": {
                "applied": False,
                "protected_skills": [
                    {
                        "name": "Nimble Navigator",
                        "candidate": protected,
                        "replacement": protected,
                        "preserved_by_replacement": True,
                    }
                ],
            },
        }

        rendered = transfer_detail_html(row, "en")

        self.assertIn("Verdict evidence", rendered)
        self.assertIn("7 / 21", rendered)
        self.assertIn("3 / 7", rendered)
        self.assertIn("Best observed delta", rendered)
        self.assertIn("+4.250", rendered)
        self.assertIn("Viable parent comparisons", rendered)
        self.assertIn("GP One × GP Two", rendered)
        self.assertIn("Complete Spark comparison", rendered)
        self.assertIn("Corner Adept", rendered)
        self.assertIn("Protected heritage comparison", rendered)
        self.assertIn("Preserved", rendered)

    def test_canonical_identity_shows_zero_score_without_internal_id(self) -> None:
        from ui_qt.presentation import transfer_detail_html

        rendered = transfer_detail_html(
            {
                "card_name": "Tach-nology",
                "rank_score": 0,
                "trained_chara_id": 918273,
                "status": "keep",
            },
            "fr",
        )

        self.assertIn("Tach-nology · 0", rendered)
        self.assertNotIn("#918273", rendered)

    def test_future_gp_shows_per_skill_generation_gains_and_affinity_context(self) -> None:
        row = {
            "score": 73.2,
            "card_name": "Candidate GP",
            "affinity_raw": 24,
            "future_parent_base_affinity": 18,
            "future_branch_base_total": 42,
            "g1_count": 11,
            "components": {"white_generation": 61.5},
            "score_breakdown": {
                "components": {
                    "white_generation": {
                        "component_score": 61.5,
                        "weight": 0.21,
                        "points": 12.915,
                    }
                }
            },
            "component_details": {
                "white_generation": {
                    "bonus_per_lineage_copy": 0.025,
                    "skill_count": 2,
                    "skills": [
                        {
                            "name": "Uma Stan",
                            "lineage_copy_count": 3,
                            "lineage_generation_bonus": 0.075,
                            "contribution": 0.06,
                        },
                        {
                            "name": "Tail Held High",
                            "lineage_copy_count": 1,
                            "lineage_generation_bonus": 0.025,
                            "contribution": 0.02,
                        },
                    ],
                }
            },
        }

        html = result_detail_html(row, "future", "fr")

        self.assertIn("Base Ace × parent ciblé", html)
        self.assertIn("Total de branche projeté", html)
        self.assertIn("Gains de génération des White Sparks", html)
        self.assertIn("Uma Stan", html)
        self.assertIn("+7.50 pts", html)
        self.assertIn("+2.50 points par porteur", html)
        self.assertIn("ni la probabilité totale", html)

    def test_scenario_proc_probability_reaches_the_visual_spark(self) -> None:
        row = {
            "parent_1": {"card_name": "Parent"},
            "parent_2": {"card_name": "Other"},
            "lineage_preview": {
                "p1": {
                    "card_name": "Parent",
                    "sparks": [
                        {"name": "Grand Live", "stars": 2, "type": "scenario"}
                    ],
                }
            },
            "component_details": {
                "blue": {
                    "scenario_inheritance": {
                        "inspiration_event_count": 2,
                        "factors": [
                            {
                                "role": "parent_1",
                                "name": "Grand Live",
                                "stars": 2,
                                "proc_probability_over_run": 0.1891,
                            }
                        ],
                    }
                }
            },
        }

        nodes = build_result_lineage_nodes(None, row, "pair")
        scenario = nodes["p1"]["sparks"][0]

        self.assertAlmostEqual(scenario["proc_probability_over_run"], 0.1891)
        self.assertEqual(scenario["inspiration_event_count"], 2)

    def test_contextual_gp_diagnostic_exposes_final_pair_and_production_run(self) -> None:
        row = {
            "score": 81.0,
            "fixed_grandparent": {"card_name": "Local GP"},
            "candidate": {"card_name": "Remote GP"},
            "final_parent_affinity": {
                "base": 45,
                "planned_g1_bonus": 18,
                "potential_total": 63,
                "common_g1_count": 3,
            },
            "projected_future_parent": {"card_name": "Target Parent"},
            "opposing_parent": {"card_name": "Opposing Parent"},
            "aptitude_summaries": {
                "surface": {
                    "base_rank_label": "B",
                    "initial_rank_label": "A",
                    "probability_reach_s": 0.22,
                },
                "style": {
                    "base_rank_label": "A",
                    "initial_rank_label": "A",
                    "probability_reach_s": 0.0,
                },
            },
            "distance_s_summary": {
                "base_rank_label": "A",
                "initial_rank_label": "A",
                "probability_reach_s": 0.48,
                "total_stars": 8,
                "carrier_count": 3,
                "parent_carrier_count": 1,
                "procs_required_for_a": 0,
                "procs_required_for_s": 1,
            },
            "distance_viability": {"key": "ready_for_s", "tier": 4},
            "production_affinity": {
                "total": 156,
                "scored_value": 72,
                "gp1_inheritance_modifier": {"total": 70},
                "gp2_inheritance_modifier": {"total": 74},
            },
            "components": {"white_generation": 35.0},
            "score_breakdown": {"components": {}},
            "component_details": {
                "white_generation": {
                    "bonus_per_lineage_copy": 0.025,
                    "included_in_weighted_score": False,
                    "skill_count": 1,
                    "skills": [
                        {
                            "name": "Tail Held High",
                            "lineage_copy_count": 2,
                            "lineage_generation_bonus": 0.05,
                            "contribution": 0.04,
                        }
                    ],
                }
            },
        }

        html = online_detail_html(
            row,
            "grandparent",
            "fr",
            {"surface": "turf", "distance": "medium", "style": "pace_chaser"},
        )

        self.assertIn("Projection de la paire finale", html)
        self.assertIn("Opposing Parent", html)
        self.assertIn("48.0%", html)
        self.assertIn("Affinité de la run de production", html)
        self.assertIn("156.0", html)
        self.assertIn("+5.00 pts", html)
        self.assertIn(">Non<", html)


if __name__ == "__main__":
    unittest.main()
