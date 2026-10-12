"""Polling watcher for official umadump daemon output directories.

This module never attaches to or modifies the game process. It only observes
files written by an independently installed/running umadump instance.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from uma_legacy_linker.umadump_import import ImportReport, import_umadump_directory


@dataclass(frozen=True)
class WatchIteration:
    started_at: float
    finished_at: float
    report: ImportReport


class UmadumpWatcher:
    def __init__(
        self,
        source_root: str | Path,
        database_path: str | Path | None = None,
        *,
        poll_interval: float = 2.0,
        logger: Callable[[str], None] | None = None,
        on_iteration: Callable[[WatchIteration], None] | None = None,
    ) -> None:
        self.source_root = Path(source_root).expanduser().resolve()
        self.database_path = Path(database_path).expanduser().resolve() if database_path else None
        self.poll_interval = max(0.5, float(poll_interval))
        self.logger = logger or (lambda _message: None)
        self.on_iteration = on_iteration

    def scan_once(self) -> ImportReport:
        return import_umadump_directory(
            self.source_root,
            self.database_path,
            logger=self.logger,
        )

    def run(self, stop_event: threading.Event | None = None) -> None:
        stop = stop_event or threading.Event()
        while not stop.is_set():
            started = time.time()
            report = self.scan_once()
            finished = time.time()
            if self.on_iteration is not None:
                self.on_iteration(WatchIteration(started, finished, report))
            stop.wait(self.poll_interval)
