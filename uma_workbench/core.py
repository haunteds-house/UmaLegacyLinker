from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import math
import os
import sqlite3
import statistics
import struct
import threading
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

STYLES = {1: "Front Runner", 2: "Pace Chaser", 3: "Late Surger", 4: "End Closer"}
DIVISIONS = {1: "Sprint", 2: "Mile", 3: "Medium", 4: "Long", 5: "Dirt"}
MAX_JSON = 32 * 1024 * 1024
MAX_ARCHIVE = 256 * 1024 * 1024


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def default_data_dir():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return base / "UmaWorkbench"


def decode_skill_events(encoded):
    """Read the validated v100000002 replay layout documented by UmaParser.

    This only reads exported bytes. An unknown layout produces an explicit error;
    callers must not count an undecodable replay as a skill activation failure.
    """
    compressed = base64.b64decode(encoded, validate=True)
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        raw = stream.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise ValueError("Replay exceeds the decoded size limit")
    if len(raw) < 36:
        raise ValueError("Replay header is incomplete")
    _, version, _, horses, horse_size, result_size, pad1, frames, frame_size = struct.unpack_from("<iifiiiiii", raw)
    if (version != 100000002 or not 1 <= horses <= 40 or horse_size != 12
            or result_size != 31 or pad1 != 0 or not 0 <= frames <= 100000
            or frame_size != 4 + horses * 12):
        raise ValueError("Unsupported replay layout; base-score analysis remains available")
    position = 36 + frames * frame_size
    if position + 4 + horses * result_size + 8 > len(raw):
        raise ValueError("Replay frames/results are incomplete")
    if struct.unpack_from("<i", raw, position)[0] != 0:
        raise ValueError("Unsupported replay padding")
    position += 4 + horses * result_size
    pad3, event_count = struct.unpack_from("<ii", raw, position)
    position += 8
    if pad3 != 0 or not 0 <= event_count <= 100000:
        raise ValueError("Unsupported replay event section")
    activations = defaultdict(list)
    for _ in range(event_count):
        if position + 8 > len(raw):
            raise ValueError("Replay event is incomplete")
        size, time, kind, count = struct.unpack_from("<HfBB", raw, position)
        position += 8
        if size != 6 + 4 * count or position + 4 * count > len(raw):
            raise ValueError("Replay event size does not match its payload")
        params = struct.unpack_from("<" + "i" * count, raw, position)
        position += 4 * count
        if kind == 3 and len(params) >= 2:
            if not 0 <= params[0] < horses:
                raise ValueError("Skill event has an invalid horse index")
            activations[params[0]].append({"skill_id": params[1], "time": time})
    if position != len(raw):
        raise ValueError("Replay contains unrecognized trailing data")
    return dict(activations)


def base_score(score_array):
    """Exactly subtract the exported bonus amounts; do not divide rounded scores."""
    return sum(int(s["score"]) - sum(int(b["bonus_score"]) for b in s.get("bonus_array", []))
               for s in score_array)


def wilson_interval(wins, count):
    if not count:
        return (0.0, 1.0)
    z = 1.959963984540054
    p = wins / count
    divisor = 1 + z * z / count
    center = (p + z * z / (2 * count)) / divisor
    half = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / divisor
    return (max(0, center - half), min(1, center + half))


class MasterData:
    TABLES = ("skill_data", "support_card_data", "card_data", "succession_factor", "race_course_set")

    def __init__(self, path=None):
        self.path = None
        self.names = {}
        self.supports = {}
        self.support_levels = []
        self.support_limits = {}
        self.cards = {}
        self.factors = {}
        self.courses = {}
        self.sha256 = ""
        if path:
            self.load(path)

    @contextmanager
    def connection(self):
        if not self.path:
            raise ValueError("Choose the game's master.mdb file in Setup to load names")
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        try:
            yield connection
        finally:
            connection.close()

    def load(self, path):
        path = Path(path).expanduser().resolve()
        if not path.is_file():
            raise ValueError("master.mdb does not exist at that location")
        previous = self.path
        self.path = path
        try:
            with self.connection() as con:
                tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"text_data", "skill_data", "card_data"}.issubset(tables):
                    raise ValueError("This is not a supported game master database")
                names = {(int(r[0]), int(r[1])): r[2] for r in con.execute(
                    'SELECT category, "index", text FROM text_data WHERE category IN (4,6,47,48,76,77,147)')}
                cards = {r["id"]: dict(r) for r in con.execute("SELECT * FROM card_data")}
                supports = {r["id"]: dict(r) for r in con.execute("SELECT * FROM support_card_data")}
                support_levels = [dict(row) for row in con.execute("SELECT * FROM support_card_level")] if "support_card_level" in tables else []
                support_limits = {row["rarity"]: dict(row) for row in con.execute("SELECT * FROM support_card_limit")} if "support_card_limit" in tables else {}
                factors = {r["factor_id"]: dict(r) for r in con.execute("SELECT * FROM succession_factor")}
                courses = {r["instance_id"]: dict(r) for r in con.execute(
                    "SELECT ri.id AS instance_id, rc.* FROM race_instance ri JOIN race ra ON ri.race_id=ra.id "
                    "JOIN race_course_set rc ON ra.course_set=rc.id")}
            self.names, self.cards, self.supports, self.factors, self.courses = names, cards, supports, factors, courses
            self.support_levels, self.support_limits = support_levels, support_limits
            self.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception:
            self.path = previous
            raise

    def card_name(self, card_id):
        return self.names.get((4, int(card_id)), f"Trainee #{card_id}")

    def support_name(self, support_id):
        chara = self.names.get((77, int(support_id)), "")
        title = self.names.get((76, int(support_id)), "")
        return f"{title} {chara}".strip() or f"Support #{support_id}"

    def skill_name(self, skill_id):
        return self.names.get((47, int(skill_id)), f"Skill #{skill_id}")

    def support_level(self, card):
        if "level" in card:
            return int(card["level"])
        rarity = self.supports.get(int(card["support_card_id"]), {}).get("rarity")
        thresholds = [row for row in self.support_levels if row["rarity"] == rarity]
        if not thresholds or "exp" not in card:
            return None
        cap = self.support_limits.get(rarity, {}).get(f"limit_{int(card.get('limit_break_count', 0))}")
        levels = [row["level"] for row in thresholds if row["total_exp"] <= int(card["exp"]) and (cap is None or row["level"] <= cap)]
        return max(levels, default=1)

    def character_id(self, card_id):
        return self.cards.get(int(card_id), {}).get("chara_id", int(card_id) // 100)

    def browse(self, table, query=""):
        if table not in self.TABLES:
            raise ValueError("Unsupported technical-data table")
        with self.connection() as con:
            rows = [dict(r) for r in con.execute(f'SELECT * FROM "{table}"')]
        named = []
        for row in rows:
            identity = row.get("id", row.get("factor_id"))
            name = (self.skill_name(identity) if table == "skill_data" else
                    self.support_name(identity) if table == "support_card_data" else
                    self.card_name(identity) if table == "card_data" else f"#{identity}")
            if query.casefold() in (name + " " + canonical(row)).casefold():
                named.append({"name": name, **row})
        return named[:250]


class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory or default_data_dir()).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "workbench.sqlite3"
        self.lock = threading.RLock()
        with self.connection() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS artifacts(
                    sha TEXT PRIMARY KEY, kind TEXT NOT NULL, source TEXT NOT NULL,
                    imported_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entities(
                    kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
                    source_sha TEXT NOT NULL, PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS captures(
                    sha TEXT PRIMARY KEY, cohort TEXT NOT NULL, source TEXT NOT NULL,
                    imported_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS observations(
                    race_key TEXT NOT NULL, veteran_id TEXT NOT NULL, cohort TEXT NOT NULL,
                    division INTEGER NOT NULL, card_id INTEGER NOT NULL, style INTEGER NOT NULL,
                    base_points INTEGER NOT NULL, final_points INTEGER NOT NULL,
                    finish INTEGER NOT NULL, course INTEGER NOT NULL, decoded INTEGER NOT NULL,
                    owned_skills TEXT NOT NULL, activated_skills TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(race_key,veteran_id));
                CREATE INDEX IF NOT EXISTS observations_cohort ON observations(cohort);
                CREATE TABLE IF NOT EXISTS goals(
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS resource_goals(
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, balance REAL NOT NULL,
                    target REAL NOT NULL, income REAL NOT NULL);
            """)

    @contextmanager
    def connection(self):
        with self.lock:
            con = sqlite3.connect(self.path, timeout=20)
            con.row_factory = sqlite3.Row
            try:
                with con:
                    yield con
            finally:
                con.close()

    def setting(self, key, default=None):
        with self.connection() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.connection() as con:
            con.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, canonical(value)))

    def entities(self, kind):
        with self.connection() as con:
            return [json.loads(r[0]) for r in con.execute(
                "SELECT payload FROM entities WHERE kind=? ORDER BY CAST(id AS INTEGER)", (kind,))]

    def counts(self):
        with self.connection() as con:
            counts = {r[0]: r[1] for r in con.execute("SELECT kind,COUNT(*) FROM entities GROUP BY kind")}
            counts["captures"] = con.execute("SELECT COUNT(*) FROM captures").fetchone()[0]
            counts["races"] = con.execute("SELECT COUNT(DISTINCT race_key) FROM observations").fetchone()[0]
            counts["observations"] = con.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            counts["artifacts"] = con.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        return counts

    def cohorts(self):
        with self.connection() as con:
            return [dict(r) for r in con.execute(
                "SELECT cohort, COUNT(*) AS captures, MAX(source) AS latest FROM captures GROUP BY cohort ORDER BY latest DESC")]

    def observations(self, cohort=None):
        with self.connection() as con:
            sql = "SELECT * FROM observations"
            args = ()
            if cohort:
                sql += " WHERE cohort=?"
                args = (cohort,)
            return [dict(r) for r in con.execute(sql, args)]

    def import_path(self, path):
        path = Path(path).expanduser().resolve()
        report = {"imported": 0, "unchanged": 0, "ignored": 0, "errors": [], "warnings": []}
        def consume(source, contents):
            try:
                status, warnings = self.import_bytes(source, contents)
                report[status] += 1
                report["warnings"].extend(warnings)
            except (ValueError, KeyError, TypeError, OverflowError, sqlite3.Error) as exc:
                report["errors"].append(f"{Path(source).name}: {exc}")
        if path.is_dir():
            for child in sorted(path.rglob("*.json")):
                # Do not follow files linked outside the selected output tree.
                if not child.resolve().is_relative_to(path):
                    continue
                try:
                    before = child.stat()
                    if before.st_size > MAX_JSON:
                        raise ValueError("JSON exceeds the size limit")
                    data = child.read_bytes()
                    after = child.stat()
                    if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                        raise ValueError("File is still being written; it will be retried")
                    consume(str(child), data)
                except (OSError, ValueError) as exc:
                    report["errors"].append(f"{child.name}: {exc}")
        elif path.suffix.lower() == ".zip":
            with ZipFile(path) as archive:
                members = [i for i in archive.infolist() if i.filename.lower().endswith(".json")]
                if sum(i.file_size for i in members) > MAX_ARCHIVE:
                    raise ValueError("Archive JSON exceeds the size limit")
                for member in sorted(members, key=lambda i: i.filename):
                    if member.file_size > MAX_JSON:
                        report["errors"].append(f"{member.filename}: JSON exceeds the size limit")
                    else:
                        # Read JSON directly. Executables and archive paths are never extracted.
                        consume(f"{path.name}/{member.filename}", archive.read(member))
        else:
            if path.stat().st_size > MAX_JSON:
                raise ValueError("JSON exceeds the size limit")
            consume(str(path), path.read_bytes())
        return report

    def import_bytes(self, source, contents):
        if len(contents) > MAX_JSON:
            raise ValueError("JSON exceeds the size limit")
        data = json.loads(contents.decode("utf-8-sig"))
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data["data"]
        kind, rows, key = self._classify(source, data)
        if not kind:
            return "ignored", []
        sha = fingerprint(data)
        with self.connection() as con:
            existing_artifact = con.execute("SELECT 1 FROM artifacts WHERE sha=?", (sha,)).fetchone()
            if existing_artifact:
                if rows is None:
                    return "unchanged", []
                active = con.execute("SELECT value FROM settings WHERE key=?", ("snapshot:" + kind,)).fetchone()
                if active and json.loads(active[0]) == sha:
                    return "unchanged", []
            if rows is not None:
                if not isinstance(rows, list) or any(not isinstance(x, dict) or key not in x for x in rows):
                    raise ValueError(f"Invalid {kind} snapshot; the previous collection was kept")
                ids = [str(x[key]) for x in rows]
                if len(ids) != len(set(ids)):
                    raise ValueError(f"Duplicate {kind} identifiers; the previous collection was kept")
                accounts = {int(x["viewer_id"]) for x in rows if int(x.get("viewer_id", 0)) > 0}
                account_row = con.execute("SELECT value FROM settings WHERE key='account'").fetchone()
                account = json.loads(account_row[0]) if account_row else None
                if len(accounts) > 1 or (account is not None and accounts and accounts != {account}):
                    raise ValueError("This is a different account. Use a separate data directory with --data-dir")
                if accounts and account is None:
                    con.execute("INSERT INTO settings VALUES ('account',?)", (canonical(next(iter(accounts))),))
                con.execute("DELETE FROM entities WHERE kind=?", (kind,))
                con.executemany("INSERT INTO entities VALUES (?,?,?,?)",
                                [(kind, str(x[key]), canonical(x), sha) for x in rows])
                con.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("snapshot:" + kind, canonical(sha)))
            warnings = self._import_tt(con, sha, source, data) if kind == "tt" else []
            con.execute("INSERT OR IGNORE INTO artifacts VALUES (?,?,?,?,?)", (sha, kind, source, utc_now(), canonical(data)))
        return "imported", warnings

    @staticmethod
    def _classify(source, data):
        name = Path(source).name.lower()
        if isinstance(data, dict) and "race_result_array" in data and "race_start_params_array" in data:
            return "tt", None, None
        if isinstance(data, dict) and "trained_chara_array" in data:
            return "veterans", data["trained_chara_array"], "trained_chara_id"
        known = {"card_data.json": ("trainees", "card_id"),
                 "support_card_data.json": ("supports", "support_card_id"),
                 "trained_chara_data.json": ("veterans", "trained_chara_id")}
        if name in known:
            kind, key = known[name]
            return kind, data, key
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                if "trained_chara_id" in first and "factor_info_array" in first:
                    return "veterans", data, "trained_chara_id"
                if "support_card_id" in first and "limit_break_count" in first:
                    return "supports", data, "support_card_id"
                if "card_id" in first and "talent_level" in first:
                    return "trainees", data, "card_id"
        if "career_data" in source.replace("\\", "/") or name in ("manifest.json", "events.json", "log.json", "veteran.json"):
            return "career", None, None
        if isinstance(data, dict) and "single_mode_load_common" in data:
            return "career", None, None
        if isinstance(data, dict) and "raceHorse" in data:
            return "single_race", None, None
        if name in ("honor_data.json", "event_data.json", "trophy_data.json", "trophy_data_limited.json", "talk_gallery_data.json"):
            return "auxiliary", None, None
        return None, None, None

    def _import_tt(self, con, sha, source, data):
        starts = {int(s["round"]): s for s in data["race_start_params_array"]}
        prepared, roster, warnings = [], [], []
        for result in data["race_result_array"]:
            start = starts.get(int(result["round"]))
            if start is None:
                raise ValueError("TT round is missing its start metadata")
            horses = {int(h["frame_order"]): h for h in start["race_horse_data_array"]}
            local = [r for r in result["chara_result_array"] if r.get("score_array")]
            if not local:
                continue
            try:
                activated = decode_skill_events(result["race_scenario"])
                decoded = 1
            except (ValueError, KeyError, TypeError, OSError, EOFError, struct.error) as exc:
                activated, decoded = {}, 0
                warnings.append(f"{Path(source).name}, round {result['round']}: {exc}")
            # A replay plus seed/course/participants identifies a race across capture files.
            race_key = fingerprint({"seed": start.get("random_seed"), "course": start["race_instance_id"],
                "participants": [(h["frame_order"], h["trained_chara_id"], h["card_id"])
                                 for h in start["race_horse_data_array"]], "replay": result.get("race_scenario")})
            for runner in local:
                horse = horses[int(runner["frame_order"])]
                identity = str(runner["trained_chara_id"])
                if identity != str(horse["trained_chara_id"]):
                    raise ValueError("TT start/result veteran identifiers disagree")
                division, style = int(result["distance_type"]), int(horse["running_style"])
                roster.append((identity, int(horse["card_id"]), division, style))
                events = activated.get(int(runner["frame_order"]) - 1, [])
                owned = [int(s["skill_id"]) for s in horse.get("skill_array", [])]
                prepared.append((race_key, identity, division, int(horse["card_id"]), style,
                    base_score(runner["score_array"]), sum(int(s["score"]) for s in runner["score_array"]),
                    int(runner["finish_order"]), int(start["race_instance_id"]), decoded,
                    canonical(owned), canonical(events), canonical({"horse": horse, "result": runner})))
        cohort = fingerprint(sorted(roster))[:16]
        con.execute("INSERT INTO captures VALUES (?,?,?,?)", (sha, cohort, source, utc_now()))
        for row in prepared:
            con.execute("INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        row[:2] + (cohort,) + row[2:])
        return warnings

    def metrics(self, cohort=None):
        grouped = defaultdict(list)
        for observation in self.observations(cohort):
            grouped[(observation["veteran_id"], observation["division"], observation["style"])].append(observation)
        metrics = []
        for (identity, division, style), observations in grouped.items():
            values = [r["base_points"] for r in observations]
            count, wins = len(values), sum(r["finish"] == 1 for r in observations)
            mean = statistics.mean(values)
            se = statistics.stdev(values) / math.sqrt(count) if count > 1 else None
            lo, hi = wilson_interval(wins, count)
            metrics.append({"veteran_id": identity, "card_id": observations[0]["card_id"],
                "division": division, "style": style, "races": count, "mean": mean, "se": se,
                "lower_score": max(0, mean - 1.96 * se) if se is not None else 0,
                "wins": wins, "win_rate": wins / count, "win_lo": lo, "win_hi": hi,
                "decoded_races": sum(r["decoded"] for r in observations)})
        return sorted(metrics, key=lambda r: (r["division"], -r["mean"], r["veteran_id"]))

    def skill_metrics(self, cohort=None):
        groups = defaultdict(lambda: {"exposures": 0, "active_races": 0, "activations": 0})
        for observation in self.observations(cohort):
            if not observation["decoded"]:
                continue
            active = [e["skill_id"] for e in json.loads(observation["activated_skills"])]
            for skill in set(json.loads(observation["owned_skills"])):
                group = groups[(observation["veteran_id"], observation["card_id"], skill)]
                group["exposures"] += 1
                group["active_races"] += int(skill in active)
                group["activations"] += active.count(skill)
        return [{"veteran_id": key[0], "card_id": key[1], "skill_id": key[2], **value,
                 "rate": value["active_races"] / value["exposures"]} for key, value in groups.items()]

    def career_summary(self):
        with self.connection() as con:
            rows = con.execute("SELECT source,payload FROM artifacts WHERE kind='career' ORDER BY source").fetchall()
        careers = {}
        for source, payload in rows:
            data = json.loads(payload)
            if not isinstance(data, dict):
                continue
            if "single_mode_load_common" in data:
                info = data["single_mode_load_common"].get("chara_info", {})
                key = str(info.get("single_mode_chara_id", Path(source).parent.parent.name))
                turn = int(info.get("turn", -1))
                entry = careers.setdefault(key, {"snapshots": 0, "turns": set(), "latest": {}, "turn": -1})
                entry["snapshots"] += 1
                entry["turns"].add(turn)
                if turn >= entry["turn"]:
                    entry["latest"], entry["turn"] = info, turn
        return [{**value, "id": key, "turns": sorted(value["turns"])} for key, value in careers.items()]

    def save_goal(self, title, payload, status="Planned"):
        if not title.strip():
            raise ValueError("A training goal needs a title")
        dependencies = [int(x) for x in payload.get("prerequisites", [])]
        if len(dependencies) != len(set(dependencies)):
            raise ValueError("Repeated prerequisite goal")
        with self.connection() as con:
            existing = {r[0] for r in con.execute("SELECT id FROM goals")}
            if any(d not in existing for d in dependencies):
                raise ValueError("A prerequisite goal does not exist")
            # New goals may only depend on existing goals: cycles cannot be created.
            cursor = con.execute("INSERT INTO goals(title,status,payload,created_at) VALUES (?,?,?,?)",
                                 (title.strip(), status, canonical(payload), utc_now()))
            return cursor.lastrowid

    def goals(self):
        with self.connection() as con:
            rows = [dict(r) for r in con.execute("SELECT * FROM goals ORDER BY id")]
        for row in rows:
            row["details"] = json.loads(row.pop("payload"))
        return rows

    def change_goal_status(self, identity, status):
        if status not in ("Planned", "In progress", "Complete", "Abandoned"):
            raise ValueError("Unsupported goal status")
        with self.connection() as con:
            row = con.execute("SELECT payload FROM goals WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise ValueError("The goal does not exist")
            prerequisites = json.loads(row[0]).get("prerequisites", [])
            if status == "In progress":
                statuses = {r[0]: r[1] for r in con.execute("SELECT id,status FROM goals")}
                if any(statuses.get(int(d)) != "Complete" for d in prerequisites):
                    raise ValueError("Complete the prerequisite goals before starting this one")
            con.execute("UPDATE goals SET status=? WHERE id=?", (status, identity))

    def save_resource(self, name, balance, target, income):
        numbers = [float(balance), float(target), float(income)]
        if not name.strip() or any(not math.isfinite(x) or x < 0 for x in numbers):
            raise ValueError("Enter a name and finite, nonnegative resource amounts")
        with self.connection() as con:
            con.execute("INSERT INTO resource_goals(name,balance,target,income) VALUES (?,?,?,?)",
                        (name.strip(), *numbers))

    def resources(self):
        with self.connection() as con:
            rows = [dict(r) for r in con.execute("SELECT * FROM resource_goals ORDER BY id")]
        for row in rows:
            row["missing"] = max(0, row["target"] - row["balance"])
            row["runs"] = math.ceil(row["missing"] / row["income"]) if row["income"] else None
        return rows

    def remove_resource(self, identity):
        with self.connection() as con:
            con.execute("DELETE FROM resource_goals WHERE id=?", (identity,))

    def lineage_export(self):
        path = self.directory / "handoff" / "trained_chara_data.json"
        path.parent.mkdir(exist_ok=True)
        rows = self.entities("veterans")
        if not rows:
            raise ValueError("Import your veterans first")
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
        return path


def measured_roster(store, master, min_races=3, distinct_styles=True):
    """Exact min-cost assignment for the AVAILABLE, OBSERVED candidate pool only.

    No unobserved runner is given a fabricated performance score. The objective
    is an approximate lower score bound; it is not a validated race simulator.
    Each character occupies at most one slot; each division has three slots.
    """
    available = {str(v["trained_chara_id"]) for v in store.entities("veterans")}
    choices = {}
    for metric in store.metrics():
        if metric["veteran_id"] not in available or metric["races"] < min_races:
            continue
        chara = master.character_id(metric["card_id"])
        style = metric["style"] if distinct_styles else 0
        key = (chara, metric["division"], style)
        previous = choices.get(key)
        if previous is None or metric["lower_score"] > previous["lower_score"]:
            choices[key] = metric
    graph = defaultdict(list)
    def edge(source, target, capacity, cost, payload=None):
        forward = {"to": target, "cap": capacity, "cost": cost, "rev": len(graph[target]), "payload": payload}
        reverse = {"to": source, "cap": 0, "cost": -cost, "rev": len(graph[source]), "payload": None}
        graph[source].append(forward)
        graph[target].append(reverse)
        return forward
    source, sink, selected_edges = ("source",), ("sink",), []
    for chara in sorted({k[0] for k in choices}):
        edge(source, ("chara", chara), 1, 0)
    for (chara, division, style), metric in sorted(choices.items()):
        selected_edges.append(edge(("chara", chara), ("role", division, style), 1, -metric["lower_score"], metric))
    for division, style in sorted({(k[1], k[2]) for k in choices}):
        edge(("role", division, style), ("division", division), 1 if distinct_styles else 3, 0)
    for division in DIVISIONS:
        edge(("division", division), sink, 3, 0)
    flow = 0
    while flow < 15:
        distances, previous = {source: 0}, {}
        # Tiny acyclic-forward residual network: Bellman-Ford handles reverse edges.
        for _ in range(len(graph) - 1):
            changed = False
            for node in list(graph):
                if node not in distances:
                    continue
                for index, e in enumerate(graph[node]):
                    proposed = distances[node] + e["cost"]
                    if e["cap"] and proposed < distances.get(e["to"], float("inf")) - 1e-9:
                        distances[e["to"]], previous[e["to"]] = proposed, (node, index)
                        changed = True
            if not changed:
                break
        if sink not in previous:
            break
        node = sink
        while node != source:
            parent, index = previous[node]
            e = graph[parent][index]
            e["cap"] -= 1
            graph[node][e["rev"]]["cap"] += 1
            node = parent
        flow += 1
    selected = [e["payload"] for e in selected_edges if e["cap"] == 0]
    selected.sort(key=lambda r: (r["division"], -r["mean"]))
    vacancies = {division: 3 - sum(r["division"] == division for r in selected) for division in DIVISIONS}
    return {"model": "observed-candidates-v1", "complete": flow == 15, "selected": selected,
            "vacancies": vacancies, "objective": sum(r["lower_score"] for r in selected),
            "note": "Approximate historical score bound. Mixed race contexts and team interactions can affect comparisons."}
