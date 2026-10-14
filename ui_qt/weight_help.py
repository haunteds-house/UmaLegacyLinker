from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from uma_legacy_linker.labels import scoring_label
from ui_qt.weight_controls import is_percentage_setting, is_probability_setting


@dataclass(frozen=True)
class WeightHelp:
    summary: str
    impact: str
    scope: str
    low_label: str
    high_label: str
    advanced: bool = False





def _label(key: str, language: str) -> str:
    return scoring_label(key, language)


def _scope(path: Sequence[str], language: str) -> str:
    if "parent_pair" in path:
        return "Final pair"
    if "parent_branch" in path:
        return "Parent branch"
    if "future_grandparent" in path:
        return "Future grandparent"
    if path and path[0] in {"uma_moe_pair", "uma_moe_parent_search"}:
        return "uma.moe"
    if path and path[0] == "transfer_helper":
        return "Transfer Helper"
    if path and path[0] == "future_grandparent_heuristics":
        return "Future grandparent"
    if path and path[0] in {"aptitude_inheritance", "future_grandparent_heuristics"}:
        return "Aptitudes"
    if path and path[0] in {
        "blue_stat_weights_by_distance",
        "blue_star_quality",
        "blue_score_influence_by_distance",
        "blue_neutral_score",
        "scenario_inheritance",
    }:
        return "Blue Sparks"
    if path and path[0] in {
        "white_inheritance",
        "white_saturation",
        "white_generation",
        "position_transmission",
    }:
        return "White Skills"
    if path and path[0] == "course_conditions":
        return "Race conditions"
    return "Lineage score"


def _scale_labels(path: Sequence[str], value: object, language: str) -> tuple[str, str]:
    root = path[0] if path else ""
    leaf = path[-1] if path else ""
    if root == "transfer_helper" and "spark_protection" in path:
        if leaf == "enabled":
            return (
                "Disabled",
                "Enabled",
            )
        if leaf == "replacement_probability_tolerance":
            return (
                "No tolerance",
                "More permissive",
            )
        if leaf == "important_packages":
            return (
                "No package",
                "Custom packages",
            )
        return (
            "Broader protection",
            "More selective protection",
        )
    if root == "transfer_helper" and any(
        token in leaf for token in ('minimum', 'tolerance')
    ):
        return (
            "More permissive",
            "Stricter",
        )
    if root == "course_conditions" and (
        leaf == "active_green_floor" or "floors" in path
    ):
        return (
            "No floor",
            "Maximum floor",
        )
    if is_probability_setting(path):
        return (
            "No chance",
            "Maximum chance",
        )
    if is_percentage_setting(path, value):
        return (
            "Ignored",
            "Higher priority",
        )
    if root in {"white_saturation", "race_saturation"} or (
        root == "white_generation" and path[-1:] == ("saturation",)
    ):
        return (
            "Earlier saturation",
            "Later saturation",
        )
    return ("Less", "More")


def _component_impact(component: str, language: str) -> str:
    impacts = {
        "distance_s": 'Increasing it favours lineages that secure an S distance rank, even when their other Sparks are weaker.',
        "surface_aptitude": 'Increasing it favours lineages that secure the targeted initial surface rank ahead of the other pink aptitudes.',
        "pink_other": 'Increasing it gives more value to running-style aptitudes beyond the Distance S and Surface constraints.',
        "white_skill": 'Increasing it favours lineages that can inherit useful White Skills with good probability.',
        "race_scenario": 'Increasing it gives the small intrinsic stat value of Race Sparks more influence. Scenario Sparks are already included in Blues.',
        "blue": 'Increasing it favours Blue Spark quality and the expected value of Scenario Sparks for the selected distance.',
        "unique": 'Increasing it gives inherited green Unique Sparks more influence.',
        "affinity": 'Increasing it favours candidates with strong modern affinity to the Ace and target parent.',
        "g1_potential": 'Increasing it gives more value to shared G1 races and future-parent G1-link potential.',
        "pink": 'Increasing it favours future grandparents carrying directly useful Pink Sparks.',
        "white_generation": 'Increasing it favours lineages that can generate useful White Sparks while producing the parent.',
    }
    english = impacts.get(
        component,
        "Increasing it gives this component more influence in the ranking.",
    )
    return english


_PARENT_SEARCH_HELP: dict[tuple[str, str], tuple[str, str]] = {
    ("retrieval", "enabled"): ('Enables splitting the API budget into Distance, Surface, and Broad cohorts instead of a single white-sorted query.', 'Disabling it returns to the single sample, where branches rich in the required pinks can vanish from the pool before any scoring.'),
    ("retrieval", "surface_cohort_enabled"): ('Allows the dedicated target-surface star cohort during API retrieval.', 'Disabling it frees its share for Distance and Broad, useful when the Ace already starts at A on the surface.'),
    ("retrieval", "distance_share"): ('Base share of the API budget reserved for the distance-star-sorted cohort.', 'Increasing it secures more distance carriers in the pool at the expense of the Surface and Broad cohorts.'),
    ("retrieval", "surface_share_below_minimum"): ('Surface share used while the Ace’s initial rank stays below the configured minimum rank.', 'Increasing it fetches more remote branches carrying the surface when the need is greatest.'),
    ("retrieval", "surface_share_at_minimum"): ('Surface share used once the Ace reaches the minimum rank but not the preferred rank.', 'Increasing it keeps feeding the surface cohort past the B threshold instead of shifting towards Distance and Broad.'),
    ("retrieval", "surface_share_at_preferred"): ('Surface share kept when the Ace already starts at the preferred surface rank.', 'Leaving it at zero devotes the remaining budget to the other cohorts; increasing it keeps a safety margin.'),
    ("retrieval", "broad_minimum_share"): ('Minimum share guaranteed to the broad white-sorted cohort regardless of other demands.', 'Increasing it protects white diversity in the pool; Distance and Surface are rescaled when needed.'),
    ("retrieval", "balanced_branch_divisor"): ('Divisor applied to the total star need so the remote branch is asked for a balanced share rather than everything.', 'Increasing it lowers the star threshold requested from the remote side and assumes the local side completes the rest.'),
    ("retrieval", "contextual_distance_star_target"): ('Distance-star reference targeted in fixed-opposing-parent mode once the initial A start is covered.', 'Increasing it keeps more distance carriers in the sample to aim at P(S) instead of shrinking the search to the bare minimum.'),
    ("retrieval", "contextual_distance_need_floor"): ('Minimum demand kept by the Distance cohort even when the opposing parent already covers the computed need.', 'Increasing it prevents apparent coverage from shrinking the Distance cohort to almost nothing.'),
    ("retrieval", "contextual_surface_reallocation_to_distance"): ('Fraction of the freed Surface share reallocated to the Distance cohort in fixed-opposing-parent mode.', 'Increasing it converts already-covered surface into extra distance stars; the remainder goes to the broad cohort.'),
    ("preselection", "distance_share"): ('Slots reserved for the most distance-rich remote branches before the local × remote cartesian product.', 'Increasing it keeps more distance specialists for exact evaluation at the cost of high-overall-score candidates.'),
    ("preselection", "surface_share_below_minimum"): ('Slots reserved for surface-rich branches while the Ace stays below the minimum rank.', 'Increasing it prevents two individually average but complementary branches from vanishing before the exact six-member score.'),
    ("preselection", "surface_share_at_minimum"): ('Surface slots reserved once the Ace reaches the minimum but not the preferred rank.', 'Increasing it keeps surface carriers past the B threshold; the remaining slots return to the overall ranking.'),
    ("preselection", "surface_share_at_preferred"): ('Surface slots kept when the Ace already starts at the preferred rank.', 'Zero returns every slot to the overall ranking; a small value keeps a few specialists as a precaution.'),
}


_CONTEXTUAL_OPPONENT_HELP: dict[str, tuple[str, str]] = {
    "white_retrieval_coverage_decay": ('Attenuation applied during API retrieval to the weight of whites already covered by the opposing parent.', 'Increasing it steers the query towards complementary whites; zero ignores the opposing parent’s coverage.'),
    "white_preselection_coverage_decay": ('Attenuation applied during preselection to the value of whites already covered by the opposing parent.', 'Increasing it favours branches that complete the pair instead of duplicating its whites; zero disables the effect.'),
    "preselection_affinity_weight": ('Weight of candidate affinity in preselection when an opposing parent is fixed.', 'The near-zero default lets the exact parent_pair engine judge affinity; increasing it reintroduces the signal too early.'),
    "preselection_g1_weight": ('Weight of G1 potential in preselection when an opposing parent is fixed.', 'The near-zero default avoids duplicating the exact engine; increasing it surfaces G1 links as early as preselection.'),
    "preselection_white_generation_weight": ('Weight of white-generation capacity in contextual preselection.', 'Increasing it favours branches that repeat useful whites during production, ahead of the exact score.'),
}


_TRANSFER_HELP: dict[str, tuple[str, str]] = {
    "analysis_mode": ('Fast mode uses the permanent baseline and naturally viable Aces; exhaustive audit restores every style and Ace variant.', 'Exhaustive mode is intended as an occasional control, may take several minutes, and enables the strictly safe verdict.'),
    "portfolio_regret_tolerance": ("Maximum accepted gap between the costume's best copy and the retained portfolio in each competitive niche.", 'Increasing it transfers more micro-variants; reducing it retains more copies close to the best score.'),
    "portfolio_direct_white_minimum_context_weight": ('Minimum contextual weight for a direct White to become a mandatory portfolio asset.', 'Increasing it limits this protection to the most strategic skills.'),
    "portfolio_direct_white_min_stars": ('Minimum star count for a collectively protected direct White.', 'Two stars protects already solid direct sources without retaining every 1-star White.'),
    "minimum_ace_aptitude_rank": ('Minimum natural surface, distance, and style rank required for an Ace to participate in fast mode.', 'B removes theoretical pairings without sacrificing naturally plausible Aces; exhaustive mode ignores this filter.'),
    "include_permanent_archetypes": ('Enables the stable Turf Sprint/Mile/Medium/Long and Dirt Sprint/Mile/Medium baseline.', 'Keeping it enabled prevents the temporary CM rotation from authorising irreversible cleanup.'),
    "include_upcoming_cm_context": ('Adds upcoming Champion Meetings as contextual evidence on top of the permanent baseline.', 'Enabling it may retain specialists useful soon and lengthens analysis; their absence never removes a permanent archetype.'),
    "competitive_score_floor": ('Absolute score at which a role starts to count as competitive.', 'Increasing it ignores more weak niches and makes verdicts more conservative.'),
    "dominance_tolerance": ('Small allowed deficit when a copy is compared with its replacement in each viable niche.', 'Increasing it allows a replacement to be slightly worse in an isolated niche.'),
    "dominance_mean_margin": ('Minimum average lead required to confirm that a replacement truly dominates a copy.', 'Increasing it requires a clearer average advantage before suggesting a safe transfer.'),
    "include_course_presets": ('Adds configured Champion Meetings to the analysed contexts.', 'Disabling it speeds up analysis but can hide a niche tied to a specific race.'),
    "upcoming_cm_limit": ('Number of upcoming Champion Meetings included in the collection audit.', 'Increasing it covers more races at the cost of longer analysis and more conservative verdicts.'),
    "include_team_trials": ('Adds Team Trials profiles to parent and grandparent contexts.', 'Enabling it protects veterans that are useful outside Champion Meetings.'),
    "include_generic_profiles": ('Adds generic surface × distance profiles in addition to known races.', 'Enabling it greatly broadens coverage and reduces the number of transfers considered safe.'),
    "minimum_competitive_contexts": ('Number of competitive contexts required for a value to count as recurring.', 'Increasing it separates versatile profiles from one-off niches more strictly.'),
    "minimum_distinct_profiles": ('Number of distinct race profiles required to confirm versatile value.', 'Increasing it requires broader usefulness before strengthening a keep verdict.'),
    "competitive_utility_floor": ('Relative-quality threshold combining absolute score, leader proximity, and percentile.', 'Increasing it reserves competitive status for the strongest copies in the pool.'),
    "elite_utility_floor": ('Relative-quality threshold used to identify elite performance.', 'Increasing it makes the elite label rarer without directly changing raw scores.'),
    "minimum_absolute_floor_ratio": ('Minimum share of the absolute floor a niche must reach before it can be viable.', 'Increasing it removes niches where every copy remains globally weak.'),
    "utility_absolute_weight": ('Share of absolute score in Transfer Helper competitive utility.', 'Increasing it favours copies with strong raw value, even in a very strong pool.'),
    "utility_leader_weight": ('Share of proximity to the best local candidate in competitive utility.', 'Increasing it favours copies that stay close to the leader in their context.'),
    "utility_percentile_weight": ('Share of percentile rank in competitive utility.', 'Increasing it gives relative position in the whole pool more importance.'),
    "enabled": ('Enables the verdict floor that protects Spark heritage not reproduced by the replacement.', 'Disabling it makes the verdict depend only on score dominance and G1 support.'),
    "minimum_context_weight": ('Maximum utility required in at least one active profile before a Spark can be protected.', 'Increasing it excludes weak or overly situational Sparks from the safeguard.'),
    "hard_to_obtain_minimum_context_weight": ('Minimum contextual utility required before acquisition scarcity is considered.', 'Increasing it avoids protecting a scarce but low-value Spark.'),
    "hard_to_obtain_max_support_hint_count": ('Maximum number of support cards directly giving the hint for a Spark to count as hard to obtain.', 'Increasing it broadens acquisition protection to Sparks available from more support cards.'),
    "repeated_review_min_carriers": ('Minimum number of distinct members carrying the same effective skill to trigger review.', 'Increasing it reserves protection for more strongly repeated lineages.'),
    "repeated_review_min_total_stars": ('Minimum total stars across the normalised sources of a repeated Spark.', 'Increasing it requires stronger combined quality before raising the verdict.'),
    "repeated_review_min_probability": ('Minimum neutral probability of inheriting a repeated Spark at least once.', 'Increasing it ignores repetitions whose combined proc rates remain low.'),
    "repeated_strong_min_carriers": ('Number of distinct carriers at which repetition becomes a strong signal.', 'Increasing it makes the likely-keep floor less common.'),
    "repeated_strong_min_probability": ('Neutral probability at which repetition becomes a strong signal.', 'Increasing it requires higher combined coverage to reach likely keep.'),
    "direct_future_gp_minimum_context_weight": ('Minimum contextual utility for a Spark carried directly by the future grandparent.', 'Increasing it limits this strong protection to the most decisive skills.'),
    "direct_future_gp_min_stars": ('Minimum direct stars required to strongly protect a future grandparent.', 'Increasing it reserves this safeguard for higher-quality direct Sparks.'),
    "replacement_probability_ratio": ('Fraction of the veteran’s inheritance probability the replacement must retain.', 'Increasing it requires coverage closer to the original.'),
    "replacement_probability_tolerance": ('Absolute probability gap tolerated when comparing inheritance assets.', 'Increasing it accepts a slightly larger loss in the replacement.'),
    "important_packages": ('Advanced list of skill sets whose combined coverage should be preserved.', 'Editing this list changes only the verdict floor, never the primary score.'),
}


def describe_weight(path: Sequence[str], value: Any, language: str) -> WeightHelp:
    path = tuple(path)
    root = path[0] if path else ""
    leaf = path[-1] if path else ""
    scope = _scope(path, language)
    low, high = _scale_labels(path, value, language)
    advanced = isinstance(value, (list, dict))

    if root == "mode_weights" and len(path) >= 3:
        component = path[-1]
        summary = f"Independent weight of “{_label(component, language)}” in the {scope.lower()} score. The engine normalises it with neighbouring weights without changing their values."
        return WeightHelp(summary, _component_impact(component, language), scope, low, high)

    if root == "future_grandparent_heuristics" and leaf == "g1_win_probability_cutoff":
        return WeightHelp(
            "Minimum win chance required for a G1 to count during the future parent’s Independent Training run.",
            "The G1 keeps its full value above the cutoff and is worth zero below it, after consecutive-race penalties.",
            scope,
            low,
            high,
        )

    if root == "blue_stat_weights_by_distance" and len(path) == 3:
        distance = _label(path[1], language)
        stat = _label(path[2], language)
        summary = f"Relative importance of {stat} among Blue Sparks for {distance} races."
        impact = f"Increasing it raises lineages carrying more {stat} Blue Sparks for this distance profile."
        return WeightHelp(summary, impact, scope, low, high)

    if root in {"blue_star_quality", "unique_star_quality", "star_quality"}:
        stars = _label(leaf, language)
        family = {
            "blue_star_quality": "Blue Spark",
            "unique_star_quality": "green Unique",
            "star_quality": "Race Spark",
        }[root]
        summary = f"Relative quality assigned to a {stars} {family}, compared with the 3★ tier."
        impact = f"Increasing it narrows the value gap between this tier and the best {family}s."
        return WeightHelp(summary, impact, scope, low, high)

    if root == "position_transmission":
        position = _label(leaf, language)
        summary = f"Multiplier applied to Sparks carried in the “{position}” lineage position."
        impact = "Increasing it makes factors from this generation more important than those in other positions."
        return WeightHelp(summary, impact, scope, low, high)

    if root in {"white_saturation", "race_saturation"} or (
        root == "white_generation" and leaf == "saturation"
    ):
        family = "White Skills" if root != "race_saturation" else "Race Sparks"
        summary = f"Diminishing-return scale used when several useful {family} contributions are added together."
        impact = "Increasing it delays saturation, so very dense lineages continue gaining more score."
        return WeightHelp(summary, impact, scope, low, high)

    if root == "race_factor":
        family = "Race Sparks"
        summary = f"Raw value contributed by {family} before saturation and the global component weight."
        impact = f"Increasing it makes each {family[:-1] if family.endswith('s') else family} more valuable in the ranking."
        return WeightHelp(summary, impact, scope, low, high)

    if root == "scenario_inheritance":
        if "base_proc_rates" in path:
            stars = _label(leaf, language)
            summary = f"Base probability per Inspiration Event for a {stars} Scenario Spark, before individual affinity."
        elif leaf == "inspiration_event_count":
            summary = "Number of Inspiration Events included in the expected stat value of Scenario Sparks."
        elif leaf == "per_event_probability_cap":
            summary = "Per-Inspiration-Event probability cap for a Scenario Spark proc."
        else:
            summary = "Number of Blue-Spark equivalents assigned to every stat granted by one Scenario Spark proc."
        impact = "Increasing it raises the expected Scenario-Spark bonus inside the Blue component, which may exceed 100."
        return WeightHelp(summary, impact, scope, low, high)

    if root == "affinity":
        if leaf.endswith("thresholds"):
            summary = "Curve that converts raw affinity or G1 count into a normalised score from 0 to 100."
            impact = "Raising a curve point rewards that raw level more; moving its input changes the required threshold."
            return WeightHelp(summary, impact, scope, low, high, True)
        if leaf == "g1_common_bonus":
            return WeightHelp(
                "Affinity bonus added for each shared G1 race on a visible link.",
                "Increasing it favours lineages whose members repeat the same G1 races.",
                scope, low, high,
            )
        if leaf == "same_character_compatibility":
            return WeightHelp(
                "Base compatibility used when two costumes represent the same character.",
                "The default grants no bonus; increasing it softens this incompatibility.",
                scope, low, high, True,
            )
        return WeightHelp(
            "Affinity engine used to calculate lineage links.",
            "This choice shapes the full calculation; change it only for a compatible profile.",
            scope, low, high, True,
        )

    if root == "course_conditions":
        condition = _label(leaf, language)
        if "modes" in path:
            summary = f"Method used to apply the “{condition}” condition to a Green Skill."
            impact = "“Minimum floor” keeps the better existing value; “Override” enforces the configured value."
            return WeightHelp(summary, impact, scope, low, high, True)
        summary = f"Minimum retained value when a Green Skill matching “{condition}” is active."
        impact = "Increasing it rewards Greens that match the exact race conditions more strongly."
        return WeightHelp(summary, impact, scope, low, high)

    if root == "white_generation":
        if leaf == "bonus_per_lineage_copy":
            summary = "Generation bonus added for each lineage member already carrying the same White Skill."
            impact = "Increasing it favours repeated useful Whites in the production branch."
        else:
            summary = "Maximum number of copies of the same White Skill counted in the lineage."
            impact = "Increasing it lets highly redundant lineages keep receiving a bonus."
        return WeightHelp(summary, impact, scope, low, high)

    if root == "uma_moe_pair":
        if len(path) > 1 and path[1] == "contextual_opponent" and leaf in _CONTEXTUAL_OPPONENT_HELP:
            en_summary, en_impact = _CONTEXTUAL_OPPONENT_HELP[leaf]
            return WeightHelp(
                en_summary,
                en_impact,
                scope, low, high,
            )
        if len(path) > 1 and path[1] in {"weights", "preselection_weights"}:
            component = leaf
            stage = "final score" if path[1] == "weights" else "fast preselection"
            summary = f"Share of “{_label(component, language)}” in the uma.moe pair {stage}."
            impact = _component_impact(component, language)
            return WeightHelp(summary, impact, scope, low, high)
        if leaf.endswith("thresholds"):
            return WeightHelp(
                "Conversion curve used to normalise this uma.moe measure to 100 points.",
                "Editing the points changes the thresholds at which a pair is considered weak, good, or excellent.",
                scope, low, high, True,
            )
        if leaf == "planned_g1_budget_default":
            summary = "Number of G1 races assumed achievable while producing the parent."
            impact = "Increasing it gives G1 potential more room without treating an unearned link as guaranteed."
        elif leaf == "single_g1_weight_default":
            summary = "Relative value of a G1 race present on only one of the two grandparents."
            impact = "Increasing it brings a one-sided G1 closer to the value of a G1 shared by both sides."
        else:
            summary = "Preselection curve for the combined potential of the three GP-branch members."
            impact = "Making it more generous keeps more candidates for full evaluation."
            advanced = True
        return WeightHelp(summary, impact, scope, low, high, advanced)

    if root == "uma_moe_parent_search":
        stage = path[1] if len(path) > 1 else ""
        help_entry = _PARENT_SEARCH_HELP.get((stage, leaf))
        if help_entry is not None:
            en_summary, en_impact = help_entry
            return WeightHelp(
                en_summary,
                en_impact,
                scope, low, high,
            )

    if root == "transfer_helper" and leaf in _TRANSFER_HELP:
        en_summary, en_impact = _TRANSFER_HELP[leaf]
        return WeightHelp(
            en_summary,
            en_impact,
            scope, low, high,
        )

    if root == "aptitude_inheritance":
        dimension = next((part for part in path if part in {"distance", "surface", "style"}), None)
        dimension_label = _label(dimension, language) if dimension else "aptitude"
        if "pink_base_proc_rates" in path:
            stars = _label(leaf, language)
            summary = f"Base chance for a {stars} Pink Spark to proc during an Inspiration Event."
            impact = "Increasing it directly improves P(A) and P(S) for lineages carrying this star tier."
        elif leaf == "inspiration_event_count":
            summary = "Number of independent Inspiration Events simulated for each aptitude Spark."
            impact = "Increasing it strongly raises final probabilities; use only the number actually available in game."
        elif leaf == "ignore_multi_rank_procs":
            summary = "Forces the model to count each proc as exactly one aptitude rank."
            impact = "Disabling it requires a reliable model of rare multi-rank procs; enabled is the safe setting."
        elif "dimension_weights_by_mode" in path:
            summary = f"Relative importance of {dimension_label} aptitude in this inheritance score."
            impact = f"Increasing it favours lineages that mainly improve {dimension_label} over the other two aptitudes."
        elif "partial_scoring" in path:
            summary = "Partial-score parameter used when a single branch does not yet reveal the final pair."
            impact = "Increasing it gives this signal more influence in the provisional Distance S estimate."
        elif leaf == "s_probability_curve":
            summary = f"Curve that converts P(S) into utility for {dimension_label} aptitude."
            impact = "Raising an output rewards that probability more; moving an input changes the required threshold."
            advanced = True
        elif "b_compensation" in path:
            summary = f"Compensation threshold used to accept a B start in {dimension_label}."
            impact = "Increasing it makes compensation stricter and rejects more fragile pairs."
        elif leaf == "minimum_initial_rank":
            summary = f"Minimum initial {dimension_label} rank targeted (6 = B): below it, the uma.moe search treats the aptitude as a priority need."
            impact = "Increasing it raises the threshold that triggers the maximum Surface shares in cohorts and preselection."
        elif leaf == "preferred_initial_rank":
            summary = f"Preferred initial {dimension_label} rank (7 = A): once reached, the Surface share switches to its at-preferred value."
            impact = "Increasing it keeps the A goal active longer and delays freeing budget towards Distance and Broad."
        elif "below_b" in path:
            below_help = {
                "base_score": (f'Floor score assigned when the Ace starts below B in {dimension_label}.', 'Increasing it makes very weak starts less penalised in the diagnostic.'),
                "initial_minimum_readiness_weight": (f'Weight of star progress towards the minimum rank while the {dimension_label} start stays below B.', 'Increasing it rewards every star that moves closer to the B threshold, even before reaching it.'),
                "minimum_probability_weight": (f'Weight of the probability of reaching the minimum rank during the run, for a below-B {dimension_label} start.', 'Increasing it favours lineages able to catch up to the B threshold through their pink procs.'),
                "a_probability_weight": (f'Weight of the probability of reaching A during the run, for a below-B {dimension_label} start.', 'Increasing it rewards full climbs to A despite the weak start.'),
                "s_probability_weight": (f'Weight of P(S) quality for a below-B {dimension_label} start.', 'Increasing it keeps a small S signal even in very weak starting scenarios.'),
            }
            en_summary, en_impact = below_help.get(
                leaf,
                (f'{dimension_label} score parameter used when the Ace starts below B.', 'Increasing it gives this starting scenario more influence in the final diagnostic.'),
            )
            summary = en_summary
            impact = en_impact
        else:
            start = "A" if "start_a" in leaf else ("B" if "start_b" in leaf else "below B")
            summary = f"Contribution of “{_label(leaf, language)}” to the {dimension_label} score when the Ace starts at {start}."
            impact = "Increasing it gives this starting scenario more influence in the final diagnostic."
        return WeightHelp(summary, impact, scope, low, high, advanced)

    if root == "blue_score_influence_by_distance":
        distance = _label(leaf, language)
        return WeightHelp(
            f"Overall Blue Spark influence on rankings for {distance} races.",
            "Reducing it pulls a weak Blue score towards neutral; increasing it makes Blues more discriminating.",
            scope, low, high,
        )

    if root == "blue_neutral_score":
        return WeightHelp(
            "Neutral point towards which the Blue score is pulled when distance-specific influence is reduced.",
            "Increasing it makes low-Blue-influence profiles more generous; decreasing it makes them harsher.",
            scope, low, high,
        )

    if root == "white_inheritance":
        if "base_proc_rates" in path or "race_base_proc_rates" in path:
            race = "race_base_proc_rates" in path
            stars = _label(leaf, language)
            family = "Race Spark" if race else "White Skill Spark"
            summary = f"Base inheritance chance of a {stars} {family} per Inspiration Event."
            impact = "Increasing it raises final probability after affinity and repeated lineage copies are applied."
        elif leaf == "inspiration_event_count":
            summary = "Number of independent Inspiration Events used to project White inheritance."
            impact = "Increasing it raises every inheritance probability; keep the real in-game value."
        elif leaf == "per_event_probability_cap":
            summary = "Cap applied to a White Skill chance during a single event."
            impact = "Reducing it limits extremely stacked lineages; 100% adds no artificial cap."
        else:
            summary = "Curve that converts the probability of obtaining a distinct White Skill into score utility."
            impact = "It suppresses anecdotal chances and rewards useful diversity with diminishing returns."
            advanced = True
        return WeightHelp(summary, impact, scope, low, high, advanced)

    if root == "future_grandparent_heuristics":
        stars = _label(leaf, language) if leaf in {"1", "2", "3"} else ""
        if "pink_dimension_weights" in path:
            dimension = _label(leaf, language)
            summary = f"Relative relevance of a {dimension} Pink Spark on a future grandparent."
            impact = f"Increasing it favours GPs carrying the targeted {dimension} aptitude."
        elif "pink_star_quality" in path:
            summary = f"Quality assigned to a {stars} Pink Spark in the simplified future-GP model."
            impact = "Increasing it narrows the gap with 3★ Pink Sparks during preselection."
        elif "pink_need_multiplier" in path:
            rank = "below A" if leaf == "below_a" else "already A or S"
            summary = f"Need multiplier when the Ace’s base aptitude is {rank}."
            impact = "Increasing it gives Pink Sparks that address this need level more value."
        else:
            summary = f"Direct quality assigned to a {stars} White Skill on a future grandparent."
            impact = "Increasing it favours this star tier before the complete final lineage is known."
        return WeightHelp(summary, impact, scope, low, high)

    title = _label(leaf, language) if leaf else "setting"
    parent = _label(path[-2], language) if len(path) > 1 else _label(root, language)
    summary = f"Controls “{title}” in the “{parent}” scoring group."
    impact = "Increasing it generally gives this signal more influence; keep the default if its role is unclear."
    return WeightHelp(summary, impact, scope, low, high, advanced)
