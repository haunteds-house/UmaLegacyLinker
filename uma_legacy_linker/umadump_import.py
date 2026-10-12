"""Import official umadump outputs into the persistent account database."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from uma_legacy_linker.account_store import AccountStore, AccountSummary

TURN_PATTERN = re.compile(r"turn_(?P<turn>\d+)_(?P<revision>\d+)\.json$", re.IGNORECASE)
TT_TIMESTAMP = re.compile(r"TT-(?P<date>\d{8})_(?P<time>\d{6})_(?P<millis>\d{3})\.json$", re.IGNORECASE)
SINGLE_DATE = re.compile(r"-(?P<date>\d{8})\.json$", re.IGNORECASE)

STATIC_EXPORTS = {
    "card_data.json": "owned_trainees",
    "support_card_data.json": "owned_supports",
    "trained_chara_data.json": "veterans",
}
MISC_EXPORTS = {
    "trophy_data.json": "trophies",
    "trophy_data_limited.json": "trophies_limited",
    "event_data.json": "events",
    "honor_data.json": "honors",
    "talk_gallery_data.json": "talk_gallery",
}


@dataclass
class ImportReport:
    source_root: Path
    database_path: Path
    scanned_files: int = 0
    imported_files: int = 0
    unchanged_files: int = 0
    ignored_files: int = 0
    failed_files: int = 0
    trainee_cards: int = 0
    support_cards: int = 0
    veterans: int = 0
    race_captures_added: int = 0
    career_snapshots_changed: int = 0
    career_artifacts_changed: int = 0
    documents_changed: int = 0
    errors: list[str] = field(default_factory=list)
    summary: AccountSummary | None = None


class UmadumpImportError(RuntimeError):
    pass


def locate_umadump_root(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    if not candidate.is_dir():
        raise UmadumpImportError(f"umadump directory not found: {candidate}")
    if _looks_like_root(candidate):
        return candidate
    children = [item for item in candidate.iterdir() if item.is_dir() and _looks_like_root(item)]
    if len(children) == 1:
        return children[0]
    return candidate


def _looks_like_root(path: Path) -> bool:
    return any(
        (path / name).is_file()
        for name in ("trained_chara_data.json", "card_data.json", "support_card_data.json")
    ) or (path / "race_replays").is_dir() or (path / "career_data").is_dir()


def import_umadump_directory(
    source_root: str | Path,
    database_path: str | Path | None = None,
    *,
    logger: Callable[[str], None] | None = None,
    progress: Callable[[int, str], None] | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> ImportReport:
    """Import one umadump output tree.

    ``logger``, ``progress`` and ``checkpoint`` match the desktop worker
    callback contract. They are optional so the importer remains usable from
    tests, the CLI and the polling watcher without Qt.
    """
    root = locate_umadump_root(source_root)
    log = logger or (lambda _message: None)
    report_progress = progress or (lambda _value, _message: None)
    check = checkpoint or (lambda: None)
    store = AccountStore(database_path)
    report = ImportReport(source_root=root, database_path=store.path)
    try:
        report_progress(5, "Reading collection exports…")
        check()
        _import_static_exports(store, root, report, log, check)
        report_progress(30, "Reading account documents…")
        check()
        _import_misc_exports(store, root, report, log, check)
        report_progress(45, "Reading race captures…")
        check()
        _import_race_replays(store, root, report, log, check)
        report_progress(70, "Reading career archives…")
        check()
        _import_careers(store, root, report, log, check)
        report_progress(92, "Saving account database…")
        check()
        store.commit()
        report.summary = store.summary()
        report_progress(100, "Account import complete.")
        return report
    except Exception:
        store.rollback()
        raise
    finally:
        store.close()


def _import_static_exports(
    store: AccountStore,
    root: Path,
    report: ImportReport,
    log: Callable[[str], None],
    checkpoint: Callable[[], None],
) -> None:
    for filename, kind in STATIC_EXPORTS.items():
        checkpoint()
        path = root / filename
        if not path.is_file():
            continue
        report.scanned_files += 1
        result = _load_changed_json(store, path, root, kind, report)
        if result is None:
            continue
        payload, source_id = result
        rows = payload if isinstance(payload, list) else []
        if kind == "owned_trainees":
            report.trainee_cards = store.replace_owned_trainees(rows, source_file_id=source_id)
        elif kind == "owned_supports":
            report.support_cards = store.replace_owned_supports(rows, source_file_id=source_id)
        elif kind == "veterans":
            report.veterans = store.replace_veterans(rows, source_file_id=source_id)
        log(f"Imported {filename}: {len(rows)} row(s).")


def _import_misc_exports(
    store: AccountStore,
    root: Path,
    report: ImportReport,
    log: Callable[[str], None],
    checkpoint: Callable[[], None],
) -> None:
    for filename, document_type in MISC_EXPORTS.items():
        checkpoint()
        path = root / filename
        if not path.is_file():
            continue
        report.scanned_files += 1
        result = _load_changed_json(store, path, root, f"document:{document_type}", report)
        if result is None:
            continue
        payload, source_id = result
        if store.store_document(
            document_type=document_type,
            source_file_id=source_id,
            payload=payload,
        ):
            report.documents_changed += 1
        log(f"Imported {filename}.")


def _import_race_replays(
    store: AccountStore,
    root: Path,
    report: ImportReport,
    log: Callable[[str], None],
    checkpoint: Callable[[], None],
) -> None:
    replay_root = root / "race_replays"
    categories = (
        (replay_root / "team_stadium", "team_stadium"),
        (replay_root / "single_race", "single_race"),
    )
    for directory, kind in categories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            checkpoint()
            report.scanned_files += 1
            result = _load_changed_json(store, path, root, f"race:{kind}", report)
            if result is None:
                continue
            payload, source_id = result
            metadata = _race_metadata(kind, payload)
            _capture_id, created = store.store_race_capture(
                capture_kind=kind,
                source_file_id=source_id,
                payload=payload,
                observed_at=_observed_at_from_name(path),
                metadata=metadata,
            )
            if created:
                report.race_captures_added += 1
            log(f"Imported {kind} capture: {path.name}.")


def _import_careers(
    store: AccountStore,
    root: Path,
    report: ImportReport,
    log: Callable[[str], None],
    checkpoint: Callable[[], None],
) -> None:
    career_root = root / "career_data"
    if not career_root.is_dir():
        return
    for archive_dir in sorted(path for path in career_root.iterdir() if path.is_dir()):
        checkpoint()
        manifest_path = archive_dir / "manifest.json"
        manifest: dict[str, Any] = {}
        if manifest_path.is_file():
            report.scanned_files += 1
            result = _load_changed_json(store, manifest_path, root, "career:manifest", report)
            if result is not None:
                payload, _source_id = result
                if isinstance(payload, dict):
                    manifest = payload
            else:
                try:
                    manifest = _read_json(manifest_path)
                except (OSError, json.JSONDecodeError):
                    manifest = {}
        archive_key = archive_dir.name
        archive_id = store.upsert_career_archive(
            archive_key=archive_key,
            source_dir=archive_dir,
            manifest=manifest,
        )

        turns_dir = archive_dir / "turns"
        if turns_dir.is_dir():
            for path in sorted(turns_dir.glob("turn_*.json")):
                checkpoint()
                match = TURN_PATTERN.search(path.name)
                if not match:
                    report.ignored_files += 1
                    continue
                report.scanned_files += 1
                result = _load_changed_json(store, path, root, "career:turn", report)
                if result is None:
                    continue
                payload, source_id = result
                if store.store_career_snapshot(
                    archive_id=archive_id,
                    turn=int(match.group("turn")),
                    revision=int(match.group("revision")),
                    source_file_id=source_id,
                    payload=payload,
                    observed_at=_mtime_iso(path),
                ):
                    report.career_snapshots_changed += 1

        for filename, artifact_type in (
            ("events.json", "events"),
            ("log.json", "log"),
            ("veteran.json", "veteran"),
        ):
            checkpoint()
            path = archive_dir / filename
            if not path.is_file():
                continue
            report.scanned_files += 1
            result = _load_changed_json(store, path, root, f"career:{artifact_type}", report)
            if result is None:
                continue
            payload, source_id = result
            if store.store_career_artifact(
                archive_id=archive_id,
                artifact_type=artifact_type,
                source_file_id=source_id,
                payload=payload,
            ):
                report.career_artifacts_changed += 1
        log(f"Indexed career archive: {archive_key}.")


def _load_changed_json(
    store: AccountStore,
    path: Path,
    root: Path,
    kind: str,
    report: ImportReport,
) -> tuple[Any, int] | None:
    try:
        stat = path.stat()
        if store.source_stat_unchanged(
            path, size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns
        ):
            report.unchanged_files += 1
            return None
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if not store.source_needs_import(path, digest):
            # The file was touched/rewritten without changing its contents.
            # Refresh the stat signature so daemon polling stays cheap.
            store.record_source(
                path,
                source_root=root,
                kind=kind,
                sha256=digest,
                size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
            )
            report.unchanged_files += 1
            return None
        payload = json.loads(raw.decode("utf-8-sig"))
        source_id = store.record_source(
            path,
            source_root=root,
            kind=kind,
            sha256=digest,
            size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
        )
        report.imported_files += 1
        return payload, source_id
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        report.failed_files += 1
        report.errors.append(f"{path}: {exc}")
        return None


def _race_metadata(kind: str, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if kind == "team_stadium":
        results = payload.get("race_result_array")
        scores = [
            int(row.get("team_total_score") or 0)
            for row in results or []
            if isinstance(row, dict)
        ]
        return {
            "support_card_bonus": _safe_int(payload.get("support_card_bonus")),
            "team_total_score": sum(scores) if scores else None,
            "race_count": len(results) if isinstance(results, list) else 0,
        }
    return {
        "has_race_scenario": bool(payload.get("race_scenario")),
        "practice_race_id": _safe_int(payload.get("practice_race_id")),
    }


def _observed_at_from_name(path: Path) -> str:
    # Filename timestamps are generated in the user's local clock but do not
    # include an offset. The filesystem mtime is an unambiguous instant, so use
    # it for persistence and leave filename interpretation to presentation.
    return _mtime_iso(path)


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(
        timespec="seconds"
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _safe_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
