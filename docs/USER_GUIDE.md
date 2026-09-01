# Uma Legacy Linker user guide

This guide covers the complete desktop workflow. For a short installation path and project overview, start with the [README](../README.md).

## 1. Prepare the required data

Uma Legacy Linker needs two inputs generated from the same current game version:

| Input | Purpose |
| --- | --- |
| `master.mdb` | Resolves characters, costumes, skills, races, affinities and course data |
| `data.json` or `trained_chara_data.json` | Provides the local veteran collection and its frozen lineages |

The game database is normally detected from common Windows and Steam locations. If detection fails, select it manually on the Data page.

### Collection exporters

The application does not include a game-memory reader. It supports exports created by:

- [UmaExtractor](https://github.com/xancia/UmaExtractor), which writes `data.json`;
- [umadump](https://github.com/Werseter/umadump), which writes `trained_chara_data.json`.

You can select an existing export or configure either tool under **Extractor** and select **Extract my collection**. The launcher recognises the backend from its filename; umadump is invoked once from the selected output directory.

umadump currently leaves `succession_trained_chara_id_1/2` at zero. As a result, Transfer Helper cannot populate the informational “referenced by” column from that export. Scoring remains available because the complete frozen parent and grandparent Sparks are present in `succession_chara_array`.

These extractors are independent projects with their own requirements, licences and warnings. Tools that read a running game process are used at your own discretion.

## 2. Link the collection

On **Data**:

1. select the current `master.mdb`;
2. select the collection export;
3. choose an output directory;
4. select **Link an existing export**.

The linker resolves:

- costume and character identities;
- Blue, Pink, Green, White and Race Sparks;
- Spark stars and granted skills;
- learned skills and G1 victories;
- parents, grandparents and available local training identifiers.

It writes an enriched `veterans_legacy_linked.json` and the supporting catalogues to the output directory. The original database and collection export are read-only inputs.

The application fingerprints the source files. If either input changes, the existing linked result becomes stale and must be regenerated. **Relink anyway** is available for recovery and diagnostics when a forced rebuild is needed.

## 3. Configure the shared Search context

Search keeps one live context for local and online calculations:

- target Ace;
- parent being produced;
- surface, distance and running style;
- exact racecourse, course layout and conditions when relevant;
- structural scoring profile;
- White Skill priority profile.

Rotation is derived from the selected MDB course layout. The context rail can be collapsed without hiding its effective values: each section header retains its current summary and modified state.

The result area contains five persistent families:

1. final parent pairs;
2. individual parent candidates;
3. future grandparents;
4. uma.moe remote parents;
5. uma.moe remote GPs.

Each family keeps its latest result independently. Changing an input marks only the result families that consume that input as stale.

## 4. Run local lineage searches

### Final parent pairs

Use this when both direct parents are selected from the linked local collection. Every candidate is evaluated as a complete six-member lineage: two parents and four grandparents.

The ranking combines:

- initial aptitude ranks and estimated `P(A)` / `P(S)`;
- individual modern affinity across the lineage;
- distance-aware Blue Spark value;
- probability-aware White Spark inheritance;
- G1 compatibility and course-specific Green Skills.

### Individual parents

Use this to identify strong direct-parent branches before committing to a full pair. A parent is presented with its own two grandparents and scored in the active Ace/race context.

### Future grandparents

Use this while producing a new parent. Generic future-GP ranking deliberately uses a pre-production model because the final lineage does not exist yet.

An optional fixed opposing branch makes the calculation exact: every candidate GP pair is inserted under the future parent and evaluated against that complete known branch with the final-pair engine. Unknown Sparks belonging to the future parent itself remain empty rather than being invented.

## 5. Search public parents through uma.moe

Configure the API URL and optional remembered API key under **Settings**. Search options remain on the Search context rail and are divided into:

- constraints shared by both remote modes;
- parent-search pairing and pool settings;
- future-GP pairing, fixed-local and opposing-branch settings.

Two modes are available:

- a remote final parent paired with a local parent;
- a remote grandparent paired with a local GP.

Friend IDs can be copied from the result table. Always confirm that a Friend ID is still active before beginning a career.

### Retrieval budget

Online retrieval is capped at 2,000 candidates per search. Final-parent discovery distributes that budget between Distance, target-surface when needed, and broad White-preferred cohorts. Results are merged and deduplicated before exact local × remote scoring.

These cohorts guide discovery; they are not a substitute for the local scoring engine. Explicit hard filters are applied to every cohort and revalidated after normalisation.

If the known local lineage already provides the required target-surface readiness, the automatic surface cohort is omitted and its budget is returned to the remaining discovery pools. Contextual future-GP searches similarly subtract known coverage from the fixed opposing branch and locked local GP before allocating the retrieval budget.

## 6. Read and compare results

The table gives the ranking overview. The detail pane explains the selected candidate through:

- score and affinity;
- aptitude targets, starting ranks and `P(S)`;
- direct and inherited Spark contribution;
- White inheritance probability across the configured Inspiration Events;
- shared and one-sided G1 victories;
- an executable G1 schedule when enough MDB data is available.

Every parent, pair and grandparent result can be opened in the top-down lineage inspector. Artwork and skill icons are visual aids only; identifiers, text labels and score diagnostics remain available if an asset cannot be downloaded.

Search can compare two candidates from the same result family. The comparison preserves both original diagnostics and reports numeric deltas as `right - left`. Cross-family comparisons are rejected rather than guessed.

### Result history and freshness

The application retains the current and immediately previous main result for each supported Search/Transfer output. History entries display their source file, generation time, schema and available input fingerprints.

Result states are explicit:

- **current** — generated from the effective inputs now selected;
- **loaded** — opened from disk without claiming current-input equivalence;
- **stale** — a consumed input changed after the calculation;
- **running** or **empty** — no completed current result is available.

## 7. Use the G1 planner

The planner builds a one-race-per-turn schedule across the Junior, Classic and Senior years.

- A race shared by both selected branches can create two future `+3` affinity links (`+6`).
- A one-sided race creates one `+3` link.
- Fixed character objectives are locked into the standard schedule.
- **Schedule for Trackblazer** shows the affinity-only variant without those objectives.
- Objective conflicts and unavoidable streaks of four or more races remain visible as risks instead of being silently removed.

For future-grandparent searches, a race keeps its full projected value only if the future parent's configured Independent Training win chance reaches the cutoff after streak penalties.

## 8. Use Transfer Helper safely

Transfer Helper analyses duplicate veterans but performs no game action. It cannot edit the collection export or delete a veteran.

The permanent baseline covers Turf Sprint/Mile/Medium/Long and Dirt Sprint/Mile/Medium across Front, Pace and Backline profiles. The default fast mode restricts analysis to Aces with natural B or better in surface, distance and style. Optional Champion Meeting, Team Trials and generic profiles can add evidence without replacing the permanent baseline.

The analyser builds a small same-costume portfolio that remains within the configured score tolerance of the best copy in each competitive context. It also protects direct 3-star aptitude Sparks, valuable White Sparks, repeated or difficult skills and configured Spark packages.

### Verdicts

| Verdict | Meaning |
| --- | --- |
| **Protected** | The copy is locked in game or carries a memo |
| **Keep** | The copy is required by the retained collection portfolio |
| **Strictly safe transfer** | One same-costume, same-Unique replacement dominates every viable checked context and preserves protected heritage |
| **Recommended transfer** | The copy is redundant at collection level, potentially covered by different retained copies in different contexts |
| **Review** | Available evidence is incomplete or does not justify a stronger verdict |

Only exhaustive mode can emit **Strictly safe transfer**. Fast-mode redundancies remain recommendations.

The detail view exposes the relevant contexts, score envelopes, strict replacement when one exists, retained cover per context and complete Spark comparison. Alternate costumes are never treated as interchangeable.

## 9. Edit weights without replacing defaults

The Weights page stores only user overrides. Bundled defaults remain under `resources/` and new settings can be introduced by later releases without replacing the entire user profile.

Useful adjustments include:

- increasing the Long Stamina preference;
- reducing Blue Spark influence for Sprint;
- changing the Distance-S utility curve;
- adjusting the thresholds that compensate for a Distance-B start;
- changing target-surface rank requirements for low-natural-aptitude Aces.

Structural scoring and White Skill priorities are separate inputs:

- `parent_scoring_overrides.json` contains structural scoring overrides;
- `skill_priorities_custom.json` contains per-skill White priorities;
- `active_parent_scoring.json` and `active_skill_priorities.json` record the effective profiles used by a run.

See [White Skill priorities](SKILL_PRIORITIES.md) for the accepted full and partial JSON formats. The formulas and exact workflow differences are documented in [Scoring](SCORING.md).

## 10. Artwork, cache and offline behaviour

The lineage inspector can request costume artwork, White Skill icons and G1 banners from GameTora. Images are not bundled with the source or Windows release.

Downloaded files are stored in a bounded per-user cache. They remain available offline, and online artwork loading can be disabled or the cache cleared from the inspector. Missing artwork falls back to a generated card and does not affect scoring.

## 11. Configuration and secrets

General preferences are stored in:

```text
%APPDATA%\UmaLegacyLinker\config.json
```

On Windows, a remembered uma.moe API key is encrypted for the current account with DPAPI and stored separately under `%APPDATA%\UmaLegacyLinker`. It is never written to `config.json`. The `UMA_MOE_API_KEY` environment variable takes priority when set.

On Linux and macOS, the optional key file is stored under `${XDG_CONFIG_HOME:-~/.config}/UmaLegacyLinker/uma_moe_api_key.dat` with restricted directory and file permissions, but without platform encryption.

## 12. Troubleshooting

### Search says the linked data is stale

Confirm that `master.mdb` and the collection export belong to the same current game version, then return to Data and link again.

### An online search returns no candidate

Check the uma.moe API URL/key, network access and hard filters. A valid empty cohort is different from an API failure; the application reports the corresponding diagnostic in the log.

### A result is marked loaded or stale

Loaded means the result came from disk. Stale means at least one effective input used by that result family has changed. Re-run the visible result family to obtain a current result.

### Artwork is missing

Confirm that online artwork is enabled and that GameTora is reachable. Artwork availability never changes the underlying result.

### A Windows build will not start from inside the ZIP

Extract the complete `UmaLegacyLinkerQt-win64.zip` first. The application is a PyInstaller `onedir` bundle and requires its adjacent runtime files.

## Related documentation

- [Scoring model](SCORING.md)
- [White Skill priority format](SKILL_PRIORITIES.md)
- [Generated/manual White weights](WEIGHTS_FORMAT.md)
- [Desktop architecture and visual QA](QT_UI.md)
- [Performance and process isolation](PERFORMANCE.md)
- [Third-party tools and services](THIRD_PARTY.md)
