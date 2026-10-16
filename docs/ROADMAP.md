# Collection planner goals

Version 1.14.0 supplies native workflows for the six planning goals. The original
lineage linker, English roster, collection filters/sorting, requirements-first
plans, five-owned/one-borrowed support rule and reversible plan removal remain.

| Goal | Implemented workflow | Evidence and limits |
| --- | --- | --- |
| Career planning | Turn-based forecasts with energy, recovery, board choices, bond, races, events, inheritance, scenario assumptions and skill costs | Seeded outcome ranges, turn timeline and same-career backtests; policy and reward assumptions remain explicit |
| TT/CM optimization | Course conditions, editable opponents, race comparisons, team assignment, joint-field refinement and planned runners | Point calibration requires recorded runner evidence; unsupported skill conditions/effects stay unranked |
| Multi-generation projects | Generated grandparent/parent/runner DAGs, result reuse, spark targets, attempt tracking, result matching, exact-parent binding and next ready career | Structured checks drive progress; arbitrary prose stop rules are not silently machine-verified |
| Internal reference tools | Readable skill/card profiles, effects/prerequisites, owned sources and contextual skill/support/trainee comparisons | Values describe the selected course/model; single cards differ from interacting decks |
| Resource advice | Awakening priorities, balances, verified drop routes and expected run/time comparisons | Only exposed MDB routes are used; missing routes remain unknown |
| Grand Concert | Current offers, lesson/song/recovery shopping, wanted-song reserves, local purchase recording and career integration | Bounded current-offer search; future availability and undecoded bonuses are not invented |

## Validation and maintenance

See [PLANNING_MODELS.md](PLANNING_MODELS.md) for coverage and assumptions.
Functional tools do not establish that every game mechanic is reproduced or
that outcome probabilities are calibrated to a player's decisions. Available
backtests and missing comparable data are reported explicitly. Further accuracy
and usability work should follow observed discrepancies and user feedback.

Windows packaging runs backend and isolated Qt checks, layout audits, a packaged
native planning check and a no-browser-runtime check. Game data, exports and the
external extractor are not bundled. The executable remains unsigned; a specific
antivirus diagnosis still needs the threat name and affected file.
