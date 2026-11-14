# Capture-time and historical-role backfill — offline development evidence

## Timestamp audit

Dated NBA feed timestamps remain offset-free; publication-time semantics are not documented by recovered source evidence. Neither UTC nor America/New_York is certified here. `capture_timing.csv` compares both hypotheses and never marks an as-of status certified.

Six of 16 Ryan/Jones player rows (three of eight build snapshots) are later than capture under both tested hypotheses:

* Nov 6 DK: source row would be 9.70 minutes after capture even if UTC.
* Nov 6 FD: 6.18 minutes after capture even if UTC.
* Nov 11 FD: 0.18 minutes (10.94 seconds) after capture even if UTC.

Those rows cannot establish that an Inactive update was available to those builds. Other rows being earlier under the UTC hypothesis does not establish the timezone or historical publication time. No player was retrospectively removed.

## Independent role prior

Backfilled 4,255 explicit participation records from 159 verified regular-season regulation games. Ten records were excluded for unknown participation, missing starter flags or invalid regulation minutes; preseason records are excluded separately. Prior recorded starts are historical outcomes available after their games, not current-game starter labels.

For each historical label game, role features use only earlier dates with completion before that game's first observed PBP timestamp. Current-build features and training labels use only earlier dates with completion before capture. Fixed research rules: last five explicit observations, at least three observations; starter rate >=0.5 defines historical-starter versus historical-reserve. The role prior is the league conditional minutes mean learned from at least 20 earlier same-role outcomes. These rules are not tuned to the one injury-heavy team-game.

2,841 chronological training examples support historical-role priors for 1,891 of 2,134 player snapshots. The remaining 243 have fewer than three earlier regular-season role observations and receive **no numeric prior**. Missing games are not added as zero minutes or nonstarts. This historical-role prior does not certify present eligibility, a current starting lineup, contract/two-way status, or injury promotion.

Ryan/Jones have zero regular-season role observations; both remain unsupported. Herro's MIL–ORL historical-starter prior is 28.6832 minutes. This is a shrinkage prior, not his final projected minutes, and there is no claim that it restores his minutes. Requiring a chosen player's forecast to move toward a known actual outcome would be a hindsight tuning rule, not a readiness gate. MIL–ORL, POR–SA and ATL–WAS remain diagnostic cases, not promotion targets.

## Exact denominator / conflict-rate status

The denominator is 159 verified regular-season games. All 159 lack a certified pregame eligible-pool snapshot under the current evidence contract; 0 are allocation-evaluable. Input-blocked coverage is **159/159 (100%)**. Genuine allocation-conflict rate is **not evaluable**, not 0% and not 100%. `game_conflict_coverage.csv` records each case with a null allocation-conflict field. Postgame participants cannot substitute for pregame eligible rosters.

Therefore no side-by-side final minutes residuals or claimed steady behavior on POR–SA / ATL–WAS are reported. Independent historical-role priors are now reproducible, but a verified current availability/lineup source remains necessary to run the combined benchmark.

## Validation and isolation

99 targeted tests pass. New tests cover current/future outcome perturbation invariance, strict earlier-game role construction, missing-history support, same-day exclusion and no implicit nonstart rows. Earlier conservation / conflict / injury-promotion tests remain passing. No production imports or defaults changed; PR #77 remains separate and offline.
