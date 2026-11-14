# Concentrated recipient routing — offline verification, 2026-11-14

**Joint checkpoint fails. No promotion. Production and PR #77 remain untouched.** No parameters were changed after the frozen candidate ran on the29 development-verification games. They were examined previously and are not a pristine final holdout.

## Training evidence
Only pre-Nov6 PBP is opened for recipient-model fitting.181 earlier games were considered:116 passed strict five-player reconstruction and whole-minute boxscore reconciliation,65 were quarantined (including10 OT games). ESPN MIN is whole-minute rounded: tolerance60.01 seconds per player, not exact second-level boxscore parity. Monotonic game clocks and valid source event order are required. SequenceNumber identifiers may reflect later provider corrections and are not sorted as chronology. Ambiguous identities, impossible substitutions and missing periods are rejected.

The31 later game IDs are excluded before opening their PBP (29 evaluation games plus two already-excluded OT games). Earlier PBP without saved projection snapshots trains replacement identities only. Only eight games have original frozen minute forecasts for identifying actual >5-minute core projection deficits. Among usable cases,39 core-deficit exit observations exist;16 are unambiguous single substitutions across nine player-games. Their top two recipients cover14/16 exits. This small statistic is not a causal estimate of every lost minute. Across all3137 earlier single exits, donor-specific top-two recipients cover65.2% of exits in-sample.1926 multi-player transitions remain joint sets rather than invented donor pairs. Recipient position tags are retained for audit; routing uses observed donor/recipient relationships, not an imposed universal positional rule. Early-October source files are included; no recovered season-type field certifies that this corpus is exclusively regular-season games.

Examples in earlier deficit cases: Derrick White -> Payton Pritchard/Baylor Scheierman; Matas Buzelis -> Noa Essengue/Caleb Wilson/Isaac Okoro. Some recipients are established regular rotation players or starters, so restricting every replacement to a<18-minute player is inappropriate.

## Frozen candidate
Use the116-game immediate-replacement priors. For each transfer pool, sample at most two supported eligible recipients without replacement, weighted by donor-conditioned empirical frequencies and donor cut sizes. Preserve240 minutes and0–48 bounds. No supported recipient => explicit unallocated amount; donor minutes are preserved rather than assigned through an invented fallback. A foul-cut player cannot simultaneously receive that pool. Deep bench (pregame physical-minute rank>10) is excluded from additional transfer receipts; explicit depth permission exists but stays off in this experiment. Production's baseline wider-minute residual is retained, so this guard does not erase its existing deep-bench noise.

Blowout donors now have physical pregame mean>=28; regular rotation receivers can gain. Tight-game transfers go to the top7. Foul shifts use the same constrained recipient mechanism. Script probabilities and transfer budgets are fixed to the first original chronological fold (training max dateOct30); none of the29 evaluation games train them. The diffuse comparator uses those same fixed probabilities/magnitudes, with the prior top7 donor rule. Therefore the policy comparison includes both concentrated recipient selection and the clarified core donor definition; it is not a pure recipient-count-only ablation. The old independent same-engine reference is reused unchanged.

Before replay, protocol.json records algorithm/data hashes and all choices. Each new arm runs1024 pregame calibration draws seed83 and2000 fresh evaluation draws seed2100. All20 new arm/build full-engine replays completed (10 builds,29 unique non-OT games,1215 forecast rows). Minute/pair replays use2000 trials, with latest pretip team snapshots for primary comparison. No archived fantasy interval rescaling.

## Full-engine fantasy80% interval coverage
Among >5-minute projection misses:

| Tier | DK independent | DK diffuse-fixed | DK concentrated | FD independent | FD diffuse-fixed | FD concentrated |
|---|---:|---:|---:|---:|---:|---:|
| Core28+ |47.3%|49.1%|50.9%|43.5%|44.9%|44.9%|
| Rotation18–27 |47.0%|47.0%|50.0%|50.0%|54.2%|54.2%|
| Bench<18 |56.0%|42.9%|51.2%|55.9%|46.2%|54.8%|
| All players/all minute errors |73.0%|71.7%|73.9%|72.7%|72.0%|73.6%|

The core/rotation gains do not establish a robust improvement: game-bootstrap intervals touch zero. Overall game-weighted coverage changes: DK+0.98pp (95%−0.10 to+2.16), FD+0.97pp (−0.05 to+2.06). DK bench game-weighted change−5.38pp (−11.81 to0); FD−0.96pp (−5.45 to+3.65). These intervals condition on fitted models, cluster by physical game, and do not incorporate training uncertainty or multiple comparisons. Only five evaluation dates exist. Large-minute-miss slices are retrospective diagnostics, not live selection features.

Player-mean projection MAE: DK0.258→0.241FP; FD0.242→0.259FP. Maximum reported team mean residual remains1.593 real points in both new arms (62 game/build reports per arm). Not every team satisfies a±1-point gate.

## Dependence and minute results
Primary bench pairs295 across29 games: observed10.17% dual+5-minute spikes. Independent prediction3.71%, diffuse-fixed4.42%, concentrated4.29%. Game-weighted Brier0.13537,0.13234,0.13416 respectively. Concentration does not resolve the remaining co-spike deficit and is worse than diffuse-fixed on this metric. Primary minute80% coverage: diffuse-fixed73.45%, concentrated77.27% (earlier independent74.72%). Improved minute coverage is not proof of improved joint fantasy calibration.

## Decision and autonomous forecasts
Reject promotion. Do not choose new magnitudes to match10.2% on these games. This experiment supports studying actual backup identities but does not demonstrate joint coverage/dependence success. The unchanged36 targeted tests pass, including the original27 plus concentrated routing, no-fallback behavior, deep-bench exclusion, conservation, schedule feasibility, source-order reconstruction and quarantine checks.

This remains a provider-centered simulation experiment. It does not prove an autonomous Simmah pregame minutes/points forecast outperforms provider inputs. That requires a separate earlier-game-only forecast generator, verified availability inputs, and a frozen side-by-side benchmark on genuinely unseen games before promotion. Archived PBP has supplied replacement priors here; it has not automatically replaced live projection inputs.
