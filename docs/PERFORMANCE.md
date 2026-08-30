# Performance and parallelisation design

Uma Legacy Linker runs long desktop operations in a Qt worker thread. This
supports cooperative cancellation, but it does not by itself isolate the GUI:
CPU-bound Python scoring and the Qt main thread still share the same GIL.

## Cooperative GIL budget

Parent optimisation uses one monotonic `CooperativeCheckpoint` per search. Hot
loops may call it on every meaningful iteration, but it invokes the worker's
real yield callback only when 10 ms have elapsed. The callback remains owned by
the Qt worker and performs `time.sleep(0)` followed by its cancellation check;
the scoring engine never sleeps directly.

The same checkpoint instance, and therefore the same deadline, is propagated
through local and uma.moe pair loops, branch evaluation, the five main scoring
components and G1 planning. This replaces the former `processed_pairs % 32`
policy, whose latency depended on the variable cost of 32 complete pairs.

The 10 ms interval is a cooperative scheduling budget, not a hard real-time
guarantee. A function that does not call the checkpoint can still retain the
GIL longer, so new CPU-heavy loops must accept or reuse the existing callback.
Checkpoint calls must remain score-neutral.

The pre-change Windows freeze probe recorded 9 heartbeat stalls without resize
(1,772.7 ms median; 29,135.6 ms maximum) and 3 during resize (3,047.1 ms median;
54,950.4 ms maximum). Replay that same probe after changes to this path. If
stalls above roughly 100 ms persist, isolate optimisation in another process as
described below.

## Main hotspots

1. Final parent-pair searches: Cartesian products of pre-ranked parent branches.
2. uma.moe automatic pairing: local pool × remote pool, followed by detailed scoring.
3. Transfer Helper: every veteran evaluated across the permanent profile matrix and naturally viable Aces, followed by same-costume portfolio coverage. Strict-replacement verdicts are reserved for exhaustive audits.

## Process-isolation fallback

Use `concurrent.futures.ProcessPoolExecutor`, not a larger thread pool.

- Initialise one `AffinityResolver` and one read-only SQLite connection per worker process. SQLite connections and resolver instances must never be shared between processes.
- Pass coarse batches of pair indexes, typically 256–1,024 pairs per task, instead of serialising a full lineage payload for every pair.
- Keep immutable candidates, scoring configuration and lookup tables in process-local globals created by the executor initializer.
- Return compact ranking summaries from workers. Recompute or retain full diagnostics only for the final top-N results to reduce inter-process transfer costs.
- Use a configurable worker count, with a conservative default such as `max(1, min((os.cpu_count() or 2) - 1, 8))`.
- Preserve a serial fallback for small workloads, frozen builds and worker failures.
- Merge results with stable secondary keys so serial and parallel executions produce the same order.

## Windows and packaged builds

The application targets Windows and is packaged with PyInstaller. Before
process-based parallelism is enabled, the executable entry point must call
`multiprocessing.freeze_support()`. Worker functions must remain at module
scope and must not capture Qt widgets, callbacks, locks or open database
handles.

Progress should be reported by completed batches through the existing worker
signals. The current cooperative cancellation flag must be propagated to a
shared process-safe event and checked between batches.

## Suggested process rollout

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
