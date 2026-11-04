# NBA build speed, November 4, 2026

The target is a full build within 60 seconds. The live Streamlit host has not yet been timed with this change, so that target is not a guaranteed production bound.

A saved six-game FanDuel pool spent 97 seconds in game scenarios, versus 4.5 seconds in contest scoring and under a second in candidate/opponent search. Optimize the simulation path first.

The shared possession engine now uses fixed-width cumulative sums for large five-player role draws and pair comparisons for duplicate-player validation. Both preserve event order, random number consumption, and input checks. Frozen event-ledger tests cover DK and FD, weighted/zero/single-player roles, and batches on both sides of the optimized path.

The game process pool can use up to four workers when CPU quota, affinity and memory allow. Containers with less than 2 GiB or unavailable memory limits keep the previous two-worker ceiling; CPU limits may further reduce it to one. This is automatic, with no user setting that can overrun the host quota. It does not provision more CPU or migrate hosting.

## Recorded benchmark

Full-size settings: 10,000 simulations for each independent construction/field/evaluation set, 5,000 candidates, 10,000 requested field-support rosters, 101 portfolio entries, 50 diversity and $58,000 minimum salary. The archived slate is October 31 FanDuel, 210 pool players, six games, 71,856 contest capacity. Synthetic entry reservations are used only for testing 101-lineup export validation.

| Work | Before | After |
| --- | ---: | ---: |
| Backend pipeline, cold | 40.55 s, two workers | 28.72 s, four workers |
| Expanded after run: pipeline + entry export validation + local diagnostic ZIP | not measured | 32.17 s |

The expanded run included 0.24 seconds of export validation and 2.72 seconds to create the roughly 9 MB diagnostic ZIP. All three simulated outcome sets, candidate indices, contest rankings and portfolio hashes matched across runs. No sample sizes, rules or limits were reduced.

These are machine-specific timing samples, not a confidence interval or a live-host guarantee. Browser rendering, initial provider fetching and asynchronous cloud upload are excluded. The app displays a total timer covering its build, export validation and synchronous diagnostic capture, alongside existing stage times; that is the next evidence for whether the production host meets one minute.

The JSON benchmark report is `data/nba_speed_trials/2026-11-04-build-workers-benchmark.json`.
