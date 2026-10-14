from __future__ import annotations

import inspect
import traceback
from dataclasses import dataclass
from typing import Any, Callable


LOG_MESSAGE = "log"
PROGRESS_MESSAGE = "progress"
RESULT_MESSAGE = "result"
ERROR_MESSAGE = "error"
CANCELLED_MESSAGE = "cancelled"
TERMINAL_MESSAGES = frozenset({RESULT_MESSAGE, ERROR_MESSAGE, CANCELLED_MESSAGE})


@dataclass(frozen=True)
class ProcessTask:
    """A picklable backend operation that must run outside the Qt process."""

    operation: Callable[..., Any]

    def __post_init__(self) -> None:
        if not callable(self.operation):
            raise TypeError("ProcessTask.operation must be callable")


class ProcessTaskCancelled(Exception):
    """Stop one backend process at a cooperative checkpoint."""


def _accepts_checkpoint(operation: Callable[..., Any]) -> bool:
    try:
        parameters = inspect.signature(operation).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == "checkpoint"
        or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


def run_process_task(task: ProcessTask, connection: Any, cancel_event: Any) -> None:
    """Execute one task in a spawned interpreter and report over a pipe.

    This module intentionally has no Qt dependency. The child owns backend
    callbacks and serialises plain protocol messages; only the supervising
    worker in the GUI process emits Qt signals.
    """

    def checkpoint() -> None:
        if cancel_event.is_set():
            raise ProcessTaskCancelled('Task cancelled by the user.')

    def log(message: str) -> None:
        checkpoint()
        connection.send((LOG_MESSAGE, str(message)))

    def progress(value: int, message: str) -> None:
        checkpoint()
        connection.send((PROGRESS_MESSAGE, (int(value), str(message))))

    try:
        checkpoint()
        kwargs: dict[str, Any] = {"logger": log, "progress": progress}
        if _accepts_checkpoint(task.operation):
            kwargs["checkpoint"] = checkpoint
        result = task.operation(**kwargs)
        checkpoint()
        connection.send((RESULT_MESSAGE, result))
    except ProcessTaskCancelled:
        connection.send((CANCELLED_MESSAGE, None))
    except Exception as exc:
        message = str(exc) or type(exc).__name__
        connection.send((ERROR_MESSAGE, (message, traceback.format_exc())))
    finally:
        connection.close()
