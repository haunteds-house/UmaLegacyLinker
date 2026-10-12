"""Persistent local account state shared by collection, race and training tools.

The account database is deliberately independent from the Legacy Linker output
folder. Collection exports and daemon observations are treated as immutable
source evidence; normalized current-state rows and compressed raw observations
are stored in SQLite so later optimizers do not need to reparse arbitrary
umadump files.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def app_data_dir() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "UmaLegacyLinker"
    if os.name == "posix":
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        return root / "UmaLegacyLinker"
    return Path.home() / ".uma_legacy_linker"


def default_account_db_path() -> Path:
    return app_data_dir() / "account.sqlite3"


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def payload_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def compressed_payload(payload: Any) -> bytes:
    return gzip.compress(canonical_json_bytes(payload), compresslevel=6)


def decompress_payload(blob: bytes) -> Any:
    return json.loads(gzip.decompress(blob).decode("utf-8"))


@dataclass(frozen=True)
class AccountSummary:
    trainee_cards: int
    support_cards: int
    active_veterans: int
    historical_veterans: int
    team_stadium_captures: int
    single_race_captures: int
    career_archives: int
    career_snapshots: int
    documents: int
    manual_values: int


class AccountStore:
    """SQLite-backed local account store.

    The schema keeps source provenance beside every imported object. Static
    collection exports represent the latest account snapshot; veterans are kept
    historically after they disappear from a later export so race/career history
    remains referentially useful.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or default_account_db_path()).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = NORMAL")
        self._initialize()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "AccountStore":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS source_files (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                source_root TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                mtime_ns INTEGER NOT NULL DEFAULT 0,
                first_imported_at TEXT NOT NULL,
                last_imported_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_source_files_kind ON source_files(kind);
            CREATE INDEX IF NOT EXISTS idx_source_files_sha ON source_files(sha256);

            CREATE TABLE IF NOT EXISTS owned_trainees (
                card_id INTEGER PRIMARY KEY,
                rarity INTEGER NOT NULL DEFAULT 0,
                talent_level INTEGER NOT NULL DEFAULT 0,
                create_time TEXT,
                skills_json TEXT NOT NULL DEFAULT '[]',
                raw_json TEXT NOT NULL,
                source_file_id INTEGER REFERENCES source_files(id),
                active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS owned_supports (
                support_card_id INTEGER PRIMARY KEY,
                exp INTEGER NOT NULL DEFAULT 0,
                limit_break_count INTEGER NOT NULL DEFAULT 0,
                favorite_flag INTEGER NOT NULL DEFAULT 0,
                stock INTEGER NOT NULL DEFAULT 0,
                possess_time TEXT,
                create_time TEXT,
                level INTEGER NOT NULL DEFAULT 0,
                max_level INTEGER NOT NULL DEFAULT 0,
                extra_json TEXT NOT NULL DEFAULT '{}',
                raw_json TEXT NOT NULL,
                source_file_id INTEGER REFERENCES source_files(id),
                active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS veterans (
                trained_chara_id INTEGER PRIMARY KEY,
                card_id INTEGER NOT NULL DEFAULT 0,
                scenario_id INTEGER NOT NULL DEFAULT 0,
                rank_score INTEGER NOT NULL DEFAULT 0,
                rank INTEGER NOT NULL DEFAULT 0,
                speed INTEGER NOT NULL DEFAULT 0,
                stamina INTEGER NOT NULL DEFAULT 0,
                power INTEGER NOT NULL DEFAULT 0,
                guts INTEGER NOT NULL DEFAULT 0,
                wiz INTEGER NOT NULL DEFAULT 0,
                running_style INTEGER NOT NULL DEFAULT 0,
                is_locked INTEGER NOT NULL DEFAULT 0,
                is_saved INTEGER NOT NULL DEFAULT 0,
                memo TEXT NOT NULL DEFAULT '',
                create_time TEXT,
                register_time TEXT,
                raw_json TEXT NOT NULL,
                source_file_id INTEGER REFERENCES source_files(id),
                active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_veterans_card ON veterans(card_id);
            CREATE INDEX IF NOT EXISTS idx_veterans_active ON veterans(active);

            CREATE TABLE IF NOT EXISTS race_captures (
                id INTEGER PRIMARY KEY,
                capture_kind TEXT NOT NULL,
                source_file_id INTEGER REFERENCES source_files(id),
                payload_sha256 TEXT NOT NULL UNIQUE,
                observed_at TEXT,
                race_count INTEGER NOT NULL DEFAULT 0,
                team_total_score INTEGER,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                payload_gzip BLOB NOT NULL,
                imported_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_race_captures_kind ON race_captures(capture_kind);
            CREATE INDEX IF NOT EXISTS idx_race_captures_observed ON race_captures(observed_at);

            CREATE TABLE IF NOT EXISTS team_stadium_races (
                id INTEGER PRIMARY KEY,
                capture_id INTEGER NOT NULL REFERENCES race_captures(id) ON DELETE CASCADE,
                race_index INTEGER NOT NULL,
                round INTEGER,
                team_total_score INTEGER,
                win_type INTEGER,
                chara_result_count INTEGER NOT NULL DEFAULT 0,
                summary_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(capture_id, race_index)
            );

            CREATE TABLE IF NOT EXISTS career_archives (
                id INTEGER PRIMARY KEY,
                archive_key TEXT NOT NULL UNIQUE,
                source_dir TEXT NOT NULL,
                archive_type TEXT,
                created_utc TEXT,
                dumper_version TEXT,
                card_id INTEGER,
                scenario_id INTEGER,
                identity_json TEXT NOT NULL DEFAULT '{}',
                manifest_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS career_snapshots (
                id INTEGER PRIMARY KEY,
                archive_id INTEGER NOT NULL REFERENCES career_archives(id) ON DELETE CASCADE,
                turn INTEGER NOT NULL,
                revision INTEGER NOT NULL,
                source_file_id INTEGER REFERENCES source_files(id),
                payload_sha256 TEXT NOT NULL,
                payload_gzip BLOB NOT NULL,
                observed_at TEXT,
                imported_at TEXT NOT NULL,
                UNIQUE(archive_id, turn, revision)
            );
            CREATE INDEX IF NOT EXISTS idx_career_snapshots_archive_turn
                ON career_snapshots(archive_id, turn, revision);

            CREATE TABLE IF NOT EXISTS career_artifacts (
                id INTEGER PRIMARY KEY,
                archive_id INTEGER NOT NULL REFERENCES career_archives(id) ON DELETE CASCADE,
                artifact_type TEXT NOT NULL,
                source_file_id INTEGER REFERENCES source_files(id),
                payload_sha256 TEXT NOT NULL,
                payload_gzip BLOB NOT NULL,
                imported_at TEXT NOT NULL,
                UNIQUE(archive_id, artifact_type)
            );

            CREATE TABLE IF NOT EXISTS account_documents (
                document_type TEXT PRIMARY KEY,
                source_file_id INTEGER REFERENCES source_files(id),
                payload_sha256 TEXT NOT NULL,
                payload_gzip BLOB NOT NULL,
                imported_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS account_values (
                key TEXT PRIMARY KEY,
                automatic_value TEXT,
                automatic_source TEXT,
                manual_value TEXT,
                unit TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                automatic_updated_at TEXT,
                manual_updated_at TEXT
            );
            """
        )
        existing = self.connection.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        if existing is None:
            self.connection.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
        elif int(existing[0]) != SCHEMA_VERSION:
            raise sqlite3.DatabaseError(
                f"Unsupported account database schema {existing[0]}; expected {SCHEMA_VERSION}."
            )
        self.connection.commit()

    def source_signature(self, path: str | Path) -> tuple[str, int, int] | None:
        row = self.connection.execute(
            "SELECT sha256, size_bytes, mtime_ns FROM source_files WHERE path = ?",
            (str(Path(path).expanduser().resolve()),),
        ).fetchone()
        if row is None:
            return None
        return str(row["sha256"]), int(row["size_bytes"]), int(row["mtime_ns"])

    def source_hash(self, path: str | Path) -> str | None:
        signature = self.source_signature(path)
        return signature[0] if signature is not None else None

    def source_stat_unchanged(
        self, path: str | Path, *, size_bytes: int, mtime_ns: int
    ) -> bool:
        signature = self.source_signature(path)
        return (
            signature is not None
            and signature[1] == int(size_bytes)
            and signature[2] == int(mtime_ns)
        )

    def source_needs_import(self, path: str | Path, sha256: str) -> bool:
        return self.source_hash(path) != sha256

    def record_source(
        self,
        path: str | Path,
        *,
        source_root: str | Path,
        kind: str,
        sha256: str,
        size_bytes: int,
        mtime_ns: int,
    ) -> int:
        now = utc_now()
        resolved = str(Path(path).expanduser().resolve())
        root = str(Path(source_root).expanduser().resolve())
        self.connection.execute(
            """
            INSERT INTO source_files(
                path, source_root, kind, sha256, size_bytes, mtime_ns,
                first_imported_at, last_imported_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                source_root = excluded.source_root,
                kind = excluded.kind,
                sha256 = excluded.sha256,
                size_bytes = excluded.size_bytes,
                mtime_ns = excluded.mtime_ns,
                last_imported_at = excluded.last_imported_at
            """,
            (resolved, root, kind, sha256, int(size_bytes), int(mtime_ns), now, now),
        )
        row = self.connection.execute(
            "SELECT id FROM source_files WHERE path = ?", (resolved,)
        ).fetchone()
        assert row is not None
        return int(row[0])

    def replace_owned_trainees(
        self, rows: Iterable[dict[str, Any]], *, source_file_id: int
    ) -> int:
        now = utc_now()
        materialized = [row for row in rows if isinstance(row, dict)]
        self.connection.execute("UPDATE owned_trainees SET active = 0")
        count = 0
        for row in materialized:
            try:
                card_id = int(row.get("card_id") or 0)
            except (TypeError, ValueError):
                continue
            if card_id <= 0:
                continue
            skills = row.get("skill_data_array") or []
            self.connection.execute(
                """
                INSERT INTO owned_trainees(
                    card_id, rarity, talent_level, create_time, skills_json,
                    raw_json, source_file_id, active, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(card_id) DO UPDATE SET
                    rarity = excluded.rarity,
                    talent_level = excluded.talent_level,
                    create_time = excluded.create_time,
                    skills_json = excluded.skills_json,
                    raw_json = excluded.raw_json,
                    source_file_id = excluded.source_file_id,
                    active = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    card_id,
                    _int(row.get("rarity")),
                    _int(row.get("talent_level")),
                    _text_or_none(row.get("create_time")),
                    json.dumps(skills, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(row, ensure_ascii=False, separators=(",", ":")),
                    source_file_id,
                    now,
                ),
            )
            count += 1
        return count

    def replace_owned_supports(
        self, rows: Iterable[dict[str, Any]], *, source_file_id: int
    ) -> int:
        now = utc_now()
        materialized = [row for row in rows if isinstance(row, dict)]
        self.connection.execute("UPDATE owned_supports SET active = 0")
        count = 0
        for row in materialized:
            try:
                support_id = int(row.get("support_card_id") or row.get("card_id") or 0)
            except (TypeError, ValueError):
                continue
            if support_id <= 0:
                continue
            extra = row.get("extra_data") if isinstance(row.get("extra_data"), dict) else {}
            self.connection.execute(
                """
                INSERT INTO owned_supports(
                    support_card_id, exp, limit_break_count, favorite_flag,
                    stock, possess_time, create_time, level, max_level,
                    extra_json, raw_json, source_file_id, active, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(support_card_id) DO UPDATE SET
                    exp = excluded.exp,
                    limit_break_count = excluded.limit_break_count,
                    favorite_flag = excluded.favorite_flag,
                    stock = excluded.stock,
                    possess_time = excluded.possess_time,
                    create_time = excluded.create_time,
                    level = excluded.level,
                    max_level = excluded.max_level,
                    extra_json = excluded.extra_json,
                    raw_json = excluded.raw_json,
                    source_file_id = excluded.source_file_id,
                    active = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    support_id,
                    _int(row.get("exp")),
                    _int(row.get("limit_break_count")),
                    _int(row.get("favorite_flag")),
                    _int(row.get("stock")),
                    _text_or_none(row.get("possess_time")),
                    _text_or_none(row.get("create_time")),
                    _int(extra.get("level")),
                    _int(extra.get("max_level")),
                    json.dumps(extra, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(row, ensure_ascii=False, separators=(",", ":")),
                    source_file_id,
                    now,
                ),
            )
            count += 1
        return count

    def replace_veterans(
        self, rows: Iterable[dict[str, Any]], *, source_file_id: int
    ) -> int:
        now = utc_now()
        materialized = [row for row in rows if isinstance(row, dict)]
        self.connection.execute("UPDATE veterans SET active = 0")
        count = 0
        for row in materialized:
            try:
                trained_id = int(row.get("trained_chara_id") or 0)
            except (TypeError, ValueError):
                continue
            if trained_id <= 0:
                continue
            self.connection.execute(
                """
                INSERT INTO veterans(
                    trained_chara_id, card_id, scenario_id, rank_score, rank,
                    speed, stamina, power, guts, wiz, running_style,
                    is_locked, is_saved, memo, create_time, register_time,
                    raw_json, source_file_id, active, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(trained_chara_id) DO UPDATE SET
                    card_id = excluded.card_id,
                    scenario_id = excluded.scenario_id,
                    rank_score = excluded.rank_score,
                    rank = excluded.rank,
                    speed = excluded.speed,
                    stamina = excluded.stamina,
                    power = excluded.power,
                    guts = excluded.guts,
                    wiz = excluded.wiz,
                    running_style = excluded.running_style,
                    is_locked = excluded.is_locked,
                    is_saved = excluded.is_saved,
                    memo = excluded.memo,
                    create_time = excluded.create_time,
                    register_time = excluded.register_time,
                    raw_json = excluded.raw_json,
                    source_file_id = excluded.source_file_id,
                    active = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    trained_id,
                    _int(row.get("card_id")),
                    _int(row.get("scenario_id")),
                    _int(row.get("rank_score")),
                    _int(row.get("rank")),
                    _int(row.get("speed")),
                    _int(row.get("stamina")),
                    _int(row.get("power")),
                    _int(row.get("guts")),
                    _int(row.get("wiz")),
                    _int(row.get("running_style")),
                    _int(row.get("is_locked")),
                    _int(row.get("is_saved")),
                    str(row.get("memo") or ""),
                    _text_or_none(row.get("create_time")),
                    _text_or_none(row.get("register_time")),
                    json.dumps(row, ensure_ascii=False, separators=(",", ":")),
                    source_file_id,
                    now,
                ),
            )
            count += 1
        return count

    def store_race_capture(
        self,
        *,
        capture_kind: str,
        source_file_id: int,
        payload: Any,
        observed_at: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[int, bool]:
        digest = payload_sha256(payload)
        existing = self.connection.execute(
            "SELECT id FROM race_captures WHERE payload_sha256 = ?", (digest,)
        ).fetchone()
        if existing is not None:
            return int(existing[0]), False
        metadata = dict(metadata or {})
        race_results = payload.get("race_result_array") if isinstance(payload, dict) else None
        race_count = len(race_results) if isinstance(race_results, list) else 1
        team_total_score = metadata.get("team_total_score")
        cursor = self.connection.execute(
            """
            INSERT INTO race_captures(
                capture_kind, source_file_id, payload_sha256, observed_at,
                race_count, team_total_score, metadata_json, payload_gzip, imported_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                capture_kind,
                source_file_id,
                digest,
                observed_at,
                int(race_count),
                _int_or_none(team_total_score),
                json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
                compressed_payload(payload),
                utc_now(),
            ),
        )
        capture_id = int(cursor.lastrowid)
        if capture_kind == "team_stadium" and isinstance(race_results, list):
            for index, race in enumerate(race_results):
                if not isinstance(race, dict):
                    continue
                summary = {
                    key: race.get(key)
                    for key in (
                        "distance_type",
                        "round",
                        "team_total_score",
                        "win_type",
                        "current_consecutive_win_count",
                        "bonus_rate_by_next_win",
                    )
                    if race.get(key) is not None
                }
                chara_results = race.get("chara_result_array")
                self.connection.execute(
                    """
                    INSERT INTO team_stadium_races(
                        capture_id, race_index, round, team_total_score, win_type,
                        chara_result_count, summary_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        capture_id,
                        index,
                        _int_or_none(race.get("round")),
                        _int_or_none(race.get("team_total_score")),
                        _int_or_none(race.get("win_type")),
                        len(chara_results) if isinstance(chara_results, list) else 0,
                        json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
                    ),
                )
        return capture_id, True

    def upsert_career_archive(
        self,
        *,
        archive_key: str,
        source_dir: str | Path,
        manifest: dict[str, Any],
    ) -> int:
        identity = manifest.get("identity") if isinstance(manifest.get("identity"), dict) else {}
        self.connection.execute(
            """
            INSERT INTO career_archives(
                archive_key, source_dir, archive_type, created_utc, dumper_version,
                card_id, scenario_id, identity_json, manifest_json, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(archive_key) DO UPDATE SET
                source_dir = excluded.source_dir,
                archive_type = excluded.archive_type,
                created_utc = excluded.created_utc,
                dumper_version = excluded.dumper_version,
                card_id = excluded.card_id,
                scenario_id = excluded.scenario_id,
                identity_json = excluded.identity_json,
                manifest_json = excluded.manifest_json,
                updated_at = excluded.updated_at
            """,
            (
                archive_key,
                str(Path(source_dir).expanduser().resolve()),
                _text_or_none(manifest.get("archive_type")),
                _text_or_none(manifest.get("created_utc")),
                _text_or_none(manifest.get("dumper_version")),
                _first_int(identity, "card_id", "cardId"),
                _first_int(identity, "scenario_id", "scenarioId"),
                json.dumps(identity, ensure_ascii=False, separators=(",", ":")),
                json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                utc_now(),
            ),
        )
        row = self.connection.execute(
            "SELECT id FROM career_archives WHERE archive_key = ?", (archive_key,)
        ).fetchone()
        assert row is not None
        return int(row[0])

    def store_career_snapshot(
        self,
        *,
        archive_id: int,
        turn: int,
        revision: int,
        source_file_id: int,
        payload: Any,
        observed_at: str | None,
    ) -> bool:
        digest = payload_sha256(payload)
        previous = self.connection.execute(
            "SELECT payload_sha256 FROM career_snapshots WHERE archive_id = ? AND turn = ? AND revision = ?",
            (archive_id, int(turn), int(revision)),
        ).fetchone()
        changed = previous is None or str(previous[0]) != digest
        self.connection.execute(
            """
            INSERT INTO career_snapshots(
                archive_id, turn, revision, source_file_id, payload_sha256,
                payload_gzip, observed_at, imported_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(archive_id, turn, revision) DO UPDATE SET
                source_file_id = excluded.source_file_id,
                payload_sha256 = excluded.payload_sha256,
                payload_gzip = excluded.payload_gzip,
                observed_at = excluded.observed_at,
                imported_at = excluded.imported_at
            """,
            (
                archive_id,
                int(turn),
                int(revision),
                source_file_id,
                digest,
                compressed_payload(payload),
                observed_at,
                utc_now(),
            ),
        )
        return changed

    def store_career_artifact(
        self,
        *,
        archive_id: int,
        artifact_type: str,
        source_file_id: int,
        payload: Any,
    ) -> bool:
        digest = payload_sha256(payload)
        previous = self.connection.execute(
            "SELECT payload_sha256 FROM career_artifacts WHERE archive_id = ? AND artifact_type = ?",
            (archive_id, artifact_type),
        ).fetchone()
        changed = previous is None or str(previous[0]) != digest
        self.connection.execute(
            """
            INSERT INTO career_artifacts(
                archive_id, artifact_type, source_file_id, payload_sha256,
                payload_gzip, imported_at
            ) VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(archive_id, artifact_type) DO UPDATE SET
                source_file_id = excluded.source_file_id,
                payload_sha256 = excluded.payload_sha256,
                payload_gzip = excluded.payload_gzip,
                imported_at = excluded.imported_at
            """,
            (
                archive_id,
                artifact_type,
                source_file_id,
                digest,
                compressed_payload(payload),
                utc_now(),
            ),
        )
        return changed

    def store_document(
        self,
        *,
        document_type: str,
        source_file_id: int,
        payload: Any,
    ) -> bool:
        digest = payload_sha256(payload)
        previous = self.connection.execute(
            "SELECT payload_sha256 FROM account_documents WHERE document_type = ?",
            (document_type,),
        ).fetchone()
        changed = previous is None or str(previous[0]) != digest
        self.connection.execute(
            """
            INSERT INTO account_documents(
                document_type, source_file_id, payload_sha256, payload_gzip, imported_at
            ) VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(document_type) DO UPDATE SET
                source_file_id = excluded.source_file_id,
                payload_sha256 = excluded.payload_sha256,
                payload_gzip = excluded.payload_gzip,
                imported_at = excluded.imported_at
            """,
            (
                document_type,
                source_file_id,
                digest,
                compressed_payload(payload),
                utc_now(),
            ),
        )
        return changed

    def set_automatic_value(
        self,
        key: str,
        value: object,
        *,
        source: str,
        unit: str = "",
        note: str = "",
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO account_values(
                key, automatic_value, automatic_source, unit, note,
                automatic_updated_at
            ) VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                automatic_value = excluded.automatic_value,
                automatic_source = excluded.automatic_source,
                unit = CASE WHEN excluded.unit <> '' THEN excluded.unit ELSE account_values.unit END,
                note = CASE WHEN excluded.note <> '' THEN excluded.note ELSE account_values.note END,
                automatic_updated_at = excluded.automatic_updated_at
            """,
            (str(key), _json_scalar(value), str(source), str(unit), str(note), utc_now()),
        )

    def set_manual_value(
        self,
        key: str,
        value: object | None,
        *,
        unit: str = "",
        note: str = "",
    ) -> None:
        encoded = None if value is None else _json_scalar(value)
        self.connection.execute(
            """
            INSERT INTO account_values(key, manual_value, unit, note, manual_updated_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                manual_value = excluded.manual_value,
                unit = CASE WHEN excluded.unit <> '' THEN excluded.unit ELSE account_values.unit END,
                note = CASE WHEN excluded.note <> '' THEN excluded.note ELSE account_values.note END,
                manual_updated_at = excluded.manual_updated_at
            """,
            (str(key), encoded, str(unit), str(note), utc_now()),
        )

    def get_value(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM account_values WHERE key = ?", (str(key),)
        ).fetchone()
        if row is None:
            return None
        manual = _decode_scalar(row["manual_value"])
        automatic = _decode_scalar(row["automatic_value"])
        return {
            "key": str(row["key"]),
            "value": manual if row["manual_value"] is not None else automatic,
            "source": "manual" if row["manual_value"] is not None else row["automatic_source"],
            "manual_value": manual,
            "automatic_value": automatic,
            "automatic_source": row["automatic_source"],
            "unit": str(row["unit"] or ""),
            "note": str(row["note"] or ""),
            "manual_updated_at": row["manual_updated_at"],
            "automatic_updated_at": row["automatic_updated_at"],
        }

    def summary(self) -> AccountSummary:
        scalar = lambda sql: int(self.connection.execute(sql).fetchone()[0])
        return AccountSummary(
            trainee_cards=scalar("SELECT COUNT(*) FROM owned_trainees WHERE active = 1"),
            support_cards=scalar("SELECT COUNT(*) FROM owned_supports WHERE active = 1"),
            active_veterans=scalar("SELECT COUNT(*) FROM veterans WHERE active = 1"),
            historical_veterans=scalar("SELECT COUNT(*) FROM veterans"),
            team_stadium_captures=scalar("SELECT COUNT(*) FROM race_captures WHERE capture_kind = 'team_stadium'"),
            single_race_captures=scalar("SELECT COUNT(*) FROM race_captures WHERE capture_kind = 'single_race'"),
            career_archives=scalar("SELECT COUNT(*) FROM career_archives"),
            career_snapshots=scalar("SELECT COUNT(*) FROM career_snapshots"),
            documents=scalar("SELECT COUNT(*) FROM account_documents"),
            manual_values=scalar("SELECT COUNT(*) FROM account_values WHERE manual_value IS NOT NULL"),
        )

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()


def _int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_int(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = _int_or_none(payload.get(key))
        if value is not None:
            return value
    return None


def _text_or_none(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _json_scalar(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode_scalar(value: object) -> Any:
    if value is None:
        return None
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return value
