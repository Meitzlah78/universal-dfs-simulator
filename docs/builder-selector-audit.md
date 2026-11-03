# Repeatable NFL and NBA builder/selector audit

## Scope and method

The offline command reads a frozen calibration/solver build and completed standings. It scores existing candidate rosters with explicitly published site fantasy points, then compares the saved selection with the available pool. It supports DK Classic/Showdown, FD Full/Single Game, and the captured DK/FD NBA roster layouts.

It never rebuilds lineups using outcomes, fits a model, or changes live rankings. Unknown player scores remain unknown. Candidate ranks assign tied scores the same first rank. Hypothetical single-candidate ranks remove identified own entries and insert one candidate; their tie-split prizes must not be added together as a hypothetical portfolio return. If entry identities are unavailable, the full supplied reference field remains in place and that limitation is explicit.

Nested archive hashes, player IDs, roster uniqueness, candidate/scored alignment and exact exported rosters are checked. NBA accented names use stable IDs where supplied, otherwise deterministic Unicode normalization; there is no fuzzy matching. Blank roster text does not remove an entry's published score from the opponent reference.

## Executed cases

| Saved case | Fully scored / saved candidates | Best pool single-candidate reference rank | Best frozen selection reference rank |
| --- | ---: | ---: | ---: |
| NFL DK Classic Nov 1 | 4,939 / 5,000 | 4 | 12 |
| NFL FD Full Nov 1 | 4,968 / 5,000 | 763 | 763 |
| NFL FD Single Nov 1 | 3,782 / 3,782 | 1 | Final selection unavailable in this package |
| NFL DK Showdown Nov 2 | 5,000 / 5,000 | 13 | 218 |
| NFL FD Single Nov 2 | 5,000 / 5,000 | 1 | 2,627 |
| NBA DK Oct 31 | 1,023 / 5,000 | 25 | 538 among 16 fully scored frozen selections |
| NBA FD Oct 31 | 5,000 / 5,000 | 617 | 24,844 for the 11 build-time selections |

The Monday NFL exports match all 20 entered rosters on each site. NBA evidence is different: none of the 17 captured DK exported rosters match the final rosters for those entry IDs, so the frozen export is a counterfactual selection, not a claim about final entered lineups. One includes Bruce Thornton, whose score is unlisted. The FD NBA package has the 11 build-time selections but no exact latest entry export; final submission is unverified.

Missing DK NBA scores affect 3,977 candidates, covering Bruce Thornton, Jae'Sean Tate, Cody Williams, Micah Peavy, Kris Murray and Alex Karaban. Candidate counts overlap across those players. These rows are excluded, not declared bad or assigned zero. That coverage gap prevents a complete DK NBA builder conclusion.

## What this identifies

Monday's FD NFL pool contains a 115.97-point lineup matching the winning score, but it was ranked 198th by saved Top 1% probability. The DK NFL pool contains a 114.77-point lineup with reference rank 13, ranked 785th pregame. Candidate building captured those outcomes; the simulated ranking did not prioritize them.

That does not prove the portfolio-selection implementation is wrong. A correct optimizer can follow inaccurate probabilities, and one realized game is not enough to learn which forecast/ranking changes generalize. The hindsight best single candidates also do not establish a cap-compliant best portfolio.

FD NBA has both a narrower strong-candidate set (one top-1% candidate among 5,000 on this outcome) and a selection gap. Its best build-time selection scores 298.6 versus the pool's 357.8. This is a historical build-time comparison, not a verified reconstruction of final FD entries.

## Player errors

Every case reports fantasy-point MAE, RMSE and signed bias by position, projection source, projected point band and projected minute band, plus largest absolute misses. Minutes bands describe the frozen forecast; actual minutes/usage errors are not inferred from fantasy scores. Missing raw stats still block role-level validation.

On the captured Oct 31 slate, matched-player MAE is approximately 9.64 DK points and 8.94 FD points (96 and 120 matched observations respectively). Both pools list RotoWire projections. Ty Jerome is a large miss on both sites, but one outcome does not justify a permanent player penalty or wholesale source rejection.

## Reproduce

```sh
python scripts/audit_builder_selector.py \
  --build /path/to/Simmah_Calibration_Solver_Latest_Export.zip \
  --standings /path/to/completed-standings.zip \
  --output /path/to/audit.json
python -m unittest discover -s tests -p test_builder_selector_audit.py -v
```

CSV standings are supported too. Input paths remain local/private; committed reports omit usernames and entry IDs. Build and standings SHA-256 values identify exact sources. Pregame capture provenance is supplied evidence, not independently certified.

Aggregate executed results: `data/engine_validation/2026-11-03-builder-selector-audit.json`.

The next measured targets are rank-probability calibration across independent later slates, NBA projection/opportunity diagnostics, and filling explicit actual-score coverage gaps. This audit is not an active model improvement or proof of profitability.
