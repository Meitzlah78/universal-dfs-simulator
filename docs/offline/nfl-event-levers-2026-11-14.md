# NFL offline event-lever audit — November 14, 2026

Status: research only; no production changes. Trained on 2022–2023; evaluated on 285 games from 2024. The 2025 holdout was not opened. Kickoffs remain fixed and promotion gates remain draft.

## Fourth-down decisions

On 3,982 observed fourth-down opportunities, observed go rate was 20.39%, candidate 19.11%, and original engine rule 7.23%. Brier error: original rule 0.18031, global league-rate baseline 0.16244, candidate 0.10028. Whole-game paired bootstrap candidate-minus-global error: -0.06217, 95% interval [-0.06889, -0.05567]. This is tuning evidence, not a promotion gate.

On neutral fourth-and-short between the opponent 50 and 35 (82 opportunities), observed go rate was 82.93%, candidate 81.26%, original rule 0%. Some slices still underpredict, including own-half short situations.

## Yardage distributions

All percentages below are conditional on observed 2024 play types and field positions, using shared uniforms and environments, 64 draws and two seeds. They are not full-game simulation results.

| Event / metric | Observed | Baseline kernel | Empirical candidate |
|---|---:|---:|---:|
| Run mean yards | 4.339 | 4.341 | 4.189 |
| Run 20+ % | 2.233 | 0.219 | 2.149 |
| Run 30+ % | 0.979 | 0.00011 | 0.856 |
| Run 40+ % | 0.544 | 0 | 0.418 |
| Completion mean yards | 10.953 | 10.372 | 10.904 |
| Completion 20+ % | 13.757 | 12.375 | 12.870 |
| Completion 30+ % | 4.969 | 3.406 | 4.856 |
| Completion 40+ % | 2.071 | 0.888 | 2.144 |

The candidate uses interval-censor-aware empirical distributions fit only on training years. Existing gain caps remain unchanged. The rushing mean regresses by approximately 0.15 yards relative to observed; latent-mean matching worsened this and was not accepted. Scrambles remain a separate unresolved process. Field-position independence within event type is a modeling assumption.

## Verification and blockers

27 local tests pass: 13 new component tests plus 14 existing situational/clock tests. The standalone new tests enforce training cutoffs, holdout rejection, pre-play-only fourth-down features, fixed caps, deterministic inputs and physical field clipping.

Recovered historical replay ZIPs contain results and source hashes but not the runnable corrected-clock driver. Local Git and remote branch recovery did not locate it. Therefore isolated and combined full-game ablations have NOT been completed; no claim is made about changed punts, points, snaps, drives, player calibration, or tomorrow readiness. Reconstructing and verifying the driver against the saved baseline is the next prerequisite. Do not substitute conditional checks for that gate.

## Reproduce components

From repository root, with numpy, pandas and scipy installed:

    OPENBLAS_NUM_THREADS=1 PYTHONPATH=. python3 -m unittest discover -s tests -p test_nfl_event_levers_offline.py
    OPENBLAS_NUM_THREADS=1 PYTHONPATH=. python3 scripts/audit_nfl_event_levers_offline.py /path/to/pbp /path/to/output --draws 64

The input directory must contain play_by_play_2022.csv.gz, play_by_play_2023.csv.gz and play_by_play_2024.csv.gz. No other season is accepted.
