# Qt desktop UI

The PySide6 interface is the desktop application. It shares the engines, configuration and output formats used by the CLI (`cli.py`).

## Included

- a dashboard showing the current MDB, local collection and latest ranking state;
- shared paths and language preference across sessions;
- extraction through UmaExtractor or umadump, linking of `data.json` or
  `trained_chara_data.json`, and skill-catalogue generation;
- searchable Ace, target-parent, course and racecourse selection with contains-based autocomplete;
- course presets and static race conditions, edited in place rather than in a modal editor;
- one Search workspace with a persistent Ace, target-parent, race, course and scoring context, held in a collapsible context rail beside a full-height result area;
- rail sections whose headers keep stating their effective values, modified state and reset action, so a collapsed section never hides the settings a calculation will use;
- persisted expert display state: rail-section expansion, active result family,
  detail visibility, splitter positions, result sorting, column order/width and
  optional-column visibility;
- clearly separated local and uma.moe source cards feeding one shared result area;
- independent background actions for final pairs, parent branches and future grandparents, so a local request computes only the requested result family;
- sortable final-pair, parent-branch and future-grandparent tables;
- tabular OpenType figures in every dense numeric result table and in the
  scoring-curve editor, preserving the application typeface while aligning
  digits vertically;
- an embedded diagnostics pane instead of separate result windows;
- a top-down visual lineage inspector for every local and uma.moe ranking: final pairs, parent branches, future-grandparent candidates and grandparent pairs;
- game-inspired rank emblems, roomier score/P(S) cards and clearly separated aptitude/readiness/affinity diagnostics;
- two-column Spark cards that explicitly fill the Qt rich-text viewport, keeping stars, names and engine probabilities readable even in the narrow result pane;
- branch summaries that total each final parent with its two grandparents, condense duplicate Blue/Pink/White Sparks, keep Green sources distinct and mark Sparks carried by the direct parent;
- costume-aware trainee artwork and White Skill icons loaded asynchronously through a persistent, optional local cache;
- explicit shared/local/remote G1 diagnostics and a themed three-year optimal calendar for both parent and grandparent pairs, with `+6`/`+3` link values, mandatory objective locks, an objective-free Trackblazer switch and cached GameTora race banners;
- high-contrast Spark chips ordered Blue → Pink → Green → White, with visible semantic labels independent of colour, resolved skill icons, the existing full-run White inheritance probability and priority emphasis for the three strongest White score contributions;
- History menus for Search rankings and Transfer Helper reports, exposing the
  current and immediately previous retained generation with file, timestamp,
  schema, source and available input SHA-256 provenance;
- side-by-side comparison of two candidates in one Search family, a Transfer
  Helper veteran against full retained coverage records, and stable identities
  before/after a recalculation, with original diagnostics, provenance and
  numeric right-minus-left deltas;
- export of a selected final pair to the uma.moe Lineage Planner format;
- live and imported uma.moe parent/grandparent searches, with shared retrieval constraints and per-search pairing, pool, fetch and import settings edited in the context rail, plus costume filters and Friend ID copy;
- stable uma.moe API URL/key configuration under Settings, separate from scoring weights and per-search filters;
- Transfer Helper with visible Fast/Exhaustive (slow), upcoming-CM, Team Trials and generic-profile
  controls, portfolio verdict/search filters, lock and memo protection, and embedded portfolio or
  strict-replacement diagnostics, plus explicit empty/running/current/loaded/stale report state and
  a visible generation timestamp; secondary rank/reference/technical columns
  start hidden but remain available from the persisted header menu;
- a two-pane scoring-profile editor with search, 51 gameplay subcategories, plain-language help for every setting, hover summaries and visible draft/default states;
- unambiguous probability, threshold, multiplier and 100%-budget controls, including live donut charts for all nine genuinely normalised scoring groups;
- live shared White Skill priority-file management across Search and Weights;
- actionable error dialogs that preserve the technical diagnostic and add one
  concrete recovery step, while full worker tracebacks remain in the log;
- live French/English switching;
- process-isolated local, uma.moe and Transfer Helper calculations, with Qt
  confined to the GUI process and a lightweight worker thread relaying typed
  IPC messages;
- cooperative cancellation from the status bar, with bounded termination when
  a backend cannot reach its next checkpoint;
- vendored, theme-tinted SVG icons for primary navigation, the Search context-rail
  toggle and the lineage inspector's affinity tag, replacing bare Unicode glyphs
  whose rendering depended on the host's font-fallback chain;
- one named point-size scale shared by the application stylesheet, painted
  charts/canvases and rich-text diagnostics, with a 10 pt body base and an 8 pt
  minimum for dense labels;
- independent 75–200% lineage and G1-calendar zoom, remembered per view and
  available through visible controls, Ctrl+wheel and Ctrl+0;
- lineage Spark hover targets that remain at least 24 device-independent pixels
  high at every supported zoom level, without overlapping invisible hitboxes;
- explicit bilingual accessible names, descriptions and label relationships
  for configuration controls, composite path pickers, result tables,
  diagnostics and dense custom views;
- one local-veteran identity (`Card name · evaluation score`) shared by
  selectors, tables and diagnostics; technical training IDs are hidden by
  default and retained only for tooltips, joins and machine-readable exports;
- a Transfer Helper diagnostic with explicit parent/future-GP evidence counts,
  complete veteran-versus-retained Spark comparison, successful and failed
  heritage protections, full strict-replacement aggregates and a role-by-role
  table of candidate-versus-retained score deltas for strict and collective
  verdicts, in a pane kept at the documented 520 px readability floor;
- a fixed opposing-parent context and offline local GP-pair ranking in the uma.moe search.

The lineage view retains the compact identities, Sparks and skill IDs required for rendering, then displays the White full-run probability already emitted by the scoring engine for its configured Inspiration Events. G1 planning likewise renders the engine's pair comparison: a race carried by both selected legacies is worth two future `+3` links, while a one-sided race is worth one. In future-GP mode, the engine also emits the target parent's Independent Training aptitude profile, base/effective win chances and binary cutoff result; the UI only presents those values. The solver maximises obtainable affinity with one race per turn, applies the documented penalties from the third consecutive race onward, then minimises risky streaks; fixed target-character objectives constrain the standard variant, while Trackblazer switches to a precomputed objective-free variant.

## Visual QA

The Windows workflow renders every page, the Search workspace with its context rail expanded, collapsed, focused on each uma.moe search mode and on each result family, the embedded local and remote result panes, and all four lineage variants in French and English at 1120×720, 1366×768 and 1600×900. Its fixtures deliberately include long names, dense White summaries and all aptitude ranks. It fails on clipped button/label text, hidden horizontal overflow or a root rich-text table that collapses into a narrow strip, and currently covers 132 screenshots plus `layout-report.json`. The overflow check measures only text that Qt actually paints, so accessible labels retained by icon-only tool buttons do not create false failures. Unit tests also enforce readable text contrast, 3:1 structural and Spark-boundary contrast, non-colour Spark labels, English coverage for visible Qt copy and safe result-pane construction before table sorting emits model callbacks. The Windows runtime matrix additionally checks that semantic names and visible-label relationships remain complete after switching between French and English.

## Artwork and offline behaviour

The application does not bundle or redistribute game artwork. The lineage inspector derives costume-aware trainee, resolved White Skill icon and G1 banner URLs from current MDB IDs, downloads only assets needed by the opened view and caches them under Qt's per-user application cache directory. The exact directory is shown as a tooltip on the cache status. Cached artwork remains usable offline; online loading can be disabled and the cache can be cleared from the inspector. The lineage and G1 planning views are fixed logical canvases inside scroll areas. Their explicit user zoom changes canvas geometry instead of stretching it to the dialog; low-resolution race banners remain capped at native bitmap resolution even when the surrounding calendar is enlarged.

The asset catalogue contains validated URL builders for trainee artwork, support-card artwork and skill icons. Trainee and skill assets are now used by the lineage inspector; support-card integration remains deliberately outside this project step. The shared asynchronous loader, strict HTTPS host allowlist, placeholders and cache are reusable by later views.

## Run from source

```powershell
py -m pip install -r requirements-qt.txt
py qt_app.py
```

## Windows build

```powershell
.\build_windows_qt.ps1
```

The build is an `onedir` bundle packaged as `dist\UmaLegacyLinkerQt-win64.zip`. After extracting the complete directory, run `UmaLegacyLinkerQt.exe`. Python is not required on the destination PC.

The **Windows release** GitHub Actions workflow runs the tests and visual audit, builds the bundle, and attaches the ZIP plus its SHA-256 checksum to the release on every `v*` tag.

## Project layout

| Path | Purpose |
| --- | --- |
| `qt_app.py` | Qt entry point |
| `backend_process.py` | Qt-free process-task and typed IPC boundary |
| `output_history.py` | atomic output replacement, one retained predecessor and shared provenance contract |
| `result_comparison.py` | Qt-free stable identities, datasets and metric definitions for comparisons |
| `cli.py` | Headless CLI sharing the same engines |
| `veteran_identity.py` | canonical local-veteran labels, score formatting and collision handling |
| `application.py` | GUI-independent configuration and workflow orchestration |
| `ui_qt/accessibility.py` | shared explicit name, description and visible-label bindings for Qt assistive APIs |
| `ui_qt/main_window.py` | application shell, navigation, progress and log drawer |
| `ui_qt/workers.py` | thread worker and backend-process IPC supervisor |
| `ui_qt/pages_home_data.py` | dashboard and local linking workflow |
| `ui_qt/pages_search.py` | unified context rail, adaptive toolbar and result families |
| `ui_qt/result_families.py` | one tab and one persistent pane per result family, with per-family freshness and provenance |
| `ui_qt/provenance.py` | shared revision labels and provenance presentation for retained outputs |
| `ui_qt/comparison_dialog.py` | shared two-column diagnostics and delta table for Search and Transfer Helper |
| `ui_qt/result_panes.py` | result tables and diagnostics shared by every family |
| `ui_qt/online_options.py` | shared uma.moe retrieval constraints and per-search strategy sections |
| `ui_qt/pages_optimizer.py` | reusable local result explorer and diagnostics |
| `ui_qt/pages_online.py` | reusable uma.moe result explorer and costume-filter dialog |
| `ui_qt/pages_transfer.py` | Transfer Helper analysis and diagnostics |
| `ui_qt/pages_weights.py` | scoring and White Skill priority editor |
| `ui_qt/pages_tools.py` | Settings: uma.moe integration |
| `ui_qt/models.py` | sortable Qt table model |
| `ui_qt/presentation.py` | safe HTML diagnostics rendering |
| `ui_qt/asset_catalog.py` | validated GameTora trainee, support, skill and race-banner asset URLs |
| `ui_qt/icon_catalog.py` | vendored SVG icons, tinted for the active theme at paint time |
| `ui_qt/icons/` | vendored Lucide SVG sources (see [`THIRD_PARTY.md`](THIRD_PARTY.md)) |
| `ui_qt/typography.py` | shared named point-size scale for QSS, painted views and rich text |
| `ui_qt/table_typography.py` | OpenType tabular-figure policy for dense numeric Qt tables |
| `ui_qt/zoom.py` | shared canvas zoom bounds, stepping, formatting and persistence keys |
| `ui_qt/view_state.py` | versioned Qt splitter/header/disclosure persistence and column chooser |
| `ui_qt/image_assets.py` | asynchronous loading, allowlist and persistent disk cache |
| `ui_qt/lineage_nodes.py` | compatibility layer for current and older pair, branch and grandparent-result schemas |
| `ui_qt/lineage_view.py` | top-down lineage inspector, G1 planning calendar, rich Spark cards and artwork controls |
| `ui_qt/weight_controls.py` | scoring taxonomy, normalised groups and slider semantics |
| `ui_qt/weight_help.py` | bilingual purpose, impact, scope and scale guidance for every weight |
| `ui_qt/distribution_chart.py` | dependency-free live donut chart for normalised weight groups |
| `ui_qt/layout_audit.py` | offscreen screenshots and overflow checks |
| `tests/` | engine, UI, release, documentation and bilingual-coverage tests |

The reasoning and comparable-app patterns behind the weights redesign are recorded in [`WEIGHTS_UI_DESIGN.md`](WEIGHTS_UI_DESIGN.md); the Search workspace redesign and its remaining phases are recorded in [`SEARCH_UI_DESIGN.md`](SEARCH_UI_DESIGN.md).

## Packaging note

PySide6 is the official Qt for Python binding and is available under LGPLv3/GPLv3 or a commercial Qt licence. The build uses an extracted `onedir` layout so the Qt runtime remains made of separate dynamically loaded libraries. Review [`THIRD_PARTY.md`](THIRD_PARTY.md) and the licence metadata included with the binary bundle before publishing a release.
