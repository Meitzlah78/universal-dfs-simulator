# Simmah: fourth-down, passing-tail and rushing-shape audit — November 15, 2026

Decision: retain Fourth-Down-Only as the leading research candidate. No model weights, candidate probabilities, clock policy or production behavior changed. Do not re-anchor a training-only fit to 4.34: that is the observed 2024 target, whereas the saved 2022–2023 target is 4.285605594. Promotion gates remain draft and 2025 stays locked.

## Matched replay and scope

Replayed Fourth-Down-Only and Combined across all 285 labels, two seeds, 512 draws per seed: 291,840 trials per arm. Passive callbacks retain fourth-down and play-outcome counters without additional random draws. Every returned dictionary exactly matches all 1,140 saved arm batches, including means, clock ledgers and accounting errors. All 46 focused tests pass, including the existing 43. Exact 3,600-second accounting is preserved. The code is research-only and main/production are untouched.

The labels key league-level seeds; these are not matchup/player-calibrated forecasts. 2024 is repeatedly reused development data. All observed fourth-down comparisons use actual pre-play states; no 2024 fitting is performed. Proposal counts include no-play retries, but go/punt/FG comparison rates use executed opportunities, matching the observed statistical-play filter. Unavailable expected-policy rates for simulated states are marked null; expected rates below are evaluated directly on observed states.

## The +2.07 punt gap

Fourth-Down-Only produces 9.47809 punts/game versus 7.41053 observed, a gap of 2.06756. Of that, 1.65304 (80.0%) occurs between the offense's own 25 and midfield. The driver only punts at distance >40 from the opposing goal, so inside the opponent 35 the direct choice is go versus FG, not punt. Those choices can still affect later drives indirectly.

| Field zone | Observed fourth opportunities/game | Simulated opportunities/game | Observed punts/game | Simulated punts/game |
|---|---:|---:|---:|---:|
| inside5 | 0.425 | 0.301 | 0.000 | 0.000 |
| opp35_to5 | 3.975 | 3.736 | 0.000 | 0.000 |
| opp50_to35 | 2.505 | 2.730 | 1.144 | 1.339 |
| own25_to50 | 5.393 | 6.947 | 4.649 | 6.302 |
| own_goal_to25 | 1.674 | 1.961 | 1.618 | 1.837 |

A coarse by-zone accounting identity allocates 1.720 extra punts/game to opportunity volume/field mix and 0.347 to within-zone action mix. This is descriptive: the within-zone term includes distance and score-script mix, so it is not a causal policy-only effect. More own-half fourth downs are the dominant location of the excess. Missing gains, field starts, penalty handling and other state mechanisms remain possible contributors; no single cause is proved.

## Fourth-down policy on observed states

| Zone / score script | Actual opportunities | Observed go rate | Frozen candidate expected rate |
|---|---:|---:|---:|
| inside5 / all | 121 | 57.02% | 46.41% |
| inside5 / trailing_any | 70 | 67.14% | 45.05% |
| opp35_to5 / all | 1133 | 23.92% | 23.75% |
| opp35_to5 / trailing_any | 523 | 32.31% | 26.80% |
| opp50_to35 / all | 714 | 34.17% | 33.52% |
| opp50_to35 / late_trailing | 49 | 79.59% | 70.64% |
| own25_to50 / all | 1537 | 13.79% | 10.15% |
| own25_to50 / trailing_any | 765 | 22.48% | 13.80% |
| own_goal_to25 / all | 477 | 3.35% | 8.49% |
| own_goal_to25 / late_trailing | 25 | 24.00% | 69.37% |

The opponent 5–35 aggregate is close (23.75% candidate versus 23.92% observed), but trailing cases underpredict. Inside five, the candidate underpredicts, especially while trailing; that sample contains only 121 total opportunities and 70 trailing cases. The own-half policy has opposite biases: too few expected attempts from own 25 to midfield and too many deep in its own end. The model currently combines both zones into one own-half bucket. A uniform aggression increase would worsen the deep-own-end mismatch. Any new split/script fit must use 2022–2023, with new evaluation, rather than fitting these 2024 rates. The complete zone/distance/script table is in analysis.json.

## Passing explosives: correct denominator and field control

Rates below are per completed pass, not per attempt/dropback. The observed completion sample is 12,074 regulation records after the common exclusions.

| Kernel / context | Mean completion yards | 20+ share | 40+ share |
|---|---:|---:|---:|
| Observed 2024 / realized states | 10.953 | 13.757% | 2.071% |
| Fourth-Down-Only / realized states | 10.454 | 12.472% | 0.893% |
| Combined / realized states | 10.454 | 12.491% | 0.900% |
| Current gamma on observed fields | 10.372 | 12.375% | 0.888% |
| Frozen empirical completion candidate on observed fields | 10.904 | 12.870% | 2.144% |

The 40+ deficit persists when opportunity count and actual field positions are held fixed: current gamma 0.888% versus 2.071% observed. It is not explained solely by simulated field mix. The existing training-only empirical completion candidate gives 2.144% and mean 10.904 versus 10.953 observed, although its 20+ share remains low (12.870% versus 13.757%). The V5 driver currently hardcodes gamma(shape=1.5) for caught passes and has no completion-model argument; the saved empirical completion model is not wired into this replay.

The conditional non-red-zone passing TD proxy rises from 0.430/game under gamma to 0.821 with the frozen candidate, versus 0.860 observed. This holds observed opportunities fixed and is not a full-game scoring or point-gain claim. No new candidate was fit or installed.

## Rushing: mean versus threshold handling

The frozen body fit matches the 2022–2023 observed mean 4.285605594, modifies only support 1–6, and leaves mass outside that body exactly unchanged. The 4.33906 mean is from 2024. Re-targeting to it would be calibration on the repeatedly inspected evaluation season. The prior full rushing-only arm already averages 4.33541 YPC; Combined averages 4.31561, and the conditional candidate on actual field states averages about 4.259. Different opportunity/field distributions must not be treated as the same estimand.

Using the same observed designed-run states and shared draws gives this yard-only first-down success comparison (gain >=40% of distance on first down, without fumble logic):

| Diagnostic kernel | Conditional YPC | First-down success | 20+ share |
|---|---:|---:|---:|
| Observed | 4.33906 | 49.09% | 2.233% |
| gaussian_current | 4.34266 | 54.10% | 0.219% |
| empirical_current | 4.25905 | 43.75% | 2.149% |
| empirical_no_environment_diagnostic | 4.26386 | 48.59% | 2.251% |
| empirical_rounded_diagnostic | 4.25845 | 48.49% | 2.250% |

Rounding the already-scaled gains in a diagnostic changes conditional mean from 4.25905 to 4.25845 (essentially unchanged), but first-down success rises from 43.75% to 48.49%, near observed 49.09%. Multiplying integer empirical gains by a continuous environment factor can push mass at exactly four yards below the four-yard success threshold. The same issue can affect conversion thresholds. This strongly motivates a representation/threshold test; it is not full-game causal proof that rounding fixes punts.

Neither rounding nor removal of environment scaling is adopted. Both diagnostics alter threshold/tail behavior: the 20+ share moves from about 2.149% to 2.250%, so they cannot be described as preserving the existing realized tail unchanged. Official PBP integer recording and true physical yards also differ. A new sampler must address these definitions and be validated in an isolated full-game replay. Raising the mean alone would not isolate this mechanism.

## Recommended controlled work

Keep Fourth-Down-Only as the leading unchanged candidate. First test adding the existing frozen completion kernel to that arm with common random streams and no other changes. Separately test an integer/threshold-consistent rushing representation with the training body held fixed; do not silently combine it with passing changes or retarget to 4.34. Any fourth-down zone/script refit should use 2022–2023 only and preserve a separate evaluation gate. These are next experiments, not promotions. No new outcome-model arms were run in this audit.

Promotion gates remain draft. Full-game model validation, main/production and 2025 remain unchanged.
