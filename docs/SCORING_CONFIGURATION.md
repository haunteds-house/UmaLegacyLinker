# Scoring configuration and generated weight artifacts

Implementation: the 1.9.0 source tree. Paths are relative to the repository root.

This document defines UmaLegacyLinker's scoring configuration layers and the generated files that connect them to the ranking engines. Formulas, ranking order and model assumptions belong in [`SCORING.md`](SCORING.md).

## 1. Configuration layers

| Layer | Canonical input | Purpose |
| --- | --- | --- |
| Structural defaults | `resources/default_parent_scoring.json` | Component weights, curves, thresholds, retrieval policy, future-GP heuristics and Transfer Helper policy. |
| Structural user override | `parent_scoring_overrides.json` | Minimal recursive differences from structural defaults. |
| White priority defaults | `resources/default_skill_priorities.json` | Strategic value of each White Skill Spark by Surface, Distance and Style. |
| White priority override | Selected JSON, commonly `skill_priorities_custom.json` | Complete or partial override merged over bundled White priorities. |
| Course presets | `resources/default_course_overrides.json` or a selected replacement | Static race metadata and optional per-skill exact-course adjustments. |

Generated files under `output/` are execution artifacts. Regenerate them from these inputs rather than editing them as permanent configuration.

## 2. Effective profiles and persistence

Before Search or Transfer Helper scoring, the application materialises:

- `active_parent_scoring.json` — fully resolved structural profile;
- `active_skill_priorities.json` — fully resolved White priority profile.

These are the first files to inspect when debugging a ranking: they record what the run actually used after defaults, migrations and overrides. The same White priority selection is shared by local and uma.moe Search; an empty selection uses `resources/default_skill_priorities.json`.

`deep_merge()` is shared by both configuration families:

1. objects merge recursively;
2. override-only keys are copied;
3. every non-object value replaces the default value;
4. arrays therefore replace the complete array at that path.

The last rule matters for White `profiles`: overriding that array replaces all bundled rules for the affected skill.

### Structural scoring

Structural overrides pass through `migrate_scoring_overrides()` before merge. The **Weights** editor stores only the recursive diff from `resources/default_parent_scoring.json`; the CLI accepts a complete or partial equivalent through `--scoring-config`.

`validate_scoring_config()` validates the effective profile: finite/non-negative numerics, required mode components, ordered/bounded curves, probabilities, booleans and integer domains, complete star mappings and positive saturation constants among other invariants.

The bundled JSON is the source of truth for the current structural schema and exact defaults. Do not duplicate its full value table here.

### White priorities

White overrides are merged directly with `resources/default_skill_priorities.json`; there is no migration layer. The resulting complete profile is validated and written to `active_skill_priorities.json`.

The desktop can create `skill_priorities_custom.json` as a full editable copy, but any selected JSON may be partial. For an existing `catalog_key`, omitted fields remain inherited from the bundled profile.

## 3. White priority schema

An effective profile has this root shape:

```json
{
  "schema_version": 3,
  "description": "Optional documentation",
  "default_weight": 0.02,
  "skills": {}
}
```

`default_weight` must be finite and non-negative; `skills` is indexed by `catalog_key`. A partial override may omit either because defaults are merged before validation.

A skill entry supports:

```json
{
  "base": 0.5,
  "surface": {"turf": 0.6, "dirt": 0.0},
  "distance": {"mile": 0.7, "medium": 0.8},
  "style": {"pace_chaser": 0.8},
  "profiles": [],
  "notes": "Optional explanation"
}
```

`base` is required in the effective entry. Canonical dimensions are:

- Surface: `turf`, `dirt`;
- Distance: `sprint`, `mile`, `medium`, `long`;
- Style: `front_runner`, `pace_chaser`, `late_surger`, `end_closer`.

Priorities represent **value as a White Spark for parent farming**. They deliberately combine race usefulness, practical acquisition scarcity and lineage differentiation; they are not raw in-race skill-strength ratings. No separate scarcity multiplier is applied later.

The bundled scale is conventionally read as `0` incompatible/useless, `~0.25` weak, `~0.5` useful, `~0.75` strong, `~1.0` top priority and `>1.0` exceptional/build-defining. This is a convention, not another scoring formula.

## 4. Resolving a White profile cell

For a mechanically compatible skill, one `surface × distance × style` cell is resolved in this order:

1. start from `base`;
2. collect matching dimension overrides;
3. with none, keep `base`;
4. with non-zero matches, use their arithmetic mean;
5. if any matching dimension is zero, set the pre-rule value to zero;
6. apply matching `profiles` rules in array order;
7. clamp the final result to `0.0…1.35`.

A mechanical incompatibility inferred from the MDB bypasses this resolver and forces `0.0` with status `mechanical_zero`.

### Exact-profile rules

A rule may match Surface, Distance and/or Style. Each match can be one canonical value or an array. Supported operations are:

| Operation | Effect |
| --- | --- |
| `override` | Replace the current value. |
| `floor` | Raise it to at least `value`. |
| `cap` | Lower it to at most `value`. |
| `multiplier` | Multiply it by `value`. |
| `bonus` | Add `value`. |

Rules are applied in array order. Invalid dimensions, canonical values or operations are rejected by `validate_skill_priorities_config()`.

### Zero values

A zero dimension sets the intermediate value to zero. A subsequent matching
`floor`, `override` or positive `bonus` can raise it. Only MDB-derived mechanical
incompatibility bypasses profile rules and stays absolute. This is the behavior
of `manual_weights._profile_weight()`, not an additional validation rule.

## 5. Stable skill identity

White priorities use `catalog_key`, generated by slugifying the English White Spark name. It is the project-level identity used to reconnect priorities to a newly generated MDB catalogue.

Current MDB identifiers are diagnostics, not persistent configuration keys:

- `factor_group_id` — current White Spark group;
- `factor_ids_by_stars` — current 1★/2★/3★ factor rows;
- `inherit_skill_id` — current inherited skill row.

Because `catalog_key` is name-derived, an upstream English rename can still require explicit migration. A custom key absent from bundled priorities must provide `base` after merge and only affects scoring when the current MDB catalogue contains that key.

## 6. MDB-derived catalogues

Linking/catalogue generation creates:

| File | Role |
| --- | --- |
| `skill_condition_catalog.json` | Current skills, parsed conditions, profile hints and White mappings. |
| `condition_type_catalog.json` | Diagnostic catalogue of condition variables/expressions. |
| `white_skill_weights_template.json` | MDB-derived scaffold with current IDs and `null` weight cells. |
| `race_factor_skill_catalog.json` | Race Spark effects and skills granted as hints. |

`white_skill_weights_template.json` is **not** the White profile selected in the application and is **not** a normal ranking input. Its generated default/matrix cells are `null`; it exposes the current catalogue in a weight-shaped diagnostic scaffold.

Regenerate these files after changing `master.mdb`; do not carry old MDB IDs forward as stable identities.

## 7. Materialised White weights

`generate_manual_skill_weights()` combines the current skill catalogue, `active_skill_priorities.json` and optional course presets.

It writes `manual_skill_weights.json`, the generic White matrix consumed by current scoring. Every current `catalog_key` receives a complete Surface × Distance × Style matrix with:

- resolved `weight`;
- `status` (`manual_priority` or `mechanical_zero`);
- `reasons` explaining the result.

Its metadata records source filenames and SHA-256 hashes for the skill catalogue and priority profile. Regenerate it; do not hand-edit it.

### Race Sparks granting skills

`race_factor_skill_catalog.json` separately identifies Race Sparks that grant a skill hint. Their granted skill is mapped back to the corresponding White relevance by the scoring engine; the catalogue does not turn all Race Sparks into ordinary White Sparks.

## 8. Exact-course overlays

A valid selected course-preset file takes priority over `resources/default_course_overrides.json`; a stale saved path falls back to the current bundled file.

A course entry can contain display metadata, Surface/Distance/(optional Style), race metadata, canonical static conditions and per-`catalog_key` rules. Course skill rules support the same five operations as profile rules and are applied in order over the generic White weight, clamped to `0.0…1.35` after each rule.

Materialisation writes `course_skill_weights.json` with, for each cell:

- `generic_weight` before the course overlay;
- final `weight`;
- ordered `course_adjustments` with reason and before/after values.

Generating this file does not activate every course. The scorer applies an overlay only when its `course_key` is selected; static course conditions are also passed separately to condition-aware scoring.

The course JSON currently has no validator as strict as the White priority schema. Unknown operations fail during generation, but arbitrary custom match metadata is not exhaustively rejected beforehand. Keep custom `match` objects to canonical `surface`, `distance` and `style` keys and inspect the generated result.

## 9. Runtime data flow

The application resolves both `active_*.json` profiles, generates MDB catalogues,
and combines the skill catalogue, active White priorities and optional course
presets into `manual_skill_weights.json` and course overlays. Local parent ranking,
uma.moe ranking and Transfer Helper consume this same materialised White model.

`ULL_SOLVER_WORKERS` and `ULL_G1_RANKING` configure execution, not scoring weights.
They are environment variables, not JSON override fields; see
[solver execution](ARCHITECTURE.md#solver-execution). Keep the ranking mode and
export metadata with a reproduction: the two active profiles alone do not identify
whether GP screening was approximate or exhaustive.

## 10. Legacy Umalator diagnostics

Umalator is no longer an input to normal ranking. `--umalator-batch` remains a separate CLI diagnostic path and expects batch `schema_version: 2`.

It regenerates the MDB catalogues and writes:

- `simulator_skill_weights.json`;
- `manual_review_queue.json`;
- `simulator_skill_weights_summary.csv`;
- optional `course_skill_weights.json`.

These simulator/review/summary artifacts are not consumed by current ranking or Transfer Helper. The legacy pipeline also has different scaling/clamp semantics from the manual model.

Use a separate output directory for Umalator diagnostics: both pipelines can write `course_skill_weights.json`, and separation keeps provenance unambiguous.

## 11. CLI surface

| Flag | Contract |
| --- | --- |
| `--scoring-config FILE` | Complete or partial structural profile; supported legacy fields are migrated before merge. |
| `--skill-priorities FILE` | Complete or partial White priority profile merged over bundled defaults. |
| `--course-overrides FILE` | Replacement course-preset catalogue. |
| `--umalator-batch FILE` | Legacy diagnostic import only; it does not reactivate simulator weights for normal ranking. |

`--rank-parents` and `--transfer-helper` both materialise the two `active_*.json` profiles before dispatching to their engines.

## 12. Editing and debugging rules

1. Change bundled defaults only when behaviour should change for every user.
2. Use structural overrides for model policy; use White priorities for individual White value.
3. Use course rules only for evidence specific to a named course.
4. Never treat generated `manual_skill_weights.json` as permanent editable configuration.
5. Inspect `active_*.json` first when a custom profile appears ignored.
6. Inspect `manual_skill_weights.json` reasons for a suspicious White value.
7. Confirm the selected `course_key` before debugging an exact-course adjustment.
8. Regenerate MDB-derived artifacts after a game-data update.
9. Keep Umalator diagnostics separate from normal scoring outputs.

## 13. Focused validation

```bash
py -m pytest -q \
  tests/test_scoring_config.py \
  tests/test_manual_weights.py \
  tests/test_course_presets.py \
  tests/test_skill_catalog.py \
  tests/test_cli.py
```

For desktop Weights/Search changes, also run the relevant Qt UI tests. If a change alters scoring semantics rather than configuration plumbing, run the engine tests referenced by `SCORING.md`.
