# Frozen pregame market trial: WAS at SF, October 19, 2026

This is an offline forward test. The live app was not changed. Kickoff is
October 19 at 8:15 PM Eastern (October 20 at 00:15 UTC). The exact morning
capture/freeze times and source hashes are in `manifest.json`.

`frozen-comparison.csv` is the immutable prediction set to grade after the game.
It contains 27 DraftKings and 26 FanDuel players, DFF and DraftEdge separately,
the app-equivalent positive-source average, and an experimental challenger.
Missing/zero projections and DFF Out/IR players are excluded from the trial.
Questionable players remain. This is an early snapshot, not final inactive news.

`paired-props.csv` contains 136 same-book, same-threshold, two-sided half-point
markets captured from Covers' sportsbook comparison tables. 27 DK and 25 FD
constraints were usable in the shared simulated player pool. One-sided anytime
TD prices, integer thresholds with push ambiguity, mismatched lines/books,
unsupported stats and constant simulated features were not fitted.

## Preregistered method

For each same-book quote, normalize its over and under implied probabilities to
sum to one (proportional margin removal). This is an estimate, not a guaranteed
true probability. Pick one threshold per player/stat: most quoting books, then
closest to the median threshold. Use the median normalized over probability at
that threshold. Do not combine the best over and under from different books.

Fit shared-game scenario weights with a soft entropy objective and fixed ridge
0.05. Keep effective sample size at least 25% of the 10,000 outcomes by tempering
weights toward uniform. Residuals remain visible; the model is not claimed to
match all markets exactly. Shared stat lines stay intact, preserving player/team
accounting. Mean absolute probability residual: 1.99 percentage points DK and
3.49 points FD. Effective sample sizes: 4,282 DK and 2,818 FD.

For each player, set the experimental point projection to:

`posted baseline + 0.5 * (market-weighted simulated mean - uniform simulated mean)`

The 50% shift, ridge, sample floor, seeds and predictions are frozen before
kickoff. No outcomes were read or used to tune these settings. All scored means
are base-slot values; apply the platform's 1.5x captain/MVP rules only when
scoring a lineup. This is not a market-only projection: touchdowns, kickers,
defenses and low-coverage players depend heavily on the original shared model.

## Limits and grading

- DFF game identity/date was verified from row attributes. Generic DraftEdge
  point values were saved exactly as the app currently blends them. Their
  scoring-system identity is not independently confirmed for FanDuel; preserve
  this caveat in comparisons rather than calling it a clean independent FD source.
- Individual sportsbook quote update timestamps were not exposed. Capture time
  is not proof that every underlying quote was fresh. Raw response SHA-256 hashes
  are recorded; raw HTML is not committed.
- Roles were reconstructed from dated weekly history preceding kickoff. Weather
  was neutral. This is not an exact replay of an app session.
- After final statistics are available, run `scripts/score_market_trial.py` with
  `--trial` pointing to the frozen comparison, `--weekly` pointing to final
  nflverse 2026 weekly player statistics, and `--output` for the results JSON.
- The grader uses exact platform raw-stat scoring, including fumbles and 2PTs.
  Unmatched actual players stay missing, never assumed zero. DST requires a
  verified contest fantasy score and is excluded from the weekly-stat grader.
- Report MAE, matched-player coverage and player-level changes. One game cannot establish
  persistent accuracy, lineup quality or ROI. Do not select winning subsets or
  tune this frozen trial after results arrive.

Preparation code: `scripts/prepare_market_trial.py`, `simmah_market_trial.py`.
Frozen roles/model inputs: `frozen-inputs.json`. Market fit: `constraints.csv`.
