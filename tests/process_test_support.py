from __future__ import annotations

import os
import sys
import time
from typing import Any, Callable


def report_process_state(
    *,
    logger: Callable[[str], None],
    progress: Callable[[int, str], None],
    checkpoint: Callable[[], None],
) -> dict[str, Any]:
    from uma_legacy_linker.application import APP_NAME

    checkpoint()
    logger("child-log")
    progress(37, "child-progress")
    return {
        "pid": os.getpid(),
        "app_name": APP_NAME,
        "qt_modules": sorted(
            name for name in sys.modules if name == "PySide6" or name.startswith("PySide6.")
        ),
    }


def fail_with_diagnostic(
    *,
    logger: Callable[[str], None],
    progress: Callable[[int, str], None],
) -> None:
    del logger, progress
    raise RuntimeError("backend exploded")


def block_without_checkpoint(
    *,
    logger: Callable[[str], None],
    progress: Callable[[int, str], None],
) -> None:
    del progress
    logger("child-blocking")
    time.sleep(30.0)
