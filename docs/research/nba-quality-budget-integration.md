# NBA quality-budget selection integration and actual-score audit

November 13, 2026. Separate branch from main; no PR #77 experimental mechanics. Not merged or deployed. Existing eight builds are development cases, not fresh holdouts or proof of future winnings.

## Implemented

NBA tournament selection now calls the existing certified two-stage quality-budget solver. First maximize measured candidate quality subject to every NBA manual/automatic cap and a full unique portfolio. Then reduce squared exposure concentration with at most a fixed 5% portfolio quality loss. Diversity off uses a zero-loss budget. The UI replaces the old 0–100 diversity slider with a clearly labeled 5% budget toggle. Cash selection and grouped late swap remain unchanged.

Top-1% ranks retain their original objective. ROI ranking uses expected prize as the nonnegative percentage-budget basis; with a common entry fee, it has the same quality-maximizing order as ROI, while avoiding percentages of negative ROI. It is not a claim to lose at most 5% of net profit.

All limits from `portfolio_limits` are passed as hard constraints; `automatic_max=100` does not erase those per-player caps. When automatic caps are explicitly disabled, no new cap is invented: 100% exposure can still occur. Caps-on portfolios are never silently relaxed.

A first-stage certification timeout stops explicitly and preserves previous saved lineups. A second-stage timeout may retain a checked feasible diversified incumbent within budget, or fall back to the certified quality optimum. Solver status and quality retained are surfaced in UI and logs. Reselecting unchanged saved candidates/settings uses a content identity rather than rerunning the solver on every page interaction. Cache invalidates on ranking scores, metric, diversity policy, player IDs and hard limits. Failed selections commit neither new lineups nor a new successful cache identity. Existing export legality checks still apply.

Diagnostic packages now include the shared selector source and portfolio quality/status metadata. No game outcomes, player parameters or opponent-field construction changed.

## Predicted-quality and exposure replay

Same saved candidates, pregame scores, portfolio sizes and recorded caps. Manifest source files are hash verified before replay. No actual outcomes enter selection.

| Date | Site | Saved quality | New quality | Change | Saved / new max exposure | Outcome |
|---|---|---:|---:|---:|---:|---|
| 2026-11-06 | DraftKings | 50.566 | — | — | 26.3% / — | stopped_explicitly |
| 2026-11-07 | DraftKings | 299.462 | 376.173 | +25.6% | 45.0% / 65.0% | valid |
| 2026-11-10 | DraftKings | 386.698 | 609.536 | +57.6% | 60.0% / 100.0% | valid |
| 2026-11-11 | DraftKings | 187.698 | 251.666 | +34.1% | 40.0% / 60.0% | valid |
| 2026-11-06 | FanDuel | 92.493 | — | — | 28.3% / — | stopped_explicitly |
| 2026-11-07 | FanDuel | 78.669 | 105.301 | +33.9% | 40.0% / 55.0% | valid |
| 2026-11-10 | FanDuel | 75.155 | 107.739 | +43.4% | 45.0% / 65.0% | valid |
| 2026-11-11 | FanDuel | 117.982 | 208.030 | +76.3% | 38.1% / 85.7% | valid |

All six successful replays have zero cap violations, exactly the requested count and physically unique rosters. Their quality losses versus certified feasible optima are 4.88–4.98%. Predicted quality gains versus saved selections are 25.6–76.3%. All six recorded caps-off builds remain caps-off; the Nov. 10 DK case still reaches 100% exposure. This is visible concentration, not a broken or silently relaxed cap.

Nov. 6 DK is infeasible under current hard caps in the frozen pool. Nov. 6 FD does not certify its quality optimum within the 15-second first-stage limit. Both stop without replacement or cap relaxation. Their historical saved portfolios reflect a different cap policy, so do not interpret an unconstrained quality comparison as a feasible improvement. Candidate-recovery behavior in a new full build is tested separately; these replays deliberately hold the candidate pool fixed.

## Actual-score benchmarks

Scores below use uploaded contest player FPTS where present (FD IDs matched directly), then unique same-date/name/team box scores from the frozen PBP audit. Missing or ambiguous players are never zero filled. Scores are not fed to the selector. An asterisk denotes the best *fully graded subset* only: it is a lower bound, not the confirmed portfolio/pool maximum.

| Date | Site | Uploaded field winner | Pool best actual | Saved selected best actual | New selected best actual |
|---|---|---:|---:|---:|---:|
| 2026-11-06 | DraftKings | 370.25 | 358.00 | 298.00 | — |
| 2026-11-07 | DraftKings | 372.0 | 353.50* | 321.00 | 322.25 |
| 2026-11-10 | DraftKings | 302.75 | 298.75 | 260.25 | 263.00 |
| 2026-11-11 | DraftKings | 328.75 | 306.25* | 265.75* | 294.00 |
| 2026-11-06 | FanDuel | unavailable | 366.90* | 278.80* | — |
| 2026-11-07 | FanDuel | 416.3 | 373.90 | 342.20 | 342.20 |
| 2026-11-10 | FanDuel | 371.4 | 328.00 | 328.00 | 328.00 |
| 2026-11-11 | FanDuel | unavailable | 361.30* | 348.60* | 333.30* |

Only Nov. 10 DK, Nov. 7 FD and Nov. 10 FD have complete field/pool/saved/new actual-score comparisons. Nov. 6 DK has complete field/pool/saved scoring but no feasible new portfolio. Nov. 7 DK has 118 ungraded candidates; Nov. 11 DK has 68 ungraded candidates and one ungraded saved lineup. Nov. 6 and Nov. 11 FD lack matching field standings and have substantial box-score coverage gaps. Detailed per-slate counts and missing IDs are in actual-comparison.json. Do not claim improvements or ceilings from starred maxima.

The three complete comparisons show:
- Nov. 10 DK: pool best 298.75 is only 4.00 below the 302.75 winner; the new selected best is 263.00, leaving 35.75 of retrospective candidate upside uncaptured (saved best 260.25).
- Nov. 7 FD: pool best 373.90 is 42.40 below the 416.30 winner; both saved and new selected best score 342.20. Both upstream generation and retrospective selection gaps remain.
- Nov. 10 FD: pool best and both selected maxima are 328.00, still 43.40 below the 371.40 winner. Selecting differently cannot recover a lineup outside this pool.

Higher pregame Top-1% quality is not a guarantee of capturing the hindsight best actual lineup. Gaps to a winner do not by themselves identify which projection, tail, game-state or candidate-search component is responsible. These eight builds cover only four dates, share games and were used in earlier development; no independent profit or significance claim is made.

## Checks and readiness

45 targeted tests passed: NBA selection/caps, pipeline, recovery, UI/export, diagnostics, cash isolation and the shared quality-budget solver. Following the generic runtime-failure preservation guard, six focused NBA quality-budget tests pass, including both certification and unexpected-error recovery. An attempted broad NBA discovery run was interrupted by a blocked external stats.nba.com request; it is not represented as a full-suite pass. Existing UI warning output is retained in test logs.

The integration is ready for review, not represented as deployed. Before broad promotion, assess the explicit certification-timeout rate on larger capped portfolios and validate fresh slates. The shared-policy tests and six successful historical replays establish quality/cap behavior, not a guarantee of live-host timing or profitable lineups. Keep the NBA game-mechanics research offline. Grouped late swap is a separate selector and was not migrated here.

## Reproduction

```
PYTHONPATH=.:tests python scripts/replay_nba_quality_budget.py EVIDENCE OUTPUT.json 0/1
PYTHONPATH=. python scripts/grade_nba_selector_actuals.py WORKSPACE
```

The scoped actual-score script expects nba-selector-evidence, nba-selector-standings, nba-selector-results/actual-replay-*.json and the frozen nba-clock-evidence comprehensive audit in WORKSPACE. Per-build quality output preserves selected player IDs so actual grading evaluates the exact replayed portfolio. No outcomes or simulations are regenerated.
