# NFL scoring workers

Candidate summaries and contest score/rank batches now use a bounded thread pool for the existing NumPy/SciPy kernels. Simulation fitting, RNG draws, candidate proposals, opponent construction, solver objectives, and hard constraints are unchanged. No samples or candidates are removed.

Results are consumed in original batch and outcome order. Floating-point accumulation, percentile interpolation, ties, ranks and payouts retain exact serial behavior. Progress callbacks run on the calling thread. At most the selected number of batches is in flight, so memory does not grow with the full contest matrix.

Automatic allocation respects CPU affinity and cgroup v1/v2 quota, uses at most four workers, and drops to two or one when available memory is below 1 GiB or 512 MiB. Small scoring jobs stay serial. The internal `workers=1` option permits exact serial comparisons. This does not provision additional hosting CPU.

## Local benchmark

Synthetic fixed inputs: 275 players, 10,000 outcomes, 5,000 candidates, 10,000 opponents. Two runs per configuration, in forward and reverse worker order. Mean combined candidate-summary and contest-scoring times:

| Workers | Seconds | Reduction vs serial |
| --- | ---: | ---: |
| 1 | 11.43 | — |
| 2 | 6.50 | 43% |
| 4 | 3.81 | 67% |

Every output DataFrame matched exactly, including numeric values, row order and attributes. These are local scoring-stage timings, not total build or Streamlit-host timing claims. Cold fitting and portfolio selection are excluded. A one-CPU host retains serial scoring.

Reproduce with `python scripts/benchmark_nfl_scoring_workers.py --output docs/benchmarks/nfl-scoring-workers-2026-11-16.json`. Raw measurements are in that JSON file.

## Verification

69 targeted tests pass across scoring kernels, candidates, contest ranks/ties/payouts, selector quality budgets, assignment/export recovery, and the real Streamlit timeout/download regression. Worker tests compare serial against two and four workers, cover special-role multipliers and joint evaluation, enforce queue bounds, surface failures, and verify quota/memory fallback.

An exploratory 88-test run also included the legacy `test_portfolio_selection` suite: two tests failed identically on the unchanged pre-fix checkout. One expects the old `select_portfolio` app call name; the other assumes a second repair-solver call when the deterministic repair already succeeds. These pre-existing failures are not counted among the 69 passing targeted tests.
