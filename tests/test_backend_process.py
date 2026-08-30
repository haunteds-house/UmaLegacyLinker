from __future__ import annotations

import multiprocessing
import os
import pickle
from functools import partial
from pathlib import Path
from typing import Any

import pytest

from backend_process import (
    CANCELLED_MESSAGE,
    ERROR_MESSAGE,
    LOG_MESSAGE,
    PROGRESS_MESSAGE,
    RESULT_MESSAGE,
    ProcessTask,
    run_process_task,
)
from tests.process_test_support import fail_with_diagnostic, report_process_state
from ui_qt.core import (
    OnlineSearchRequest,
    OptimizationRequest,
    TransferRequest,
    run_online_search,
    run_optimization,
    run_transfer_analysis,
)


def _spawn_messages(
    task: ProcessTask, *, cancelled_before_start: bool = False
) -> tuple[list[tuple[str, Any]], int]:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    cancel_event = context.Event()
    if cancelled_before_start:
        cancel_event.set()
    process = context.Process(
        target=run_process_task,
        args=(task, sender, cancel_event),
    )
    process.start()
    sender.close()
    messages: list[tuple[str, Any]] = []
    try:
        while True:
            if receiver.poll(5.0):
                try:
                    messages.append(receiver.recv())
                except EOFError:
                    break
                continue
            if not process.is_alive():
                break
            pytest.fail("spawned backend did not answer within five seconds")
    finally:
        receiver.close()
        process.join(timeout=5.0)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5.0)
    return messages, int(process.exitcode or 0)


def test_spawned_task_relays_callbacks_and_keeps_qt_out_of_child() -> None:
    messages, exit_code = _spawn_messages(ProcessTask(report_process_state))

    assert exit_code == 0
    assert messages[0] == (LOG_MESSAGE, "child-log")
    assert messages[1] == (PROGRESS_MESSAGE, (37, "child-progress"))
    kind, result = messages[2]
    assert kind == RESULT_MESSAGE
    assert result["pid"] != os.getpid()
    assert result["app_name"] == "Uma Legacy Linker"
    assert result["qt_modules"] == []


def test_spawned_task_returns_backend_traceback() -> None:
    messages, exit_code = _spawn_messages(ProcessTask(fail_with_diagnostic))

    assert exit_code == 0
    assert len(messages) == 1
    kind, payload = messages[0]
    assert kind == ERROR_MESSAGE
    assert payload[0] == "backend exploded"
    assert "RuntimeError: backend exploded" in payload[1]


def test_spawned_task_honours_cancellation_before_work() -> None:
    messages, exit_code = _spawn_messages(
        ProcessTask(report_process_state), cancelled_before_start=True
    )

    assert exit_code == 0
    assert messages == [(CANCELLED_MESSAGE, None)]


def test_all_heavy_desktop_requests_are_picklable_process_tasks() -> None:
    root = Path("fixture")
    tasks = (
        ProcessTask(
            partial(
                run_optimization,
                OptimizationRequest(
                    master_path=root / "master.mdb",
                    veterans_json_path=root / "veterans.json",
                    output_dir=root / "output",
                    ace_card_id=1,
                    future_parent_card_id=2,
                    surface="turf",
                    distance="mile",
                    style="pace",
                ),
            )
        ),
        ProcessTask(
            partial(
                run_online_search,
                OnlineSearchRequest(
                    search_mode="parent",
                    master_path=root / "master.mdb",
                    veterans_json_path=root / "veterans.json",
                    output_dir=root / "output",
                    ace_card_id=1,
                    target_parent_card_id=None,
                    fixed_local_id=None,
                    automatic_pairs=True,
                    local_pool_size=10,
                    remote_pool_size=10,
                    surface="turf",
                    distance="mile",
                    style="pace",
                ),
            )
        ),
        ProcessTask(
            partial(
                run_transfer_analysis,
                TransferRequest(
                    master_path=root / "master.mdb",
                    veterans_json_path=root / "veterans.json",
                    output_dir=root / "output",
                ),
            )
        ),
    )

    for task in tasks:
        restored = pickle.loads(pickle.dumps(task))
        assert restored.operation.func is task.operation.func
        assert restored.operation.args == task.operation.args
        assert restored.operation.keywords == task.operation.keywords


def test_process_boundary_and_frozen_entrypoint_are_explicit() -> None:
    backend_source = Path("backend_process.py").read_text(encoding="utf-8")
    search_source = Path("ui_qt/pages_search.py").read_text(encoding="utf-8")
    transfer_source = Path("ui_qt/pages_transfer.py").read_text(encoding="utf-8")
    data_source = Path("ui_qt/pages_home_data.py").read_text(encoding="utf-8")
    entrypoint_source = Path("qt_app.py").read_text(encoding="utf-8")

    assert "PySide6" not in backend_source
    assert "ui_qt" not in backend_source
    assert search_source.count("ProcessTask(partial(") == 2
    assert transfer_source.count("ProcessTask(partial(") == 1
    assert "ProcessTask" not in data_source
    assert "isinstance(operation, ProcessTask)" in Path(
        "ui_qt/main_window.py"
    ).read_text(encoding="utf-8")
    assert "freeze_support()" in entrypoint_source
