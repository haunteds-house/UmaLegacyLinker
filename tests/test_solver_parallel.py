import json
import multiprocessing as mp
import os
from pathlib import Path
import time

import pytest

from tests.solver_fixtures import real_file_fixture
from tests.solver_process_support import pair_job, nested_search
from uma_legacy_linker.backend_process import ProcessTaskCancelled
from uma_legacy_linker.parent_optimizer import optimize_parents
from uma_legacy_linker.solver_parallel import parallel_pair_rows
from uma_legacy_linker.solver_runtime import SolverRuntime, solver_scope, current_runtime


@pytest.mark.parametrize("failure", ["cancel", "exception", "crash"])
def test_parallel_failure_reaps_all_workers(tmp_path, failure):
    args = real_file_fixture(tmp_path)
    resolver, context, members, pairs = pair_job(args)
    runtime = SolverRuntime(True, workers=2)
    injected = False
    if failure == "exception":
        context.pop("surface")  # An evaluator error must come back from the child.

    def checkpoint():
        nonlocal injected
        stats = runtime.stats.get("parallel", {}).get("local_parent", {})
        if len(stats.get("child_pids", [])) == 2 and not injected:
            injected = True
            if failure == "cancel":
                raise ProcessTaskCancelled("cancel test")
            if failure == "crash":
                next(p for p in mp.active_children() if p.pid in stats["child_pids"]).terminate()

    try:
        with solver_scope(runtime), pytest.raises(ProcessTaskCancelled if failure == "cancel" else RuntimeError):
            parallel_pair_rows("local_parent", context, members, members, pairs,
                               checkpoint=checkpoint, logger=lambda _: None)
        stats = runtime.stats["parallel"]["local_parent"]
        assert stats["reaped"]
        assert not set(stats["child_pids"]) & {p.pid for p in mp.active_children()}
    finally:
        resolver.close()


def _pid_running(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists():
        try:
            return stat.read_text().split(")", 1)[1].strip().split()[0] != "Z"
        except FileNotFoundError:
            return False
    return True


@pytest.mark.parametrize("terminate_owner", [False, True])
def test_pool_can_run_inside_spawned_backend_and_cannot_outlive_it(tmp_path, terminate_owner):
    args = real_file_fixture(tmp_path, count=12)
    spawn = mp.get_context("spawn")
    parent, child = spawn.Pipe()
    backend = spawn.Process(target=nested_search, args=(args, child, terminate_owner))
    backend.start()
    child.close()
    pids = []
    try:
        assert parent.poll(15), "Backend did not start solver children"
        kind, pids = parent.recv()
        assert kind == "children" and len(pids) == 2
        if terminate_owner:
            backend.terminate()
        else:
            assert parent.poll(15), "Nested solver did not finish"
            kind, stats, path, qt_modules = parent.recv()
            assert kind == "done" and not qt_modules and Path(path).is_file()
            assert stats["parallel"]["local_parent"]["reaped"]
        backend.join(5)
        assert not backend.is_alive()
        deadline = time.monotonic() + 10
        while any(_pid_running(pid) for pid in pids) and time.monotonic() < deadline:
            time.sleep(.025)
        assert not any(_pid_running(pid) for pid in pids), "Orphan solver process"
    finally:
        parent.close()
        if backend.is_alive():
            backend.terminate()
            backend.join(5)
        backend.close()
