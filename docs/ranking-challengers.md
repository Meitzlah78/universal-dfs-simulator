# NFL/NBA ranking challenger comparison

This is a retrospective screen, not an active ranking change or a prospective trial. It follows the builder-versus-selector audit and uses four NFL latest-export packages plus two NBA build packages. The older FD Single Game package lacks the final settings/export checkpoint required by this comparison and is not silently assigned guessed settings.

## Outcome-blind selection

Five fixed methods are compared: saved Top 1% probability, saved win probability, saved expected prize, saved simulated mean points, and an equal-weight percentile-rank blend of Top 1%, expected prize and mean points.

All challenger portfolios are selected before the results file is loaded. Actual scores and actual-score availability cannot filter candidates. Every method uses the same saved pool, entry count and current shared selector. NFL uses saved manual controls and diversity. NBA uses current hard limits derived from the frozen pool (overall, minutes and ownership rules); historical hidden manual overrides are unavailable. Platform metadata is restored before interpreting NBA ownership.

This is a comparison under equal current rules, not an exact replay of an older selector implementation. Diversity's normalized score objective means the methods can affect both rank order and the quality/diversity tradeoff. Feasibility constraints are identical; realized exposures need not be.

Identified original entries are removed and the entire new portfolio is inserted jointly. Own-entry ties and opponent ties share the occupied payout positions. Unsupported player scores make the entire portfolio's return unknown; incomplete lineups are not discarded or assigned zeros. Entry IDs and usernames do not appear in the aggregate report.

## Observed joint net returns

| Case | Top 1% baseline | Win rate | Expected prize | Mean points | Fixed blend |
| --- | ---: | ---: | ---: | ---: | ---: |
| NFL DK Classic Nov 1 | $0.30 | $0.20 | $0.20 | -$0.50 | $0.80 |
| NFL FD Full Nov 1 | $3.55 | $3.41 | $3.31 | $2.53 | $3.30 |
| NFL DK Showdown Nov 2 | -$0.40 | -$0.20 | -$0.40 | -$1.00 | -$1.40 |
| NFL FD Single Nov 2 | -$3.75 | -$3.25 | -$3.25 | -$2.42 | -$3.00 |
| NBA FD Oct 31 | -$0.55 | -$0.55 | -$0.55 | -$0.55 | -$0.55 |
| NBA DK Oct 31 | Unknown | Unknown | Unknown | Unknown | Unknown |

These are counterfactual portfolio returns using the supplied ladder, not account statements. The current Top 1% replay can differ from the original historical export because selector versions changed. None of the alternatives consistently beats this normalized baseline. The DK NBA selections contain unlisted player scores; none receives a certified return.

## Rank correlations and top-5% screening

Monday's FD NFL winning-score exemplar ranks 198th of 5,000 by Top 1%, 1,813th by win rate, 893rd by expected prize and 411th by mean points. Only Top 1% places that exemplar inside the top 250. Top-250 inclusion does not imply selection into a constrained 20-entry portfolio.

Across that Monday pool, Top 1%'s pregame top 250 contains 38 hindsight top-5% candidates (15.2% precision). Expected prize contains 14 (5.6%); win rate 10 (4.0%); mean points 43 (17.2%). These are overlap precision values, not the probability a lineup wins or the fraction of all elite lineups recovered. Ties can expand the hindsight elite set beyond 250.

On NBA FD, Spearman correlation with realized fantasy points is 0.3592 for Top 1% versus 0.3515 for expected prize; top-5% precision is 15.6% versus 14.0%. On the fully scored DK NBA subset, correlations are 0.3288 versus 0.3218 and precision is 9.62% for both. DK's missing outcomes make that a conditional subset diagnostic, not a full-pool verdict.

A saved inverse ownership-sum proxy is screened only where available and is explicitly not expected payout or ownership-product leverage. A geometric-mean return or Sharpe ratio is not reconstructed from an aggregate expected ROI column; it would require appropriately defined scenario returns, stake/bankroll and risk objectives.

## Validation boundary

Earlier outcomes had already been inspected before constructing this screen. Re-running them with another label is not a new independent holdout. DK and FD contexts of the same slate/game are not independent validation games. A high correlation does not guarantee top-tail capture, and a better historical return does not establish a future improvement.

No method is promoted. Keep this protocol fixed for later frozen slates, then evaluate complete portfolio returns and tail capture by independent slate/date clusters. Any choice of method or weights from these historical cases must be tested on untouched later outcomes. The live default remains unchanged.

## Reproduce

```sh
python scripts/compare_portfolio_rankings.py \
  --build /path/to/frozen-calibration-package.zip \
  --standings /path/to/completed-standings.csv \
  --output /path/to/ranking-comparison.json
python -m unittest discover -s tests -p test_ranking_challengers.py -v
```

Both CSV and ZIP standings are supported. Tests check that changing an actual-score column cannot change selection or relax a manual cap, and that multiple own entries receive the correct joint tie share.

Aggregate report: `data/engine_validation/2026-11-03-ranking-challengers.json`. Source hashes, constraints and scoring coverage remain alongside every case.
