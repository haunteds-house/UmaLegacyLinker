from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any


def previous_output_path(path: str | Path) -> Path:
    resolved = Path(path)
    return resolved.with_name(f"{resolved.stem}.prev{resolved.suffix}")


def write_text_with_history(
    path: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    """Atomically replace one output while retaining exactly one predecessor."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    history_temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            stream.write(content)
            temporary = Path(stream.name)
        if destination.is_file():
            with tempfile.NamedTemporaryFile(
                dir=destination.parent,
                prefix=f".{destination.name}.history.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                history_temporary = Path(stream.name)
            shutil.copy2(destination, history_temporary)
            history_temporary.replace(previous_output_path(destination))
        temporary.replace(destination)
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if history_temporary is not None:
            history_temporary.unlink(missing_ok=True)


def write_json_with_history(path: str | Path, payload: Any) -> Path:
    return write_text_with_history(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
