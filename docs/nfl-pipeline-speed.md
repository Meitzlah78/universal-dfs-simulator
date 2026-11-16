# NFL pipeline speed follow-up

This follows the scoring-worker, selector-cache and history-loading fixes in PRs 86–87. The additional change removes repeated work inside every fitting and outcome-generation call, rather than reducing numerical work or changing football policy.

The engine reuses an aligned fourth-down mask instead of performing a membership search, checks receiver/runner selections on their smaller event subsets, skips empty possession/conversion updates, and caches the same normalized cumulative probabilities used by weighted selection. Cumulative tables are keyed by both player names and weights; RB-only receiving and rushing pools can share names while requiring different probabilities. The common random stream and within-player event order remain unchanged.

UI callbacks across fitting, candidate construction, opponent construction and contest scoring are coalesced to at most one update per 250 milliseconds during ordinary forward progress. First, zero, reset and completion notifications still pass through. Numerical work and progress callback delivery on the calling thread are unchanged. A deterministic test reduces 626 dense notifications over approximately three seconds to at most 15 widget updates; this is a UI-traffic check, not a hosted latency benchmark.

## Measured local replay

Frozen 261-player FanDuel full-slate inputs, 20 team market targets, all standard fitting passes, 10,000 evaluation outcomes and 10,000 independent construction outcomes. One paired cold replay:

| Stage | Before | After |
| --- | ---: | ---: |
| Projection/market fitting | 36.43 s | 31.12 s |
| Evaluation generation | 5.97 s | 5.64 s |
| Construction generation | 6.14 s | 5.32 s |
| Complete numerical preparation | 48.82 s | 42.35 s |
| Warm preparation load | 0.062 s | 0.058 s |

Cold numerical preparation decreased by 13.2%. Parameters, reports, evaluation and construction DataFrames matched exactly. These timings exclude network, candidate and field search, portfolio selection and the live Streamlit UI. They do not establish a whole-build or hosted latency gain. The previously measured scoring-worker benefit is documented separately in `nfl-scoring-workers.md`; timings from the two benchmarks must not be added as if they were one run.

The optional selector formulation trial reduced matrix size but made the captured 5,000-candidate selection slower (9.41 to 10.73 seconds), so it was discarded. Solver objectives, proof requirements, limits and quality/exposure constraints remain unchanged.

Reproduce cold/warm parity with `python scripts/benchmark_nfl_preparation_speed.py --fit-spec FROZEN_FIT_SPEC.json --output result.json`, or use `--archive CALIBRATION_SOLVER.zip`. The recorded numerical evidence is `nfl-pipeline-speed-validation.json`. The frozen replay used its original baseline parameters; separate original-engine golden cases cover both sites, active learned rushing parameters, concentrated opportunities, RB-only pools, missing quarterbacks/receivers and one-outcome empty-event paths. Golden digests include every stat, diagnostic and final RNG state.

The learned-model implementation revision preserves all scientific parameters, training/validation dates and evidence; no holdout was retested or model promoted. It only updates compatibility for the exact-parity engine implementation. Engine fingerprinting remains strict, so a first run after this deployment can rebuild an older prepared cache. Subsequent identical-input retries reuse the new cache. The 2025 data and research branches are unchanged.
