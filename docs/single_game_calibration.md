# Offline single-game ownership calibration

`simmah_single_calibration.calibrate_role_weights` projects a prior over enumerated legal lineups onto separate Captain/MVP and FLEX ownership targets. No application build or ranking path imports it. Enumeration still enforces salary, team and player eligibility rules.

Inputs are integer lineup indices with special role first, nonnegative prior mass per row, and two ordered probability vectors. Captain/MVP probabilities sum to 1, FLEX probabilities to 5, and each player's combined probability is at most 1. Missing targets are never inferred. Exact prior zeros remain zero and can make targets infeasible.

The implementation uses positive-exponent weights `softmax(log(q) + X @ theta)`, minimizing `log Z - theta @ target`. Its gradient is achieved ownership minus target. With the alternative negative-exponent convention the gradient sign reverses. Sum-to-one is handled analytically, so there is no additional normalization parameter. Dual coordinates are scaled by inverse target Bernoulli standard deviation (variance floor 1e-6) to improve rare-role conditioning; objective and residual acceptance remain unchanged. Only lineup indices, role vectors and per-lineup probabilities are needed for dual iterations; no dense lineup-by-player incidence array is built.

A separate sparse HiGHS feasibility LP has seven nonzeros per lineup. It still has one primal variable per positive-prior support row, so it is not guaranteed to be instantaneous on million-row supports. The time limit is configurable. Infeasibility, unknown feasibility (including timeout), and dual nonconvergence are distinct errors. A feasible LP witness is not used as a replacement for the KL solution. Boundary targets can require divergent dual parameters and yield nonconvergence.

Weights are accepted only after checking normalization, finiteness and the maximum role-ownership error. Default tolerance is 1e-6 probability (0.0001 percentage points). Optimizer status is retained separately from residual acceptance. There is no implicit slack, regularization or target adjustment. Diagnostics include KL distance and effective support size.

## CLI

```sh
python scripts/calibrate_single_support.py \
  --support challenger_support.npz \
  --player-ids support_player_ids.json \
  --targets independent_role_targets.json \
  --output calibrated_support.npz
```

Support NPZ contains `indices` (J x 6) and `probabilities` (J,). Player IDs JSON supplies the ordered pool-row mapping. Targets JSON has `player_ids`, `special`, `flex`, and an explicit `source` record. IDs must match exactly; target order is aligned automatically. Source can include provider ID, actual pull time or null if unknown, slate identity, checksum and projected/actual classification. The CLI stores that record verbatim, but cannot independently verify that a provider forecast is authentic or pre-lock. Actual contest ownership is suitable for an oracle diagnostic only, never a predictive backtest baseline.

Output is an exclusive new NPZ containing support indices, calibrated probabilities, priors, ordered IDs, achieved and target marginals, diagnostics, configuration, provenance and input hashes. Load with `allow_pickle=False`. Sampling with replacement preserves duplicates. Sampled frequencies fluctuate around calibrated expected frequencies; exact marginal matching is a property of the probability distribution, not every finite random field.

Matching marginals does not guarantee pair or duplication realism. For incidence X and normalized weights w, pair probabilities are `X.T @ diag(w) @ X`, not `w.T @ X` (the latter contains marginals). Validate off-diagonal pair residuals, salary distributions, team splits and duplicate curves at equal represented contest size on frozen slates. Any added pair constraints require another feasibility check and independent training evidence. Live use remains frozen pending those tests and independent role-ownership inputs.

Benchmark: 12,267 legal NE–CHI support rows, 26 players, synthetic feasible exponential-tilt targets: approximately 0.17 s including feasibility on this environment, maximum marginal error approximately 0.00000039 percentage points. This is a correctness/performance check, not measured ownership forecast quality or guaranteed deployment speed.
