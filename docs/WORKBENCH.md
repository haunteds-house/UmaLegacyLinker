# My collection and career plans

This fork is the main Windows application. It uses the existing Qt shell and
inheritance engines; the previous Tkinter companion is replaced by the native
**My collection** page.

## Roster viewer and quick plans

**Roster and collection → Veterans** is a native roster viewer inspired by the
roster/legacy workflow of [Uma.guide](https://uma.guide/roster-viewer/).
It uses your imported collection directly. No website or browser is loaded,
and your roster is not sent to a website. Names come from the selected game
database. Optional portraits download separately and remain cached offline.

Search and sort the illustrated veteran cards, or use **Filters** for sparks,
aptitudes, skills and stats. Open a veteran for stat bars, aptitude grades,
learned skills and illustrated ancestry. Rating and training date help distinguish
copies. **Use as parent 1/2** sends that exact copy to **Lineage planner**.

In **Lineage planner**, choose an owned trainee and up to two owned parents.
It shows the six-member spark totals, starting aptitude changes, character
compatibility and shared G1 bonuses using the existing local inheritance code.
Missing ancestor/race data is labelled incomplete. Starting aptitude is capped
at A; S needs an in-career inheritance roll. The preview lists possible skill
hints from sparks, not all learned parent skills. Parent characters must differ
from each other and from the trainee, including across outfits.

**Find setups / save plan** carries the selected target and exact parent copies
to the career editor. Choices are retained between sessions. Leave the trainee
open, or use **New career plan**, to start from desired skills and aptitudes.
Borrowed veterans remain visible in the roster and cannot fill owned parent
slots. The original **Lineage linker** remains available for deeper inheritance
probabilities, remote searches and race calendars.

The plan editor has three main tabs: **Goal**, **Lineup** and **Suggested setups**.
Practice estimates and training-order controls are optional under **Show practice
comparison and more options**. They retain the limitations documented in
[TRAINING_MODEL.md](TRAINING_MODEL.md).

A complete support deck is **five owned cards plus one borrowed card**.
The borrowed picker includes cards you already own, because a friend's copy
may have better levels or limit breaks. Leaving it open lets the search suggest
a rental from the game database; check that it is available from your friends.
Incomplete collections produce explicitly incomplete lineups.

**My collection**, **Veterans** and every illustrated card picker share the same
**Filters** control. Combine named sparks and minimum stars, current aptitude
grades, skill access, stat minimums, rarity, support type, level and limit breaks.
The optional family spark total includes the veteran and the two immediate
grandparents in its exported lineage. All selected filters must match.

Use **Remove plan** to clear a finished or unwanted plan. **Show removed plans**
and **Restore** recover it, preserving its status and prerequisite links.

## Start from source

Install Python 3.12, open a terminal in the checkout, then run:

```powershell
py -m pip install -r requirements-qt.txt
py qt_app.py
```

`run.bat` launches the same application. Run `build_windows_qt.ps1` on Windows
to build `dist\UmaLegacyLinkerQt\UmaLegacyLinkerQt.exe`. Extract and move the
whole built directory together. Source does not contain a prebuilt executable.

## Import and search

1. From **Home**, choose **1 · Set up and import**. In **Setup**, choose the
   game's `master.mdb` file and click **Save setup**. This loads character,
   support and skill names.
2. Click **Import my collection** and select your umadump ZIP or collection/race
   JSON files. Executables inside a ZIP are neither extracted nor run.
3. Open **My collection**. Switch between **Trainees**, **Support cards** and
   **Veterans**, search by name and choose a sort order. Each item has a portrait or card illustration.
   Click **View** for readable stats, learned skills and inheritance sparks.
   Raw fields are available only on the separate **Technical data** tab.
4. Open **Career plans → Plan a career**. Set a race role, skills and aptitude
   targets, then **Find setups in my collection**. Leave the trainee empty to
   compare owned characters. Suggested setups show pictures, names, parents,
   supports, aptitude changes and skill sources. **Use this setup** fills the
   lineup. You can also save requirements alone or fix choices before searching.
5. Use **Team Trials** to compare recorded runners and skill activations.
   Double-click a runner for its picture, stats and a readable race summary.
   **Find a replacement** keeps the selected division and running style while
   leaving the trainee open, so another character can take that role.
6. Click **Link collection for lineage** above the collection to prepare your
   veterans and open the original **Lineage linker**. Choose a target and open
   results for the illustrated lineage. Repeat after importing new veterans.

The **Home** page explains each workflow. **Lineage linker** and **Link exported
veterans** are always visible in the sidebar. **Show advanced tools** reveals the
transfer and weight editors, plus raw game-data browsing.

Trainees sort by name, rarity or awakening. Supports also sort by level and limit
breaks. Veterans sort by name, rating, date, individual stats and blue/red spark
totals. Each collection remembers its sort order; illustrated choice dialogs
offer the same options. Records with missing values sort last.

Pictures load on demand from GameTora. If a portrait or support image cannot
load, the app tries the corresponding asset in
[Hakuraku](https://github.com/ayaliz/hakuraku/tree/main/public/assets).
Successful images are cached for offline browsing. Missing artwork shows initials;
names and collection actions still work. Disable online downloads in **Setup**
or **Settings**. No artwork or account data is bundled in the executable.

The portrait selectors and expandable runner overview were informed by
Hakuraku's [PortraitSelect](https://github.com/ayaliz/hakuraku/blob/main/src/pages/MultiRacePage/components/PortraitSelect.tsx)
and [CharaCard](https://github.com/ayaliz/hakuraku/blob/main/src/components/RaceDataPresenter/components/CharaList/CharaCard.tsx).
The Qt implementation is native to this fork; Hakuraku's race simulator is not
integrated into this release.

The exported veteran snapshot can include a borrowed veteran from an ongoing
career. Collection displays the exported records; the inheritance engine
excludes borrowed entries when ranking your local collection.

Imports retain the previous companion's private state location:
`%LOCALAPPDATA%\UmaWorkbench\workbench.sqlite3`. An existing workbench database
can be reused. Your exports and MDB are read-only inputs. Account IDs prevent
different positive account identities from being combined in that database.

## Daemon exports

Select your existing umadump output folder and click **Start live updates**. The app
reads new JSON files separately, retries partial writes, and deduplicates
imports. Closing the app stops its file watcher.

The optional **Open umadump** button runs the separate executable you
selected, using exactly:

```text
umadump.exe --rerun-mode daemon --poll-interval 2
```

The selected output folder is the process working directory. The daemon has its
own console and continues after closing the app; stop it there when finished.
Download and update umadump only from [its upstream releases](https://github.com/Werseter/umadump/releases).
No extractor code or binary is bundled or modified. The upstream author's
account-risk notice continues to apply.

## Planning studio

Choose a saved career plan at the top of **Planning studio**, or use **New plan**
to start from skills and aptitudes with the trainee left open.

- **Career forecast:** fills open lineup choices from your collection, runs model
  careers and shows final-stat ranges, skill points and a turn timeline. Edit
  **Career assumptions** for energy policy, events, race rewards and scenario
  additions. **Use in team planning** retains a forecast runner. Changing the plan,
  database or collection invalidates it. **Check recorded careers** reports errors
  only for earlier/later snapshots of the same explicit career identity.
- **Race comparisons:** select owned runners, choose a named course and conditions,
  and optionally add opponent builds. Compare fields or build TT/CM rosters,
  including retained forecast runners. Times and conditional win rates are model
  outputs; point forecasts require recorded-runner calibration in that division.
- **Training projects:** convert a saved plan into an ordered lineage project.
  Existing good parents are reused. Imports complete matching stages, bind exact
  parent copies and update the next useful career. Parent/grandparent plans show
  their required result sparks. Repeating generation reuses the existing project.
- **Skills and cards:** read descriptions, effects, costs, prerequisites and owned
  sources. Rank skills for the current course/runner or compare owned supports and
  trainees for the chosen plan. Unknown model values stay unranked.
- **Resource advice:** compare awakening unlocks for wanted skills. Enter balances
  and minutes per entry, then inspect verified race drops and expected effort.
  Missing acquisition routes remain unknown.
- **Grand Concert:** enter performance balances and mark current offers and wanted
  songs. Plan affordable lesson/song/recovery purchases and reserves. Record them
  locally and update offers after the in-game refresh. Save an assumed purchase
  schedule into a career forecast.

See [Planning models](PLANNING_MODELS.md) for coverage, assumptions and backtests.

## Recorded Team Trials and saved plans

Team Trials reports base points after subtracting exported bonus amounts,
win rates with Wilson intervals, and skill activation rates from decoded
replays. Roster cohorts keep different teams, running styles and divisions
separate. An eligible skill record means the runner owned that skill and the
replay decoded, rather than that the skill's activation conditions were met.

The measured shortlist maximises an approximate lower score bound within the
observed veteran pool. It requires three observations per candidate, one slot
per character and three per division, with optional distinct styles. Its
shortlist spans recorded cohorts; historical comparisons can be confounded.
It does not model teammate interactions or simulate an untrained runner.

Career plans record a race role, skill and aptitude requirements, optional stat
targets, support decks, parents, scenario, prerequisites, attempt limits and
stop conditions. A final trainee is optional. **Edit / find setups** refines an
existing plan without creating a duplicate. Dependencies must be complete
before starting a goal. Manual plans can be completed by the player; generated
projects also check structured criteria against imported veterans. Career observations are
retained for inspection. **Check collection** shows owned veterans meeting the
plan's stored character, stat, skill and aptitude checks for you to review; it
does not infer that a new career satisfied every finish condition.

### How setup search works

The search compares owned trainees, legal local parent pairs and support decks
with distinct characters. Fixed choices stay fixed. It excludes borrowed
veterans from owned parents and reserves exactly one rental slot plus at most
five owned supports. A particular rental can be chosen explicitly or suggested
by the search. The selected division/style supplies aptitude targets; exact distance
also determines its distance group. Individual aptitude targets override the
profile's minimum grade.

The preview explains starting aptitudes using red sparks in each parent branch
and its two immediate grandparents. S requires an in-career inheritance roll.
Skill sources distinguish the trainee's owned awakening level, support hint
pools, possible support-event rewards, and actual skill sparks. A skill merely
learned by a parent is not counted as an inheritance source. Higher skill tiers
cover their positive prerequisite steps. Known surface, distance and style
restrictions are checked; this is not a complete skill-activation simulator.

Ranking prioritises aptitude gaps, missing skill sources and complete lineups,
then the practice model's contribution toward your stat targets when available.
Trainee skill access, growth and levels remain fallback/tie-break measures. Every
legal parent pair is screened, with up to 80 per trainee passed to joint support
comparison. Support coverage keeps a bounded frontier with several support-type
compositions, then evaluates practice output jointly. The shortlist can miss
another setup. Event choices can conflict, and events, hints and inheritance
are possibilities. Stat targets are goals, not predicted outcomes. The original
lineage tool remains available for its deeper affinity, inheritance-probability
and G1 analysis.

### Compare training output

The career editor's **Practice plan** tab uses the same training counts and
conditions to compare different owned decks. Choose an example plan or enter
your own counts. Set the comparison facility level, mood, the share of practices
after friendships are built, later-stage fans and typical energy. Borrowed
support level and limit breaks are explicit; owned cards use their exports.

In **Suggested setups**, **Lineup** retains the illustrated parents and supports.
**Practice estimate** shows five stat bars, skill points from practices and the
remaining targets. The subtotal includes trainee starting stats, support starting
bonuses and expected practice gains under the selected conditions. It excludes
inheritance, race/event rewards, scenario bonuses, shop items and energy/rest
management. It is not a final-career or race forecast.

When available, the same panel shows a completed career for the same trainee and
scenario. Support-card overlap is stated; their levels and other career choices
may differ. This is a reference result, not calibration of the subtotal.
Comparable enabled practice previews in imported career snapshots are checked
against the formula. Unmodelled teammates, character conditions and unsupported
unique effects are excluded. Disagreement disables practice-based sorting for
that search; aptitude and skill-source search remains usable.

Applying and saving a setup retains its comparison. The saved plan labels it as
a snapshot; **Edit / find setups** recalculates after collection or MDB changes.
See [Practice model](TRAINING_MODEL.md) for the assumptions and formula.

## Internal calculators

**Calculators** contains native tools rather than a list of external links:

- **Skill points:** choose named skills, include positive prerequisite steps
  once, mark learned skills and enter the discounted prices shown in game.
  The tool shows the total, remaining points and deficit. A missing price
  remains unknown until entered.
- **Awakening materials:** choose an owned trainee and current/target awakening
  levels. Named material totals come from the MDB. Enter balances and average
  materials per run, including fractional averages, to estimate missing
  materials and runs. Missing upgrade rows are labelled as incomplete.
- **Grand Concert:** select wanted songs and mark bought songs. Enter current
  Dance, Passion, Vocal, Visual and Composure balances to see costs and
  shortages separately. Song effects are shown from the MDB. This is a song
  budget; it does not simulate lesson offers, techniques or an optimal shopping
  sequence.
- **Resource milestones:** retain manual saving targets and progress.

Calculator inputs are saved locally. Balances, current shop offerings and
verified material earning rates are not supplied by the collection dump, so
they remain manual inputs. Game database browsing stays an advanced raw-data
tool. See [Remaining goals](ROADMAP.md) for the next development steps.

## English interface

UI labels, help, logs, reports and CLI instructions are English source strings.
The language selector and bilingual translation catalog have been removed.
Old language preferences are ignored. Previously saved race-condition labels
are migrated to their English equivalents without changing their numeric
conditions or scoring weights. English-only label helpers retain existing
presentation-call compatibility.

## Validation

```powershell
py -m pip install -r requirements-build-qt.txt
py -m pytest -q tests --ignore=tests/test_qt_runtime.py
py tests/check_english.py
```

The release build runs existing Qt smoke tests in separate processes. Linux
offscreen checks verify widget construction and data workflows; native Windows
daemon execution and the Windows executable require a Windows test.
