# Solver execution

Normal local and online searches use prepared numeric inputs, search-local
curve and G1 transition caches, and delayed diagnostic hydration. Pair scoring
preserves the original floating-point accumulation order (validated variant A).
Existing candidate limits, filters and stable tie order remain in effect.
Retained results receive complete canonical details.

## G1 screening for generic GP searches

Generic GP searches (local or remote second pool, fixed or exhaustive first
pool) use E2 screening by default. E2 applies the base Independent Training
cutoff, allowed calendar years, mandatory objectives, turn conflicts and race
budget. It greedily places higher-value races first, then races with fewer
available slots, with deterministic name/index ties. It does not optimize
streaks. Mandatory objectives reserve their turns before optional G1 races.
The existing fallback for unresolved imported race metadata remains in effect.

For X requested results (clamped to 1–500), the pipeline is:

1. Score every eligible pair with E2, using the same remaining score components.
2. Keep at most 2X pairs, restore their original enumeration order, recalculate
   their complete score with the exact Standard schedule, and sort again.
3. Hydrate only the final X results with exact Standard and Trackblazer details.

The shortlist can contain 1,000 pairs when X=500. Exact ties retain their
original enumeration order, not the approximate order. Screening runs in the
normal spawn workers; exact shortlist rescoring runs in the coordinator and
cooperates with cancellation. Only finalists receive Trackblazer diagnostics.

The JSON and CSV contain the same exact final top in E2 mode. No approximate
scores or schedules are exported. `result_count` is the exported count;
`evaluated_pair_count` remains the complete screened pool. Metadata and search
diagnostics expose `g1_ranking` with the shortlist size, CSV scope and the lack
of a global recall guarantee. Runtime counters aggregate `g1_estimator_calls`
and `g1_solver_calls` from workers, plus screening/reranking elapsed times.

To retain exhaustive exact ranking and the previous all-pairs CSV:

    $env:ULL_G1_RANKING = "exact"
    Remove-Item Env:ULL_G1_RANKING # Restore E2 screening

The accepted values are `e2` (default) and `exact`. The policy is serialized
into worker inputs; it is not selected independently by each worker. Parent
searches and contextual GP searches with a fixed opposing parent retain exact
scoring. The latter project a third G1 history, outside the validated generic
model. Canonical `SolverRuntime(False)` scopes also retain exact scoring.

The supplied eight-case benchmark recovered the full oracle top60 at 2X
(23,593 pairs; worst E2 rank 67). This is empirical evidence, not a guarantee
for other pools, weights, or result counts. The original benchmark script was
not supplied with this patch; the integrated estimator implements the E2 rules
above and is covered by new integration tests, but has not been rerun against
those eight original datasets. Use exact mode for oracle comparisons.

## Workers

No setup is required. The default is automatic: up to four workers, bounded by
the logical CPU count. Searches below 2,000 parent pairs or 200 GP pairs run
sequentially to avoid startup overhead. Explicit worker counts override those
thresholds.

To override the policy for applications launched from PowerShell:

    $env:ULL_SOLVER_WORKERS = "1"     # Optimized sequential execution
    $env:ULL_SOLVER_WORKERS = "4"     # Four workers, limited by pair count
    Remove-Item Env:ULL_SOLVER_WORKERS # Restore automatic selection

The values "auto" and "0" also select automatic mode. Invalid values fail before
the search starts. Each worker owns its numeric caches, so increasing the count
also increases memory use. The setting is read once per search.

Workers use spawn on all platforms, receive serializable input snapshots, and
return bounded batches consumed in original enumeration order. They never
receive Qt objects, SQLite connections or weight-lookup closures. Search
completion, cancellation and worker failure all close the pool. A separate
owner pipe makes workers exit when their backend is terminated abruptly.

Custom Python entry points must follow multiprocessing's main-guard convention
when using parallel searches. The bundled CLI and Qt entry points already do.

## Regression coverage

The solver tests compare canonical evaluation with optimized sequential and
spawn execution, including local parents, branches, future grandparents, online
filters, and generic/contextual GP pairs. In exact mode, CSV bytes and JSON details must match
except for generation timestamps. E2 tests compare final JSON results and CSV
rows with the corresponding exact top, exercise 1/2/4/auto workers and small
pools, verify solver-call counts, and force a screening-order inversion so the
exact rerank must recover the true winner. Numerical tests exercise repeated factors,
ties, missing lineage, probability caps, distinct snapshots sharing business
IDs, and cache lifetime. Process tests cover cancellation, worker exceptions,
worker crashes and backend termination.

    python -m pytest -q tests/test_solver_math.py tests/test_solver_pairs.py tests/test_solver_parallel.py tests/test_solver_production.py tests/test_g1_preranking.py

The production engine writes no prototype captures or comparison reports.
