# Collection and training workbench

This fork is the main Windows application. It uses the existing Qt shell and
inheritance engines; the previous Tkinter companion is replaced by the native
**Workbench** page.

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

1. Open **Workbench → Sync**. Select the game's `master.mdb` and
   save the paths. The **Local data** page shares the same selected MDB.
2. Choose **Import dump or JSON** and select your umadump ZIP or individual
   collection/race JSON files. ZIP executables are neither extracted nor run.
3. Browse trainees, supports and veterans in **Collection**. Double-click a
   row to inspect its recorded skills, Sparks, ancestry, locks and other fields.
4. Choose **Use collection for lineage search**. The app creates a private
   veteran snapshot, links it with its own inheritance engine, and opens Search.
5. Select the Ace, future parent and race profile in Search and run an existing
   local or uma.moe search. After a new veteran import, use the collection for
   lineage search again to refresh the snapshot.

The exported veteran snapshot can include a borrowed veteran from an ongoing
career. Collection displays the exported records; the inheritance engine
excludes borrowed entries when ranking your local collection.

Imports retain the previous companion's private state location:
`%LOCALAPPDATA%\UmaWorkbench\workbench.sqlite3`. An existing workbench database
can be reused. Your exports and MDB are read-only inputs. Account IDs prevent
different positive account identities from being combined in that database.

## Daemon exports

Select your existing umadump output folder and start file monitoring. The app
reads new JSON files separately, retries partial writes, and deduplicates
imports. Closing the app stops its file watcher.

The optional **Launch upstream daemon** button runs the separate executable you
selected, using exactly:

```text
umadump.exe --rerun-mode daemon --poll-interval 2
```

The selected output folder is the process working directory. The daemon has its
own console and continues after closing the app; stop it there when finished.
Download and update umadump only from [its upstream releases](https://github.com/Werseter/umadump/releases).
No extractor code or binary is bundled or modified. The upstream author's
account-risk notice continues to apply.

## Team Trials and training goals

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

Training goals record target stats, skills, support decks, parents, scenario,
prerequisites, attempt limits and stop conditions. The editor validates
collection ownership and character conflicts. Dependencies must be complete
before starting a goal. Completion remains manual; career observations are
retained for inspection.

Resources are manual milestones. Balances, shop inventories and verified
earning rates are not present in the supplied dump. Game database browsing
shows raw technical fields and does not claim a validated skill tier list.

The fork's existing inheritance scorer is available. Full TT/CM race
simulation, collection-wide ace selection, automatic lineage career scheduling,
support-deck optimisation and a Concert calculator still need implementation.

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
