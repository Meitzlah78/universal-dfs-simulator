# NBA build speed: November 13, 2026

## Findings

A full-size four-team synthetic build took 34.20 seconds before this change:
12.57 seconds in game simulation, 3.78 in scoring, and 17.07 in the two portfolio
solver calls (1.94 quality certification plus a 15.13-second diversity timeout).
Selection time was absent from the stage timing display.

NBA's game workload includes explicit player rotations and three independent
scenario sets. This is different from the NFL build path; these measurements do
not establish a universal NBA-versus-NFL runtime ratio or a hosted timing SLA.

## Changes

1. Prepare each overtime period only when a simulation actually reaches it.
   Each requested schedule still uses its original seed and full original batch
   size, including when a calibration pilot sees only a prefix. The ten-period
   overtime limit remains unchanged. All periods are available if needed.
2. When NBA's existing "Diversify within 5% quality budget" checkbox is off,
   return the certified highest-quality feasible portfolio immediately. The old
   path still ran the concentration optimizer with a zero-loss budget. Manual
   and automatic caps stay hard; a quality-certification timeout still fails and
   preserves saved lineups. With diversification on, its existing objective,
   budget and timeout behavior remain unchanged. Shared NFL callers retain the
   prior default behavior.
3. Display and export portfolio-selection time with the other stage timings.
   Existing builds lacking this field still display normally. Changed selector
   request keys invalidate older reselection caches.

No simulation counts, construction seeds, candidates, field-support targets,
event rates, calibration iterations or ranking formulas are reduced. The game
cache fingerprint includes the new overtime implementation. PR #77's mechanics
and PR #79's DD import/display score are separate.

## Measurements

On one saved six-game FanDuel pool (209 players), two paired runs in alternating
order used 10,000 trials per independent phase. Sequential game simulation
averaged **50.21 seconds eager versus 47.02 on demand**, a **6.35% reduction**.
All three outcome arrays and all calibration reports matched exactly in both
pairs. This tests current-engine execution on saved inputs, not reproduction of
the original archived engine or live Streamlit hardware performance.

The full-size four-team synthetic build/export check used 10,000 trials per
phase, 5,000 candidates, 10,000 requested opponent-support rosters and 20 entries.
With the new game code, diversification on took **32.89 seconds**; off took
**17.14 seconds**. Selection took **17.56 versus 1.83 seconds**. Candidate and
ranking-report hashes matched. The off portfolio kept the certified quality
optimum (30.6919 versus 29.2286 with the 5% budget), while concentration increased
from 910 to 978. Both respected the same 30% maximum exposures in this fixture.
This on/off comparison changes an explicit diversification preference; it is
not a same-policy 48% speedup. Uncapped real slates can concentrate more.

These are offline timings, not promises for the hosted app. Feed fetches, UI,
cloud persistence, hardware quotas and solver difficulty can change total time.

## Reproduction and safety checks

`scripts/benchmark_nba_overtime.py ARCHIVE --repeats 2 --output RESULT.json`
verifies the archived input manifest and compares eager versus on-demand
rotation schedules. The new tests check exact schedule/pilot-prefix agreement,
on-demand allocation, all ten overtimes, event-ledger equality, DK/FD market and
player calibration, wider minutes, and three independent seeds. Existing parallel
game, cache, pipeline, selection, UI, exposure and saved-lineup tests also apply.

The full build/export contract is exercised with diversification on and off.
Disabling diversification is an explicit user choice, not a new default.
