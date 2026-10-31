# Full-site-slate oracle experiment

Offline only. The recovered pregame FanDuel upload for slate 135541 contained 58 listed players, including all 49 players observed in the supplied completed-contest standings. The test retains every listed player without applying the candidate point/injury filters. Unknown pregame ownership is not inferred: these are explicitly actual same-contest oracle targets. Nine unobserved site players have zero actual role ownership; those exact zeros restrict the fitted distribution to a boundary face, while KL retains normalization against the full 58-player uniform prior.

Configuration: MVP plus five distinct unordered FLEX players, 1.5x MVP salary, $60,000 cap, no salary floor, both teams, all site-listed MVPs. The existing streamed NumPy enumerator generated 237,130,742 legal role assignments and found all 10,440 observed rosters (88,087 entries): 100% exact and entry-weighted coverage. Enumeration took about 28.45 seconds in the test environment. This establishes coverage for this slate and these rules only.

Feasibility was certified by HiGHS on the actual observed-roster subset after every observed row was verified to be contained in the full legal universe. That LP witness extends to the complete universe by assigning zero weight to unobserved rows. A 237-million-variable primal LP was not materialized or claimed to be solved.

The experimental `SalaryPartition` implementation computes the same uniform-prior legal-universe partition, marginals and salary distribution using exact integer salary-grid subset dynamic programming. Reverse accumulation supplies analytic gradients. It supports exactly two teams and the no-floor configuration described above, not arbitrary lineup priors or slot rules. Salaries and cap must be exact integer dollars; unsupported fractional inputs fail rather than being truncated.

A forced-FLEX conditional partition supplies exact joint moments. The implementation is tested against independent small-universe enumeration, finite-difference partition gradients, explicit joint outer products, and zero-target boundary normalization. This is an experimental offline backend; live code does not import it.

Full-support oracle results:

- 63 L-BFGS iterations, about 7.22 seconds including partition-count normalization (feasibility performed separately).
- Maximum ownership residual 1.608e-8 probability = 0.000001608 percentage points; acceptance tolerance remained 1e-6 probability.
- KL from full-universe uniform prior: 11.417696 nats. The prior has vastly larger support than the earlier observed-roster prior, so raw KL changes are not an isolated measure of model deterioration.
- Salary Wasserstein: $205.196829, versus $254.680341 on the observed-support oracle. Above the exploratory $150 alert.
- Maximum role-pair residual: 4.000942 percentage points, versus 3.817435 on observed support. Below the exploratory 5-point alert. Exact conditional moment evaluation took about 3.55 seconds.

The experiment changes available combinations, not just individual player availability: the closed oracle already contained all 49 observed players. Neither the Wasserstein improvement nor the residual magnitude establishes a cheap-player causal explanation, a percentage of human behavior reconstructed, or predictive profitability. The reference standings' full-contest completeness was not independently established.

## Replay

`python scripts/full_slate_oracle.py --slate-csv SITE_LIST.csv --actual-field actual_field.npz --slate-id 135541 --output NEW_DIRECTORY`

Site CSV columns: `Id`, `Nickname`, `Salary`, `MVP 1.5x Salary`, `Team`. Preserve the original salary-list identity, game set and checksum outside normalization. Actual NPZ comes from the observed-support oracle harness and must have same-slate `actual_contest` metadata. Output is a new directory; failed runs can leave partial output and should not be treated as sealed production snapshots. The script exports an implicit partition solution and independently streams the full enumeration for exact coverage. Pair calculations are available via `SalaryPartition.role_moments` and require the same player-ID mapping.
