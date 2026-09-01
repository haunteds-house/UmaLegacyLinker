<div align="center">

# Uma Legacy Linker

**Build and compare inheritance lineages for Umamusume: Pretty Derby.**

[![Latest release](https://img.shields.io/github/v/release/Rom1foucher/UmaLegacyLinker?display_name=tag&sort=semver)](https://github.com/Rom1foucher/UmaLegacyLinker/releases/latest)
[![Windows release](https://github.com/Rom1foucher/UmaLegacyLinker/actions/workflows/release-windows.yml/badge.svg)](https://github.com/Rom1foucher/UmaLegacyLinker/actions/workflows/release-windows.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)

[Download for Windows](https://github.com/Rom1foucher/UmaLegacyLinker/releases/latest) · [User guide](docs/USER_GUIDE.md) · [Scoring model](docs/SCORING.md) · [Changelog](CHANGELOG.md)

</div>

Uma Legacy Linker turns a local veteran export and the current `master.mdb` into actionable parent, grandparent and complete six-member lineage rankings. It combines local analysis with optional [uma.moe](https://uma.moe/) searches, then explains every result through Sparks, aptitude readiness, affinity and G1 compatibility.

> Independent community project. Not affiliated with or endorsed by Cygames.

## Why use it?

| Workflow | What it answers |
| --- | --- |
| **Lineage Search** | Which local or local × remote parent pair best fits this Ace and race? |
| **Future grandparents** | Which veterans should be used to produce the next parent? |
| **Lineage inspector** | Where do the useful Sparks, probabilities and G1 links come from? |
| **G1 planner** | Which compatible races can be scheduled across the three training years? |
| **Transfer Helper** | Which duplicate veterans are worth keeping, redundant or safe to review? |
| **Weights** | How should the scoring profile reflect a distance, style or personal priority? |

The desktop application includes French and English interfaces, sortable rankings, side-by-side comparisons, retained result history, detailed JSON/CSV exports and process-isolated calculations that keep Qt outside the scoring process.

## Install on Windows

The packaged Windows application is the recommended way to use Uma Legacy Linker. It includes Python, PySide6, PyYAML and the default scoring profiles.

1. Open the [latest release](https://github.com/Rom1foucher/UmaLegacyLinker/releases/latest).
2. Download `UmaLegacyLinkerQt-win64.zip` and, optionally, its `.sha256` file.
3. Extract the **whole ZIP** to a normal folder.
4. Run `UmaLegacyLinkerQt.exe` from the extracted directory.

The executable is not currently Authenticode-signed, so Windows SmartScreen may display a warning on first launch. The archive checksum can be verified with:

```powershell
Get-FileHash .\UmaLegacyLinkerQt-win64.zip -Algorithm SHA256
Get-Content .\UmaLegacyLinkerQt-win64.zip.sha256
```

The two SHA-256 values must match.

## Run from source

Requirements:

- Python 3.10 or newer;
- Windows as the primary supported platform;
- a current Umamusume `master.mdb`;
- a collection export from UmaExtractor or umadump.

```powershell
git clone https://github.com/Rom1foucher/UmaLegacyLinker.git
cd UmaLegacyLinker
py -m pip install -r requirements-qt.txt
py qt_app.py
```

On Windows, `run.bat` launches the same interface after the dependencies have been installed.

## First run

Open **Data** and configure:

1. **Current game database** — select `master.mdb` if it was not detected automatically.
2. **Exported collection** — select `data.json` or `trained_chara_data.json`.
3. **Output directory** — keep generated rankings and diagnostics separate from the source export.
4. Select **Link an existing export**.

The original collection export is never modified. Linking creates `veterans_legacy_linked.json` and the catalogues required by Search and Transfer Helper in the selected output directory.

You can also configure UmaExtractor or umadump and use **Extract my collection**. These tools are separate projects and are not bundled with Uma Legacy Linker.

## Main workflows

### Search a lineage

The shared Search context contains the target Ace, parent to produce, race profile, course conditions and scoring files. From the result tabs, run only the calculation you need:

- final parent pairs;
- individual parent branches;
- future grandparents;
- local parent × remote parent through uma.moe;
- local GP × remote GP through uma.moe.

Every result can be inspected as a top-down lineage. The detail view exposes aptitude targets, `P(S)`, modern affinity, Spark sources, White inheritance probabilities and G1 planning without introducing a second scoring formula.

Online retrieval is capped at 2,000 candidates per search. An uma.moe API key can be entered under **Settings** and remembered locally.

### Review duplicate veterans

Transfer Helper evaluates each local veteran across a permanent set of Turf and Dirt profiles, with optional Champion Meeting, Team Trials and generic contexts. Its verdicts distinguish protected copies, required portfolio members, strict replacements, collection-level redundancies and cases requiring manual review.

It is an analysis tool only: it never edits the export and cannot transfer or delete a veteran in game. Fast mode is recommended for routine use; only the slower exhaustive mode can emit **Strictly safe transfer**.

### Adjust scoring

The Weights page edits minimal overrides on top of the bundled defaults. It includes searchable categories, bilingual explanations, purpose-built controls and live distribution previews for normalised scoring groups.

The structural scoring profile and per-skill White priorities remain separate. See [White Skill priorities](docs/SKILL_PRIORITIES.md) for partial override examples and merge rules.

For the complete operational walkthrough, result states, extraction limitations and troubleshooting guidance, read the [user guide](docs/USER_GUIDE.md).

## Data and network use

| Data | Behaviour |
| --- | --- |
| Collection export and `master.mdb` | Read and processed locally; originals are not modified |
| Generated rankings | Written to the selected output directory |
| uma.moe | Used only for requested remote-parent searches |
| GameTora artwork | Downloaded on demand by the lineage view; optional and locally cached |
| API key | Protected with Windows DPAPI when remembered on Windows; never stored in `config.json` |

No game assets, executable extractors, `master.mdb`, collection exports or uma.moe datasets are distributed with this project. Cached artwork can be disabled or cleared from the lineage inspector.

## Output files

| File | Contents |
| --- | --- |
| `veterans_legacy_linked.json` | Collection resolved against the current MDB |
| `legacy_parent_rankings.json` | Complete local parent, pair and future-GP results |
| `legacy_parent_pairs.csv` | Compact final-pair ranking |
| `legacy_future_grandparents.csv` | Compact future-grandparent ranking |
| `transfer_helper_report.json` | Complete portfolio evidence and replacement analysis |
| `transfer_helper_candidates.csv` | Compact Transfer Helper verdict list |
| `uma_moe_parent_pairs.json` | Local-parent × remote-parent results |
| `uma_moe_grandparent_pairs.json` | Local-GP × remote-GP results |

The application also writes catalogues, readable diagnostics, raw online responses and one previous generation of its principal Search and Transfer Helper results.

## Command line

The desktop interface is the recommended workflow. The same Qt-free services are available for local linking, catalogue generation, lineage ranking and Transfer Helper automation:

```powershell
py cli.py --help
```

## Project layout

| Path | Purpose |
| --- | --- |
| `qt_app.py` | Desktop entry point |
| `cli.py` | Headless entry point |
| `uma_legacy_linker/` | Qt-free application services, data linking and scoring engines |
| `ui_qt/` | PySide6 shell, pages, models and visualisation components |
| `resources/` | Bundled default profiles and SVG interface icons |
| `tests/` | Engine, UI, accessibility, release and i18n checks |
| `docs/` | User, scoring, architecture and release documentation |

## Development and Windows build

Install the complete build environment:

```powershell
py -m pip install -r requirements-build-qt.txt
```

Run the portable test gate and translation audit:

```powershell
py -m pytest -q tests --ignore=tests/test_qt_runtime.py
py tests/check_i18n.py
```

Build the verified Windows bundle:

```powershell
.\build_windows_qt.ps1 -RunLayoutAudit
```

The script runs the portable suite, executes every Qt runtime smoke test in a fresh process, performs the bilingual layout audit, builds the PyInstaller `onedir` bundle, then creates the ZIP and checksum. See [Releasing](docs/RELEASING.md) for the publication checklist.

## Documentation

- [User guide](docs/USER_GUIDE.md) — setup, workflows, result states and troubleshooting;
- [Scoring model](docs/SCORING.md) — formulas, probabilities and workflow-specific scoring;
- [White Skill priorities](docs/SKILL_PRIORITIES.md) — complete and partial priority profiles;
- [Qt UI](docs/QT_UI.md) — desktop architecture, visual QA and packaging;
- [Performance](docs/PERFORMANCE.md) — process isolation and cancellation design;
- [Third-party components](docs/THIRD_PARTY.md) — tools, services, icons and licences;
- [Releasing](docs/RELEASING.md) — Windows build, verification and GitHub release procedure;
- [Changelog](CHANGELOG.md) — release history and current unreleased work.

## Project status

Uma Legacy Linker is a community tool under active development. Rankings are decision support, not guarantees: inheritance remains probabilistic, remote Friend IDs can expire and community-derived game mechanics may evolve after game updates.

Umamusume: Pretty Derby and related assets belong to their respective rights holders.
