# Single-game structural validation

Offline diagnostics compare two distributions with explicit identical site and slate IDs and identical player-ID sets. Reference IDs are reordered by key, never assumed to match array order. Role columns are explicitly exported: all CPT (DK) or MVP (FD) columns first, then all FLEX columns. Any-role player pairs are also reported separately. Cross-slate player-ID comparisons are rejected; historical construction profiles across different players require a separately designed feature mapping.

The utility uses sparse incidence matrices with exactly six indicators per lineup. It calculates joint probabilities, marginal ownership and covariance separately. Signed residuals are simulated minus reference: positive means overrepresentation. Pair summaries exclude the diagonal, special/special pairs and same-player special/FLEX pairs. Marginal errors are reported separately so ownership shifts cannot masquerade as pair fit.

Covariance subtracts the independent product component; it is not correlation and does not make results fully independent of marginal ownership or comparable across weeks. The matrices are descriptive, not evidence of causal interactions or predictive edge. Reference data must come from the same slate and a verified historical player/salary mapping; scores must never become pregame predictor inputs.

Salary distributions are normalized discrete probability masses, with weighted inverse-CDF quantiles, maximum CDF distance and Wasserstein distance in dollars. No universal $49,500–$50,000 salary curve is assumed. Each site, slate and contest can differ. Reference and simulated weights are passed to Wasserstein in the correct corresponding order.

KL distortion uses normalized priors on the same lineup rows. A positive calibrated weight where the prior is zero produces infinite KL, not an epsilon-smoothed finite value. The CLI reports that case with an explicit flag. Low KL means little change to a prior; it does not establish that the prior is realistic. At a solved interior optimum, the positive-exponent minimized dual objective is the negative of the primal KL value (normalized q); the diagnostic computes primal KL explicitly rather than mislabeling the objective.

## Usage

```sh
python scripts/validate_single_field.py \
  --sim calibrated_support.npz \
  --reference actual_contest_field.npz \
  --output validation.zip \
  --covariance-alert-pp 5 \
  --salary-alert-dollars 150
```

Inputs contain `indices` (J x 6, special first), `probabilities` (row probabilities or counts normalized by the utility), `salary` (row totals), `player_ids` (ordered), and scalar `metadata_json`. Both metadata objects require explicit `slate_id`, `site` (`dk` or `fd`), and `source_kind`. Reference kind is `actual_contest` or `generated_reference`. Caller-supplied identities are validated for agreement; the utility cannot independently authenticate their correctness or completeness. Keep source checksums, expected entry counts, mapping provenance and salary snapshot identity in metadata.

Calibrated-support export retains input salaries when present and copies top-level `site` and `slate_id` from targets JSON. These identifiers must be supplied for validation. Missing salaries or identity metadata cause a hard failure rather than invented mappings.

`prior` is optional and must be row-aligned. Without it KL is unavailable, not zero. Output ZIP contains explicit column mapping, role and any-slot joint/covariance residual arrays, signed pair CSVs, weighted salary distributions, source metadata and hashes. Input files and output are never overwritten.

Alert thresholds are optional, explicit, and exploratory. A 5-percentage-point CPT/MVP–FLEX covariance difference and $150 Wasserstein distance have not been validated as universal gates. There is no automatic live promotion, target relaxation or fitted-pair feedback.

Existing `simmah_contest_history.parse_lineups` reads contest CSVs and `verified_fanduel_mvp_first` verifies FD special-role ordering against published scores. Raw standings still need historical player-ID/salary mapping and completeness checks before producing `actual_contest_field.npz`. Current NE–CHI comparison data are generated fields, not observed human tournament results.
