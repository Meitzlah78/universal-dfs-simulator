# Small-portfolio NBA FanDuel concentration speedup

NBA FanDuel portfolios of up to 25 entries use an exact, tightened formulation
for the second, concentration-minimization solve. The first quality-optimum
solve, exposure constraints, independent validation and timeout fallback remain
in place. Positive Diversity values retain the live 5% aggregate quality-loss
budget; zero disables diversification. No slider scaling is introduced.

The tightened formulation removes a candidate only when even its strongest
possible companions cannot reach the existing quality floor. For each player,
upper bounds on quality at each appearance count restrict the square-function
epigraph to feasible count ranges. The already-certified quality optimum also
provides an incumbent objective bound. These are pregame bounds, not a heuristic
top-N filter. No actual scores, ranks or payouts enter selection.

Selected lineups may differ among tied optima or time-limited incumbents. The
guarantees are the same objective, quality floor, exposure limits and validated
count; identical realized fantasy scores are not promised.

The shared solver's tightening flag defaults off. NBA enables it for FanDuel
counts up to 25. Larger FD portfolios, NBA DraftKings and NFL use the existing
formulation. Only positive-diversity, small-FD selection cache keys receive the
new formulation marker; other existing keys are preserved.

## Repeated local benchmark

Three repeats per formulation with alternating execution order. Both arms use
the existing 5% budget, saved pregame Top 1% metric, the same candidate pool and
the exposure limits derived from that saved pool. Source manifests are checked.
The first five cases retain their saved portfolio counts. The November 4 case
uses a controlled 25-entry count from its saved candidate pool to test the
rollout boundary; it is not a replay of its original 101-entry portfolio.

| Slate | Candidates | Entries | Original median wall time | Tightened median wall time |
|---|---:|---:|---:|---:|
| November 7, 2026 | 755 | 20 | 1.495s | 0.840s |
| November 10, 2026 | 632 | 20 | 2.816s | 0.766s |
| November 11, 2026 | 5,000 | 21 | 8.963s | 3.564s |
| November 13, 2026 | 5,000 | 20 | 9.770s | 2.550s |
| November 14, 2026 | 5,000 | 20 | 15.355s | 5.124s |
| November 4, 2026, controlled boundary | 5,000 | 25 | 5.288s | 3.579s |

Across these 18 measurements per formulation, median wall time was 7.403s
original versus 3.072s tightened; maximum was 15.384s versus 5.185s. Tightened
certified concentration optimality with reported 0% MIP gap in all 18 runs.
Original certified 15/18; the three November 14 repeats stopped at a 1.1901%
gap. All certified original concentration optima matched tightened. At November
14, original returned squared concentration 1538 and tightened certified 1526.
Every returned portfolio passed the quality floor and exposure/count validation.

Times include selection preparation and both solves. Metadata also records
separate stage times, concentration status, MIP gap, dual bound and retained
candidate count. The configured solver limit is 15 seconds per stage; it is
not a hard wall-clock guarantee. These are local selection measurements, not
end-to-end simulation or Streamlit build timings.

## Stress-case rollout guard

The source November 4 portfolio has 101 entries. Explicitly forcing the new
formulation at that size returned the certified quality-optimum fallback with
concentration 27437, while original found a feasible incumbent at 26173. Neither
certified concentration. The new formulation is therefore disabled above 25
entries. The November 6 source has 60 entries; both arms stopped at the first
quality-certification stage. That first-stage limitation is not changed here.
Neither stress case is included in the small-portfolio timing aggregate.

## Reproduce

```bash
python scripts/benchmark_fd_concentration.py PRIVATE_ARCHIVES... --repeats 3 --output /tmp/fd-times.json
python scripts/benchmark_fd_concentration.py PRIVATE_BOUNDARY_ARCHIVE --portfolio-count 25 --repeats 3 --output /tmp/fd-boundary.json
python -m unittest discover -s tests -p test_nba_fd_concentration.py -v
python scripts/check_nba_build.py
python scripts/check_nba_build.py --full-scale
```

The benchmark explicitly forces both formulations to expose regressions outside
the rollout range. Private source ZIPs and raw run outputs are not committed.
Quality-certification failures are recorded and stop subsequent repeats of that
case. The benchmark never loads actual player or contest results.

New tests cover exhaustive small-instance optimality, quality-floor preservation,
manual minima, infeasible locks and duplicate rosters, missing-incumbent timeout
recovery, single-entry pruning, unchanged diversity budgets, FD/DK routing,
the 25/26-entry cutoff and selective cache invalidation. Local validation also
passed the 429-test NBA/build/storage suite (one skipped), 37 NFL selector/UI
checks, 26 final focused checks, and the full-scale build-to-export regression.
