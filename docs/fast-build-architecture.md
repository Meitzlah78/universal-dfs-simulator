# Fast-build architecture

This branch speeds lineup generation without reducing player simulation counts or changing contest/ROI evaluation.

## Mode mapping

| Site / mode | Fast builder architecture | Preserve |
| --- | --- | --- |
| DraftKings Showdown | Existing bounded weighted Captain/FLEX search | CPT 1.5x salary/points, locks/fades, exposures, salary range, ownership, correlation |
| FanDuel Single Game | Bounded weighted MVP/FLEX search modeled on Showdown | FanDuel MVP scoring/roster rules, locks/fades, exposures, salary range, ownership, correlation |
| DraftKings Classic | Bounded slot-aware weighted search with precomputed NumPy metadata | QB/RB/WR/TE/FLEX/DST eligibility, stack rules, locks/fades, exposures, salary range |
| FanDuel Full Roster | Bounded slot-aware weighted search modeled on Classic | FanDuel roster eligibility, stack rules, locks/fades, exposures, $60k salary rules |

## Pipeline boundary

Player/game simulation -> candidate generation -> candidate scoring -> opponent field -> contest/ROI simulation.

The lineup builder must not own the football simulation model. This lets the planned NFL PBP engine replace the current outcome generator later without rewriting roster generation.

## Performance rules

1. Precompute player names, salaries, teams, opponents, positions, eligibility, ranking weights, and name-to-index maps before lineup attempt loops.
2. Use NumPy masks/index arrays inside hot loops instead of repeated pandas row filtering or `np.flatnonzero` name searches.
3. Bound attempts per lineup class/captain/MVP/roster build so impossible salary or lock combinations cannot spin indefinitely.
4. Keep all eligible players available where roster rules allow; weighting controls sampling frequency rather than silently excluding the player pool.
5. Deduplicate canonical lineups during generation.
6. Do not lower the 10,000 player/game simulations merely to make lineup construction faster.
7. Keep opponent-field construction and contest/ROI scoring separate from candidate generation.

## Validation gate

Before merging this branch, verify all four NFL formats for syntax, roster legality, salary legality, locks/fades, stack rules where applicable, candidate uniqueness, ownership/exposure behavior, opponent field generation, and contest/ROI output.
