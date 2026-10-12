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


def callback_kwargs(
    operation: Callable[..., Any],
    callbacks: dict[str, Callable[..., Any]],
) -> dict[str, Callable[..., Any]]:
    """Return only worker callbacks accepted by ``operation``.

    UI/background workers provide logger, progress and checkpoint hooks, but
    lightweight operations are not required to implement every hook. This
    keeps shared worker infrastructure from imposing accidental keyword
    arguments on otherwise valid callables.
    """
    try:
        parameters = inspect.signature(operation).parameters.values()
    except (TypeError, ValueError):
        # Builtins and opaque callables are rare in backend work. Preserve the
        # historical callback contract when Python cannot inspect a signature.
        return dict(callbacks)
    parameter_list = tuple(parameters)
    accepts_extra = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameter_list
    )
    accepted_names = {parameter.name for parameter in parameter_list}
    return {
        name: callback
        for name, callback in callbacks.items()
        if accepts_extra or name in accepted_names
    }


def run_process_task(task: ProcessTask, connection: Any, cancel_event: Any) -> None:
    """Execute one task in a spawned interpreter and report over a pipe.

    This module intentionally has no Qt dependency. The child owns backend
    callbacks and serialises plain protocol messages; only the supervising
    worker in the GUI process emits Qt signals.
    """

    def checkpoint() -> None:
        if cancel_event.is_set():
            raise ProcessTaskCancelled("Task cancelled by the user.")

    def log(message: str) -> None:
        checkpoint()
        connection.send((LOG_MESSAGE, str(message)))

    def progress(value: int, message: str) -> None:
        checkpoint()
        connection.send((PROGRESS_MESSAGE, (int(value), str(message))))

    try:
        checkpoint()
        kwargs = callback_kwargs(
            task.operation,
            {
                "logger": log,
                "progress": progress,
                "checkpoint": checkpoint,
            },
        )
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
