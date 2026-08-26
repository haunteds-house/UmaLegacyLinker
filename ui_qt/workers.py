from __future__ import annotations

import inspect
import threading
import time
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from ui_qt.core import OperationCancelled


class WorkerSignals(QObject):
    progress = Signal(int, str)
    log = Signal(str)
    result = Signal(object)
    error = Signal(str, str)
    cancelled = Signal()
    finished = Signal()


class FunctionWorker(QRunnable):
    """Run a backend operation without blocking Qt's event loop.

    Logger and progress callbacks remain cancellation points. CPU-bound
    backends can additionally accept an independent ``checkpoint`` callback,
    allowing responsive cancellation without emitting UI noise.
    """

    def __init__(self, function: Callable[..., Any]):
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()
        self.cancel_event = threading.Event()
        self.setAutoDelete(True)

    def _checkpoint(self) -> None:
        if self.cancel_event.is_set():
            raise OperationCancelled("Tâche annulée par l'utilisateur.")

    @Slot()
    def run(self) -> None:
        def yield_to_ui() -> None:
            # CPU-bound Python scoring runs in a Qt pool thread.  Explicitly
            # yield at backend checkpoints so the GUI thread can process the
            # Cancel click promptly even under sustained scoring load.
            time.sleep(0)
            self._checkpoint()

        def log(message: str) -> None:
            self._checkpoint()
            self.signals.log.emit(message)
            yield_to_ui()

        def progress(value: int, message: str) -> None:
            self._checkpoint()
            self.signals.progress.emit(value, message)
            yield_to_ui()

        try:
            kwargs: dict[str, Any] = {"logger": log, "progress": progress}
            parameters = inspect.signature(self.function).parameters
            if "checkpoint" in parameters or any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            ):
                kwargs["checkpoint"] = yield_to_ui
            result = self.function(**kwargs)
        except OperationCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:  # backend exceptions are presented by the UI
            self.signals.error.emit(str(exc), traceback.format_exc())
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
