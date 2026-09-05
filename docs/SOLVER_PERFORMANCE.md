# Solver execution

Normal local and online searches use prepared numeric inputs, search-local
curve and G1 transition caches, and delayed diagnostic hydration. Pair scoring
preserves the original floating-point accumulation order (validated variant A).
There is no approximate top prefilter: every eligible pair in the selected
search mode is scored. Existing candidate limits, filters and stable tie order
remain in effect. Retained results receive complete canonical details; full CSV
exports retain their existing columns and schedule-detail policy.

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
filters, and generic/contextual GP pairs. CSV bytes and JSON details must match
except for generation timestamps. Numerical tests exercise repeated factors,
ties, missing lineage, probability caps, distinct snapshots sharing business
IDs, and cache lifetime. Process tests cover cancellation, worker exceptions,
worker crashes and backend termination.

    python -m pytest -q tests/test_solver_math.py tests/test_solver_pairs.py tests/test_solver_parallel.py tests/test_solver_production.py

The production engine writes no prototype captures or comparison reports.
