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

## Why Monday's rank-198 exemplar was excluded

An exact neutral-control trace reproduces the current selector's original full-pool selection. Rank 198 is feasible at all 20 steps. Saved manual MVP/FLEX/overall maximums are 100%, no locks/fades/minima are active, and the automatic preferred overall cap is 80% at diversity 50. No hard cap or new stack rule excludes it. It loses the combined normalized pregame Top 1%, cumulative exposure and maximum-roster-overlap objective. Its modeled Top 1% probability is about 2.09%, versus about 5.16% for the highest-ranked candidate.

## Top-250 diversity and random screen

The top 250 are fixed by saved pregame Top 1% scores before outcomes load. Five diversity values (0/25/50/75/100) and a farthest-first combination-distance heuristic are selected without outcomes. Every experiment has the same hard 80% overall player ceiling; the diversity slider also changes a softer preferred cap, recorded separately. None selects the rank-198 hindsight exemplar. Estimated net results for the five settings are -$0.50, -$1.75, -$1.75, -$2.25 and -$4.00; combination distance gives -$0.75.

Uniform 20-of-250 samples are then rejection-sampled under that same hard cap, using seed 20261103. There are 1,000 accepted portfolios out of 1,670 draws. The specific exemplar appears in 77 portfolios (7.7%), near its unconstrained inclusion probability of 8%. Mean net on this one historical result is +$1.1779, but median net is -$1.3864; only 215/1,000 portfolios are profitable. Random sampling performs better in average return on this outcome, but neither its Monte Carlo sample size nor this one missed winner establishes a persistent bias or future edge.

A universal top-250 filter is not justified: the Monday DK candidate with reference rank 13 was ranked 785th pregame, so that filter would discard it. Other saved best candidates also fall below rank 250. Capturing one known FD winner cannot define a general selection policy.

The reproducible FD 20-entry sweep is:

```sh
python scripts/sweep_portfolio_diversity.py \
  --build /path/to/frozen-fd-single-game-package.zip \
  --standings /path/to/completed-fd-standings.csv \
  --trials 1000 --output /path/to/diversity-sweep.json
```

Aggregate sweep and exact objective trace: `data/engine_validation/2026-11-03-fd-diversity-sweep.json`. Four CI tests now include outcome-independent distance/random sampling with fixed caps. No sweep setting is promoted.
