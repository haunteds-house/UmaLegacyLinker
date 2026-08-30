# Performance and process isolation

Uma Legacy Linker runs local lineage optimisation, uma.moe pairing and Transfer
Helper analysis in a spawned backend process. Qt and every widget remain in the
GUI process; the child imports only the GUI-independent workflow and scoring
modules, so it owns a separate Python interpreter and GIL.

A lightweight `QRunnable` remains in the GUI process solely to supervise a
one-way IPC pipe. It converts the child's typed log, progress, result, error and
cancellation messages into the existing Qt signals. Requests and results must
therefore remain picklable; `ProcessTask` performs a serialisation preflight
before the child starts. Linking, extraction and catalogue generation are
I/O-oriented and continue to use the original thread worker.

This is process isolation, not multicore scoring: one heavy desktop operation
still runs deterministically and sequentially in one child. It removes the
backend's GIL from the Qt process without changing formulas, scores or ordering.

## Cooperative cancellation budget

Parent optimisation uses one monotonic `CooperativeCheckpoint` per search. Hot
loops may call it on every meaningful iteration, but it invokes the child
process callback only when 10 ms have elapsed. That callback checks the shared
cancellation event; the scoring engine neither sleeps nor communicates over IPC
on every iteration.

The same checkpoint instance, and therefore the same deadline, is propagated
through local and uma.moe pair loops, branch evaluation, the five main scoring
components and G1 planning. This replaces the former `processed_pairs % 32`
policy, whose latency depended on the variable cost of 32 complete pairs.

The 10 ms interval is retained as a cooperative cancellation budget inside the
child. It no longer tries to schedule the GUI thread: the two processes do not
share a GIL. New CPU-heavy loops should still accept or reuse the checkpoint so
Cancel can stop cleanly. The supervisor propagates cancellation through a
process-safe event and terminates an uncooperative child after a short grace
period. Checkpoint calls must remain score-neutral.

The pre-change Windows freeze probe recorded 9 heartbeat stalls without resize
(1,772.7 ms median; 29,135.6 ms maximum) and 3 during resize (3,047.1 ms median;
54,950.4 ms maximum). A first replay with timed thread checkpoints still showed
multi-second stalls, proving that cooperative `time.sleep(0)` could not provide
a GUI-latency guarantee under the shared GIL. Replay the same probe against the
process-isolated build; heartbeat stalls now measure GUI/OS behaviour rather
than Python scoring contention.

## Main hotspots

1. Final parent-pair searches: Cartesian products of pre-ranked parent branches.
2. uma.moe automatic pairing: local pool × remote pool, followed by detailed scoring.
3. Transfer Helper: every veteran evaluated across the permanent profile matrix and naturally viable Aces, followed by same-costume portfolio coverage. Strict-replacement verdicts are reserved for exhaustive audits.

## Future multicore scoring

If calculation throughput later needs improvement, use
`concurrent.futures.ProcessPoolExecutor` inside a dedicated backend design, not
a larger Qt thread pool.

- Initialise one `AffinityResolver` and one read-only SQLite connection per worker process. SQLite connections and resolver instances must never be shared between processes.
- Pass coarse batches of pair indexes, typically 256–1,024 pairs per task, instead of serialising a full lineage payload for every pair.
- Keep immutable candidates, scoring configuration and lookup tables in process-local globals created by the executor initializer.
- Return compact ranking summaries from workers. Recompute or retain full diagnostics only for the final top-N results to reduce inter-process transfer costs.
- Use a configurable worker count, with a conservative default such as `max(1, min((os.cpu_count() or 2) - 1, 8))`.
- Preserve a serial fallback for small workloads, frozen builds and worker failures.
- Merge results with stable secondary keys so serial and parallel executions produce the same order.

## Windows and packaged builds

The application targets Windows and is packaged with PyInstaller. Its
executable entry point calls `multiprocessing.freeze_support()` before starting
Qt. Worker functions remain at module scope and never capture Qt widgets,
callbacks, locks or open database handles.

Progress is reported through the IPC supervisor and existing worker signals.
The cooperative cancellation flag is a shared process-safe event checked by
the child's callbacks and scoring checkpoints.

## Suggested parallel rollout

1. Parallelise uma.moe pair summaries first. It is the most isolated Cartesian workload.
2. Apply the same batch executor to local final-parent pairs.
3. Parallelise exhaustive Transfer Helper audits by profile/context chunks, then deterministically merge each veteran's maxima, percentile evidence and portfolio inputs.

Transfer Helper is the most delicate stage because percentile distributions and portfolio requirements are global. Parallel workers should emit raw per-context scores; portfolio selection and final strict-replacement decisions should remain in the parent process. Fast mode already removes most of the former cost by filtering implausible Ace/profile pairs and merging equivalent future-GP aptitude signatures.

## Validation

Before enabling parallel mode by default:

- compare serial and parallel JSON outputs on fixed fixtures;
- require identical top-N identities and scores within floating-point tolerance;
- benchmark process startup separately from scoring time;
- keep serial execution for workloads below a measured break-even threshold;
- test both source execution and the packaged Windows executable.
