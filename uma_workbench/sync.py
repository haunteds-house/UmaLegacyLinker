from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import urllib.request
from pathlib import Path

from .core import MAX_JSON

RELEASE_PAGE = "https://github.com/Werseter/umadump/releases"
RELEASE_API = "https://api.github.com/repos/Werseter/umadump/releases/latest"


class ExportWatcher:
    """Monitor JSON files only. Failed or partial writes are retried next poll."""

    def __init__(self, store, folder, callback, interval=3):
        self.store = store
        self.folder = Path(folder).resolve()
        if not self.folder.is_dir():
            raise ValueError("Select an existing umadump output folder")
        self.callback = callback
        self.interval = interval
        self.stopped = threading.Event()
        self.seen = {}
        self.thread = threading.Thread(target=self.run, daemon=True, name="export-watcher")

    def start(self):
        self.thread.start()

    def stop(self):
        self.stopped.set()

    def poll_once(self):
        summary = {"imported": 0, "unchanged": 0, "ignored": 0, "errors": [], "warnings": []}
        for path in sorted(self.folder.rglob("*.json")):
            if self.stopped.is_set():
                break
            if not path.resolve().is_relative_to(self.folder):
                continue
            try:
                before = path.stat()
                signature = (before.st_mtime_ns, before.st_size)
                if self.seen.get(path) == signature:
                    continue
                if before.st_size > MAX_JSON:
                    raise ValueError("JSON exceeds the size limit")
                contents = path.read_bytes()
                after = path.stat()
                if signature != (after.st_mtime_ns, after.st_size):
                    continue
                status, warnings = self.store.import_bytes(str(path), contents)
                summary[status] += 1
                summary["warnings"].extend(warnings)
                self.seen[path] = signature
            except (OSError, ValueError, KeyError, TypeError) as exc:
                summary["errors"].append(f"{path.name}: {exc}")
        return summary

    def run(self):
        while not self.stopped.is_set():
            try:
                result = self.poll_once()
                if result["imported"] or result["errors"] or result["warnings"]:
                    self.callback(result)
            except Exception as exc:
                self.callback({"imported": 0, "errors": [str(exc)], "warnings": []})
            self.stopped.wait(self.interval)


def launch_umadump(executable, output_folder):
    """Run the user's upstream executable, without patching or wrapping its reader."""
    if os.name != "nt":
        raise ValueError("Live umadump launching is available on Windows")
    path = Path(executable).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".exe":
        raise ValueError("Select the umadump.exe you downloaded from Werseter's releases")
    output = Path(output_folder).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen([str(path), "--rerun-mode", "daemon", "--poll-interval", "2"],
                            cwd=str(output), shell=False,
                            creationflags=subprocess.CREATE_NEW_CONSOLE)


def check_release(executable=None):
    request = urllib.request.Request(RELEASE_API, headers={"User-Agent": "UmaWorkbench/0.1.0", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        contents = response.read(2 * 1024 * 1024 + 1)
    if len(contents) > 2 * 1024 * 1024:
        raise ValueError("Release response exceeds the size limit")
    data = json.loads(contents)
    assets = [a for a in data.get("assets", []) if a.get("name") == "umadump.exe"]
    digest = assets[0].get("digest") if assets else None
    local_digest = None
    if executable and Path(executable).is_file():
        local_digest = "sha256:" + hashlib.sha256(Path(executable).read_bytes()).hexdigest()
    return {"tag": data["tag_name"], "page": RELEASE_PAGE, "upstream_digest": digest,
            "local_digest": local_digest,
            "matches_latest": local_digest == digest if digest and local_digest else None,
            "note": "Release check only. Download and replace umadump through its upstream releases."}
