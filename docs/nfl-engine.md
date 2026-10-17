# Shared NFL engine v2

DraftKings Classic/Showdown and FanDuel Full Roster/Single Game call the same
football simulator. Site scoring and Captain/MVP multipliers are applied later;
the engine returns unmultiplied player outcomes.

Each requested simulation gets its own random game state. NumPy advances games
in parallel through clock, possession, down, distance and field position. There
is no 150-script cap, row bootstrap, final-score projection scaling or zero floor.
Historical player-week usage/efficiency feeds target/carry shares, completion rates,
interceptions and yards. Projections remain a secondary allocation signal.

Touchdowns create a single PAT or two-point attempt. Made field goals award three
scoreboard points and the kicker's distance-specific fantasy points. Pass yards,
pass TDs and conversions credit both participants; turnovers credit the opposing
defense. Defensive touchdowns/safeties are excluded from that unit's opponent's
points-allowed total; conversion points are included. NFL DST scoring has no
yards-allowed adjustment. Actual negative fantasy outcomes remain negative.

Historical profile names are normalized consistently with salary names. Missing
pool players do not stop the underlying opponent offense from playing. No fake
DFS player rows are added. Every player column shares the same game index.

## Validation

Run `python -m unittest discover -s tests -p test_nfl_engine.py` and
`python -m unittest discover -s tests -p test_full_roster_stacks.py`.
The engine tests cover scoring, 10,000 distinct full-game outcomes, finite values,
pass/receiver and turnover conservation, complete scoreboard accounting, one
conversion attempt per TD, missed kicks, negative scores, historical names/2PT/
fumbles, team aliases, incomplete pools and both site scoring paths.

A local synthetic 10-game/200-player benchmark generated 10,000 outcomes in about
17 seconds, using about 169 MiB for stat arrays (not total process memory). This
excludes network loading, lineup building and contest simulation; hosting will vary.

## Limits

This is a simplified regulation-game Monte Carlo model, not a replay of historical
NFL plays or an empirically validated forecast. It does not model overtime,
penalties, timeouts, halftime possession, injuries/substitutions or the full range
of special-teams plays. Some event rates and play-call decisions use fixed model
assumptions. A successful test run establishes bookkeeping/scoring consistency;
it does not validate projection accuracy, tail calibration, field realism or ROI.
Contest-upload feedback is still not wired into model fitting.
