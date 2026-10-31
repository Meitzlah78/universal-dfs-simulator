# Offline benchmark: DK Classic, version 1

The benchmark is separate from Streamlit and performs no network requests. It is
an evidence and evaluation tool, not a replacement production builder.

## Freeze evidence

Prepare a contest JSON with `format` equal to `DraftKings Classic`, `owner`
matching the account name in standings, `entry_fee`, final `field_size`, and
`payouts` containing `[first_rank, last_rank, dollars]` ranges.

```bash
python simmah_benchmark.py freeze \
  --players players.csv \
  --portfolio portfolio.csv \
  --field opponents.csv \
  --standings completed-standings.zip \
  --contest contest.json \
  --destination replay-bundle
```

The destination must not exist. The command copies each input, records its SHA256
and byte count, and fingerprints the manifest. Subsequent audits reject changed
files. Freezing evidence now does not prove it was captured before lock.

Raw bundles contain supplied contest entries. Keep them outside source control;
commit only aggregate diagnostic reports.

## Evaluate and compare

```bash
python simmah_benchmark.py audit replay-bundle \
  --projection-baseline --output benchmark-report.json
```

The optional baseline selects 20 lineups when the saved portfolio has 20 entries.
It sequentially maximizes the supplied external point projections, proves each
roster's optimum with SciPy/HiGHS, excludes each previously selected roster, and
limits each player to 80% of entries. Its fixed salary range is $48,000–$50,000.
It enforces DK positions, team limits and no opposing offense against its defense.
It does not impose stack requirements or use ownership. These are explicit
comparison settings, not a reconstruction of every original user control.

Baseline selection completes before the code opens completed standings. Neither
actual scores nor actual ownership chooses baseline lineups. A solve that times
out or fails to reach optimality is reported as a failure, not silently accepted.

Each saved/baseline portfolio independently replaces the owner's original entries.
The evaluator retains opponent entries with blank roster text, uses official
scores, includes ties among the replacement entries, and shares the occupied
prize positions. Missing actual player scores are never assigned zero. Standings
must have final TimeRemaining values and unique entry IDs. The number of replaced
entries and the final field size must match.

The report distinguishes user lineup constraints from legal opponent behavior;
opponents are allowed to roster offense against their defense. It reports actual
score coverage for sampled opponents and never hides excluded rows.

## Boundaries and gates

- Version 1 audits saved portfolios; it does not run the football simulator.
- Only DK Classic is supported. Other formats must be added with their own rules.
- Input validation identifies ambiguous same-team projected QBs and missing
  ownership snapshots. It cannot reconstruct unavailable historical roles,
  timestamped markets or individual-player simulation distributions.
- The projection baseline is a numeric diagnostic on the supplied projections.
  It does not resolve a disputed starter or establish that its inputs are valid.
- Timings cover validation, baseline construction and actual-result evaluation.
  They are not timings for the 10,000-outcome simulation pipeline.
- A slate already used to develop/calibrate a model is diagnostic data, not a
  holdout. Do not report improvement on it as proof of future performance.

Next gates are a verified pregame snapshot schema, a headless simulation runner,
persisted separate construction/evaluation outcomes, per-stage performance
budgets, and comparison on untouched completed slates. Keep live UI changes out
of this benchmark phase.
