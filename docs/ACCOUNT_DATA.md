# Account data foundation

The long-term optimizer needs one local source of truth for the player's collection, race history and training projects. `account.sqlite3` is that source. It is separate from generated Legacy Linker output files and is stored under the application's local data directory by default.

## Source boundary

Uma Legacy Linker does not attach to the game process and does not modify umadump. The account importer only reads files written by an independently installed/running official umadump release.

The first importer supports the current umadump 2.x output shapes used by the supplied real-world sample:

- `card_data.json`
- `support_card_data.json`
- `trained_chara_data.json`
- `race_replays/team_stadium/*.json`
- `race_replays/single_race/*.json`
- `career_data/*/manifest.json`
- `career_data/*/turns/turn_###_###.json`
- `career_data/*/events.json`
- `career_data/*/log.json`
- `career_data/*/veteran.json` when present
- `trophy_data.json` / `trophy_data_limited.json`
- `event_data.json`
- `honor_data.json`
- `talk_gallery_data.json`

Unknown files are left untouched and are not treated as errors.

## Persistence model

Current collection state is normalized into dedicated tables for owned trainee cards, support cards and veterans. Veterans that disappear from a later collection export are retained as inactive historical rows so race/career history can continue to refer to them.

Large observations such as Team Stadium captures and career snapshots are stored as compressed JSON blobs. The original source path, hash, size and modification time are retained in `source_files` for provenance and incremental scanning.

A daemon scan first compares file size and modification time. Unchanged files are not re-read. Files whose stat signature changed are hashed; a rewrite with identical bytes updates provenance without reparsing. This keeps a frequent polling watcher practical even when race replay payloads contain large `race_scenario` blobs.

## Manual account values

`account_values` supports both an automatically detected value and a manual override. The effective-value rule is:

1. manual override, when present;
2. detected/automatic value;
3. unknown.

Automatic refreshes never delete a manual override. This is intended for currencies and account resources that umadump does not currently expose. If a future umadump release begins exporting one of those values, the application can show both the detected value and the retained manual value and ask the user which should be effective.

## Team Stadium

A Team Stadium capture is stored once by payload hash even if it is renamed or copied. Each entry in `race_result_array` also receives a lightweight `team_stadium_races` summary row. Detailed UmaParser-compatible race analysis will operate from the preserved raw payload rather than reducing the capture during import.

## Career observations

Each `career_data` directory becomes a career archive keyed by its umadump archive folder. Every `turn_###_###.json` revision is retained. Event/log/final-veteran files are attached as named career artifacts.

The account database therefore has enough history for a later Career Assistant to compare a live run with its training-project target without changing umadump's daemon process.

## Desktop integration

The Local Data page accepts the umadump output directory and can import its current contents into the account database. Collection-file selectors remain available because Parent Maker still consumes them directly during the transition to the shared account layer.

`umadump_watcher.UmadumpWatcher` provides the backend polling loop. Continuous desktop watching will be integrated after the import/database behavior has been exercised on Windows.
