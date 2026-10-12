from __future__ import annotations

import multiprocessing
import pickle
import threading
import time
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from uma_legacy_linker.backend_process import (
    CANCELLED_MESSAGE,
    ERROR_MESSAGE,
    LOG_MESSAGE,
    PROGRESS_MESSAGE,
    RESULT_MESSAGE,
    TERMINAL_MESSAGES,
    ProcessTask,
    callback_kwargs,
    run_process_task,
)
from uma_legacy_linker.application import OperationCancelled


PROCESS_POLL_SECONDS = 0.05
PROCESS_CANCEL_GRACE_SECONDS = 1.0


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
            raise OperationCancelled("Task cancelled by the user.")

    def request_cancel(self, *, force: bool = False) -> None:
        del force
        self.cancel_event.set()

    @Slot()
    def run(self) -> None:
        def yield_to_ui() -> None:
            # CPU-bound Python scoring runs in a Qt pool thread. Explicitly
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
            kwargs = callback_kwargs(
                self.function,
                {
                    "logger": log,
                    "progress": progress,
                    "checkpoint": yield_to_ui,
                },
            )
            result = self.function(**kwargs)
        except OperationCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:  # backend exceptions are presented by the UI
            self.signals.error.emit(str(exc), traceback.format_exc())
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class ProcessFunctionWorker(QRunnable):
    """Supervise a CPU backend in an interpreter isolated from Qt's GIL."""

    def __init__(self, task: ProcessTask):
        super().__init__()
        self.task = task
        self.signals = WorkerSignals()
        self.cancel_event = threading.Event()
        self._force_stop = threading.Event()
        self._process_lock = threading.Lock()
        self._process: multiprocessing.process.BaseProcess | None = None
        self.setAutoDelete(True)

    def request_cancel(self, *, force: bool = False) -> None:
        self.cancel_event.set()
        if not force:
            return
        self._force_stop.set()
        with self._process_lock:
            process = self._process
            if process is not None:
                try:
                    if process.is_alive():
                        process.terminate()
                except (AssertionError, ValueError):
                    pass

    def _relay_message(self, message: object) -> bool:
        if not isinstance(message, tuple) or len(message) != 2:
            raise RuntimeError("Invalid backend IPC message.")
        kind, payload = message
        if kind == LOG_MESSAGE:
            self.signals.log.emit(str(payload))
        elif kind == PROGRESS_MESSAGE:
            if not isinstance(payload, tuple) or len(payload) != 2:
                raise RuntimeError("Invalid backend IPC progress message.")
            self.signals.progress.emit(int(payload[0]), str(payload[1]))
        elif kind == RESULT_MESSAGE:
            self.signals.result.emit(payload)
        elif kind == ERROR_MESSAGE:
            if not isinstance(payload, tuple) or len(payload) != 2:
                raise RuntimeError("Invalid backend IPC error message.")
            self.signals.error.emit(str(payload[0]), str(payload[1]))
        elif kind == CANCELLED_MESSAGE:
            self.signals.cancelled.emit()
        else:
            raise RuntimeError(f"Unknown backend IPC message type: {kind!r}")
        return kind in TERMINAL_MESSAGES

    @Slot()
    def run(self) -> None:
        process: multiprocessing.process.BaseProcess | None = None
        receiver = None
        sender = None
        terminal_received = False
        cancel_started: float | None = None
        try:
            # Fail before starting a child when a page accidentally captures a
            # widget, lock or closure instead of a serialisable request.
            pickle.dumps(self.task, protocol=pickle.HIGHEST_PROTOCOL)
            if self.cancel_event.is_set():
                self.signals.cancelled.emit()
                terminal_received = True
                return

            context = multiprocessing.get_context("spawn")
            receiver, sender = context.Pipe(duplex=False)
            child_cancel_event = context.Event()
            process = context.Process(
                target=run_process_task,
                args=(self.task, sender, child_cancel_event),
                name="UmaLegacyLinkerBackend",
            )
            with self._process_lock:
                self._process = process
            process.start()
            sender.close()
            sender = None

            while True:
                if self.cancel_event.is_set():
                    child_cancel_event.set()
                    if cancel_started is None:
                        cancel_started = time.monotonic()
                    grace_expired = (
                        time.monotonic() - cancel_started
                        >= PROCESS_CANCEL_GRACE_SECONDS
                    )
                    if process.is_alive() and (
                        self._force_stop.is_set() or grace_expired
                    ):
                        process.terminate()

                if receiver.poll(PROCESS_POLL_SECONDS):
                    try:
                        message = receiver.recv()
                    except (EOFError, BrokenPipeError):
                        break
                    terminal_received = self._relay_message(message) or terminal_received
                    # run_process_task closes its endpoint immediately after a
                    # terminal protocol message. Polling again can raise
                    # BrokenPipeError on Windows (WinError 109).
                    if terminal_received:
                        break
                    continue
                if not process.is_alive():
                    while receiver.poll():
                        try:
                            message = receiver.recv()
                        except (EOFError, BrokenPipeError):
                            break
                        terminal_received = (
                            self._relay_message(message) or terminal_received
                        )
                    break

            process.join()
            if not terminal_received:
                if self.cancel_event.is_set():
                    self.signals.cancelled.emit()
                else:
                    self.signals.error.emit(
                        "The calculation process stopped unexpectedly "
                        f"(exit code {process.exitcode}).",
                        "No backend diagnostic was received.",
                    )
        except Exception as exc:
            if not terminal_received:
                self.signals.error.emit(str(exc) or type(exc).__name__, traceback.format_exc())
        finally:
            if sender is not None:
                sender.close()
            if receiver is not None:
                receiver.close()
            with self._process_lock:
                self._process = None
            if process is not None:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=1.0)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=1.0)
                if not process.is_alive():
                    process.close()
            self.signals.finished.emit()
