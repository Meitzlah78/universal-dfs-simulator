# Cold NFL preparation regression

The November 12 final-context fix (`8c7db8e`) changed a market-enabled cold
preparation from 9 preliminary fitting pilots plus 4 market pilots to those
same 13 pilots plus a second 9-pilot fit: 22 pilots before final sampling.
The extra fit corrected a real problem. In the frozen November 12 WAS-NYG
inputs, reconstructing the earlier single-fit schedule produced a 1.17-point
offensive mean absolute projection residual, versus 0.22 with final-context
refitting. Simply reverting to the earlier schedule would restore inflated
player means. This comparison isolates the fitting schedule on the same
engine; it is not a full replay of the earlier application's other features.

The new policy spends only two parameter updates (three pilots) on the
preliminary market initializer. Market calibration still uses all four pilots,
and the complete eight-update/nine-pilot final-context projection fit remains.
That is 16 pilots instead of 22. The 1,024 fitting draws and separate 10,000
evaluation/construction samples are unchanged. When no market is supplied,
the only projection fit retains its full budget. Explicit smaller final-fit
budgets are never increased by the preliminary budget.

The policy and both fitting budgets are part of cache and pregame metadata.
New-policy candidate replays apply the captured correlation/weather context,
the shortened preliminary budget, market calibration, and the full final refit.
Legacy snapshots retain their original interpretation. Resume/checksum checks,
independent seeds, scores, roster selection, injury checks and exposure limits
are unchanged.

## Numerical validation and limits

`nfl-cold-fit-validation.json` contains the historical reconstruction, tested
alternatives, separate site-specific uploaded input checks, fixed-workload
preparation timing, and the validation thresholds. Site-specific numerical
checks use 240 positive uploaded player projections in the original salary-file
order. Defense forecasts were not included in the uploads. These main-slate
cases use fallback historical roles, the already-accepted rushing parameters,
and a fixed weather scenario; the separate archived WAS-NYG case includes its
frozen historical roles and observed pregame weather. They are numerical
projection-alignment checks, not validation against final player results or ROI.

Checks retain the final-context fit and reject the zero-update shortcut where
it worsens projection alignment. Small differences in fitted event inputs and
simulated player means are possible with the new preliminary budget; this is
not an exact-outcome-parity claim. The underlying conditional-event engine and
its learned parameter values do not change. The active model receives a
code-bound calibration-policy revision with the same original scientific
validation and unchanged parameters, retaining the immutable earlier version.
No 2025 data is used and no research rushing/fourth-down candidate is activated.

Local timings are not Streamlit Cloud guarantees. Fetching history/news and the
remaining candidate, field and contest stages are outside the preparation
benchmark. Checkpoints need the same cache files to remain available. The first
build under changed code must prepare a fresh matching bundle.
