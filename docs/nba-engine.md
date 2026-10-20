# NBA implementation status

FanDuel NBA enters a separate route from NFL. The original nine-slot entry CSV
supplies IDs, positions, salaries and game pairs. Historical FPPG is not a
projection. DFF and RotoWire positive projections are averaged, uploaded CSV
values take priority (including exclusion by zero), and OUT players are ineligible.
RotoWire supplies projected minutes with exact date/game/slate guards.

## Numerical core

- Screenshot-verified FanDuel scoring: points + 1.2 rebounds + 1.5 assists +
  3 steals + 3 blocks - turnovers. Made threes are not counted twice.
- Experimental NumPy minutes sampler conserves 240 regulation team minutes,
  caps individuals at 48, and assigns unmodeled reserve minutes no fantasy points.
  Minute uncertainty and blowout flags are caller inputs, not fitted estimates.
- NumPy lineup scoring shares scenario/player outcomes across all lineups and
  processes bounded batches. Local synthetic benchmark: 5,000 nine-player
  lineups by 10,000 scenarios, 83 players, float32: 0.279 seconds. This excludes
  outcome generation, field ranking, I/O and hosted execution.

## Historical data

ESPN final-game PBP requires the game's date to precede the target slate and the
last event score to match the box score. Six games from October 21-22, 2025
preserved total points in initial possession reconstruction. This is a score
ledger check, not independent validation of every possession boundary.
Technical/retained-possession free throws, reviews and unclear control changes
are flagged, not silently treated as clean observations.

Rotation reconstruction uses box-score starters, substitutions and evidence of
participation before a first substitution. Unresolved initial lineups invalidate
the corresponding team-period. In the first test game, one overtime team-period
had only four identifiable starters and remains unresolved.

## Experimental forward events

`simmah_nba_engine.py` now simulates quarters and optional overtime using explicit five-player
rotations and caller-supplied event rates. Made field goals generate scoring and
optional non-self assists. Misses create rebound opportunities and possible
blocks. Turnovers create possible steals. Offensive rebounds retain possession.
Free throw trips distinguish final missed attempts from earlier dead-ball misses.
NumPy batches scenarios while the event loop advances shared game clocks.

A synthetic 10,000-game regulation benchmark took 1.673 seconds locally. This
uses equal role weights and illustrative rates, not trained NBA parameters. It
excludes model fitting, rotation generation, overtime and contest evaluation.
Regulation ties require explicit overtime rotations. Ties remaining after the
supplied overtime periods are marked `requires_overtime`; they are not final
game outcomes. Period-crossing actions are discarded at the boundary. Individual
shooting efficiency, fouls and coaching decisions need further development.

NBA roster validation and an offline entry export helper now preserve the
nine-slot header and original entry/player IDs. The helper requires an explicit team limit. FanDuel rules at
https://www.fanduel.com/rules (Lineup Restrictions, checked October 20, 2026)
require at least three teams and no more than four players per team for most
multi-game contests. The NBA validator now also enforces the three-team minimum.
These helpers remain disconnected from the live BUILD/export interface.

## Not ready for builds

The forward core, fitted event rates, calibrated rotation or injury probabilities,
NBA opponent model, portfolio evaluation and entry export are not connected yet. The NBA BUILD button remains disabled. Next work must validate
rotations and possession reconstruction broadly, fit historical rates without
lookahead, then implement and test shared forward events and legal lineups.

## Preliminary historical fit

`simmah_nba_fit.fit_baseline` estimates pooled event rates from pre-slate team box
scores, with unique-game and date guards. Its default minimum is 30 games. An
explicit exploratory override on six October 21-22, 2025 games produced 14.24%
turnovers per modeled action, 41.98% three-point attempt share, 57.56% two-point
shooting, 34.00% three-point shooting, and 79.28% free throws. These observations
are not season-wide estimates or an out-of-sample validation. FTA/2 is an
approximation to trips; team/personal turnovers and player-specific efficiencies
remain unresolved. This fit cannot by itself enable NBA builds.

### Expanded historical audit

The offline audit of April 1–10, 2026 requested 70 completed games.
One game (401810990) failed the official final-score check and was excluded.
The remaining 69 games split chronologically into 59 fitting games and 10 held-out
games beginning April 9. All 69 reconstructed score ledgers matched final totals;
67 had complete rotation reconstruction. Incomplete rotations remain flagged.
This is a source/reconstruction audit, not evidence of predictive accuracy.
The fitted rates are experimental and are not installed as live build defaults.

Reproduce with:
```sh
python scripts/nba_history_check.py --start 2026-04-01 --end 2026-04-10 --before 2026-10-20 --cache /tmp/simmah-nba-corpus --output /tmp/nba-corpus-audit.json --limit 70 --holdout 8
```

Player allocation rates now use historical FGA, AST, REB, STL and BLK per minute,
shrunk toward pooled rates with a fixed 120-minute prior. ESPN player IDs retain
identity across team changes. The audit's 59 training games yielded 434 players;
215 held-out player-games included 211 with fitted player history.
Conditional on actual minutes, player/pooled MAE was 2.325/2.634 FGA,
1.429/1.610 AST, 1.722/2.055 REB, .714/.721 STL and .503/.532 BLK.
These are allocation diagnostics, not fantasy-point or pregame-minute accuracy.
The role model is offline and has not been connected to live NBA builds.

### Minutes baseline check

A frozen chronological baseline used each player's last three regulation games
from the same 59-game training set. On 152 covered held-out player-games, minutes
MAE was 5.743, RMSE 7.239 and bias -0.629 minutes. The full-training mean baseline
had MAE 5.783. Another 63 player-games lacked three historical observations.
Overtime is excluded from this regulation-only diagnostic. Holdout results never
update the fitting history. This conditions on participation and cannot measure
DNP risk, pregame injury information, or redistribution after scratches.
Consequently recent averages do not replace RotoWire's pregame projected minutes.
Historical uncertainty calibration still requires a larger sample and a separate
validation set before any tuned uncertainty model enters live builds.

### Rotation scheduling bridge

Complete team-minute arrays now convert into 48 one-minute on-court lineups per
scenario. Integer apportionment preserves 240 team minutes, five distinct players
per minute and at most 48 minutes per player. Missing reserve minutes are rejected.
This is a feasibility schedule, not learned coaching or substitution timing.
A synthetic 10,000 team-scenario run took 0.206 seconds locally. Integration tests
feed these schedules into the shared forward engine. Live NBA builds remain disabled.

### NBA market environment

The contest tab extracts complete two-sided totals/implied scores from the
existing RotoWire odds fields, rejecting conflicting or inconsistent values.
Spreads are displayed relative to the named first team (negative means favored).
Manual per-game totals and spreads override automatic values. The refresh button
reloads the same RotoWire projection/odds cache, with its existing 15-minute TTL.
The experimental simulate_market_game entry point fits team shooting event
probabilities to implied scores using separate pilot/evaluation seeds. Player
fantasy points are still computed from credited stats, not multiplied afterward.
Calibration residuals are returned explicitly, including a four-point tolerance
flag; market totals alone do not identify pace. Live NBA builds remain disabled.
A fresh external odds request timed out during this change, so live feed and
Streamlit rendering were not reverified; extraction/calibration tests passed.

Market calibration stress check (synthetic five-player rotations, 10,000 games,
fixed seed 37; wall time includes four 1,024-game pilot passes):

| Team targets | Evaluation means | Seconds |
| --- | --- | --- |
| 95 / 100 | 95.009 / 100.024 | 3.026 |
| 115 / 115 | 115.792 / 115.475 | 3.157 |
| 125 / 130 | 124.952 / 129.963 | 3.282 |
| 130 / 100 | 130.117 / 100.091 | 3.104 |

This checks numerical targeting on synthetic inputs, not player prediction,
real-world spread coverage, or the accuracy of the market itself. Separate
contract tests ensure changed targets trigger changed event-rate calibration and
conflicting source rows cannot produce an automatic market.

### Conditional historical event check

scripts/nba_conditional_check.py runs fitted event rates and player role weights
on held-out games using their recorded participating players and minute budgets.
A guard rejects overlapping game IDs. Changing held-out actual points does not
change simulated scores (covered by a regression test). This deliberately does
not use postgame points as calibration targets. Box minutes are normalized to
240 only when their rounded ledger lies within 235–245; overtime is excluded.
The ten-game check uses 1,000 scenarios per game. Without historical market
snapshots, pooled shooting produces similar team means and cannot reproduce
pregame team-strength differences. This diagnostic is not a full pregame backtest
and does not establish that the new market calibration improves predictive error.

### Archived closing-line comparison

ESPN summary pickcenter records expose DraftKings provider ID 100 with explicit
pointSpread home/away close lines and total over/under close lines. The loader
requires both sides to agree and uses competitor team IDs, never default/open
values. These records were retrieved after completion, so their closing labels
are not independently frozen pregame timestamps. The ten retrieved records are
retained in data/nba_validation/2026-04-09-10-closing-lines.json.

On the same ten held-out games, 1,000 scenarios each, conditional on recorded
participants/minutes, archived-market anchoring reduced team-point MAE from
9.853 to 8.802 and mean bias from +2.153 to -0.135. Maximum evaluation mean
residual from a market target was 1.407 points. No holdout final score was used
as a target. This small conditional comparison supports the calibration path;
it does not validate live player projections, injury handling, ROI or accuracy
across future slates. Re-run the conditional script with --markets pointing to
the retained JSON to reproduce the market-conditioned calculation.

### Batched candidate construction

simmah_nba_candidates.build_candidates accepts shared slate outcomes aligned to
original pool rows, preserves the uploaded nine-slot order, and returns indices
into that same pool. Positive projections, injury exclusion, salary limits, nine
distinct players, at least three teams and at most four players per team apply.
Candidates follow individual joint slate outcomes with modest search noise;
portfolio exposure diversity is a separate downstream decision. Search is bounded,
uses canonical roster sets to reject duplicates across flexible-slot assignments,
and reports shortfalls without duplicate padding. This is heuristic search, not
proof that all feasible or optimal lineups were found. Independent evaluation
outcomes remain required to avoid construction/evaluation reuse.

A synthetic 40-player fixture generated 5,000 unique legal candidates from 39,424
attempts in 0.212 seconds locally; this is not a live slate or end-to-end benchmark.
Legality, reproducibility, zero/OUT exclusions and bounded shortfalls are tested.
The live NBA route remains disabled pending integration and validation.

### NBA contest and portfolio boundary

simmah_nba_contest.evaluate_candidates grades candidates on independent supplied
outcomes in bounded batches. It requires an exact payout vector for every contest
position and positive integer opponent multiplicities. Scores use integer tenths
to preserve FanDuel ties. Prize pools across occupied tied ranks are divided by
the total tied entries, including duplicate opponents. Win, Top 1%, cash and ROI
metrics are produced. A distinct evaluation seed is mandatory; callers remain
responsible for actually generating independent outcomes rather than relabeling
an array. No field-size scaling is inferred silently.

This is marginal single-lineup evaluation against the supplied field. Other user
entries are not jointly inserted and the output is not a joint portfolio ROI
simulation. Opponent ownership modeling and a complete live NBA build route are
still pending. select_entries maps candidate indices back to original player IDs
and reuses the shared exposure/overlap selector with Top 1% default. Changing
exposure diversity reselects these saved candidates without rerunning the engine.
Tests cover weighted duplicate ties, payouts, independent-seed guards and a
20-entry selection with a 60% maximum exposure preference.

### Ownership-shaped opponent field

simmah_nba_field.build_field fits probabilities over a supplied finite legal
roster support to complete ownership targets. Input percentages must be finite,
between 0 and 100, and sum approximately to 900 for the nine-player format.
The source label is mandatory. Flexible-slot permutations are deduplicated before
fitting. L-BFGS fits marginal frequencies, then multinomial sampling produces
integer duplicate-entry copies without materializing the whole field. Returned
expected/sampled frequencies, maximum target error, optimizer status and unique
roster counts make shortfalls visible. This is a marginal ownership model, not a
learned joint distribution of real NBA entrant behavior.

The public RotoWire NBA players endpoint for slate 29784 returned 67 rostership
values totaling 1340.7 on this check, not 900. Consequently the raw RST column is
shown with an unverified label and is not automatically supplied to field fitting.
No normalization is used to silently reinterpret this discrepancy. Matching,
semantics and source freshness still need verification before live use. The
field module rejects incomplete or unsupported ownership targets. Tests verify
50,000 sampled entries, duplicate compression, target-fit error and reproducibility.

### Offline orchestration

simmah_nba_pipeline.run_pipeline now connects candidate simulation/search,
independent opponent support/search, ownership fitting, independent contest
scoring and saved-candidate portfolio selection. Defaults retain 10,000 scenarios
per set, 5,000 candidates and up to 10,000 distinct field-support rosters. Three
separate seeds and exact-array reuse checks guard against accidental scenario
reuse. Ownership mismatch above the explicit tolerance stops the run. Integer
field copies cover the supplied payout vector's whole contest, without a guessed
field-size multiplier. Progress hooks expose the pipeline stages.

export_portfolio validates and inserts original player IDs into reserved entry
rows using the existing NBA export guard. An integration test covers the full
path with synthetic outcomes/ownership and preserves all five original entry
IDs. The production pregame outcome_factory adapter and verified ownership
source remain prerequisites; this offline integration does not enable the live
Streamlit NBA button or claim a validated full pregame backtest.

### Pregame engine adapter

simmah_nba_pregame.PregameEngine supplies the offline pipeline's outcome_factory
contract. It requires complete provider-projected 240-minute team rotations,
historical FGA/AST/REB/STL/BLK per-minute role weights, complete exact-match market
lines, and an explicitly supplied historical event-rate baseline. It maps shared
game outcomes back into original salary-pool order, with ineligible players zero.
The RotoWire parser now retains historical role rates separately from projected
minutes and fantasy projections. Missing rookie history is not treated as zero.

The current slate's provider rotations total 240 per team, but Labaron Philon
(PHI, 10 projected minutes) and Aday Mara (OKC, 3) have zero historical games.
The strict adapter rejects these missing roles by name. Explicit, sourced rookie
priors remain needed. Projected minutes are currently fixed scenario budgets;
minute uncertainty, coaching and injury redistribution remain uncalibrated.
Unresolved overtime is reported, and player means are not yet anchored to the
external fantasy projections. This is an experimental adapter, not live readiness.

### Explicit rookie role priors

simmah_nba_role_priors fits G/F/C per-minute role rates from the frozen 59-game
historical training partition (cutoff April 9, 2026). Sample minutes: G 14,595,
F 9,986, C 3,856. Multigroup observations are split proportionally. Both event
rates and position priors are retained in data/nba_models with source game IDs,
cutoff, counts and experimental status. Future-dated models are rejected.
Only eligible players with positive external projections and projected minutes
receive missing role rates; projections are never created or overwritten.
The player pool labels estimated Role Rate Source explicitly.

The actual uploaded 83-player slate ran 1,000 scenarios using cached public
RotoWire inputs plus explicit rookie priors for Philon and Mara. Team means were
NY 117.853 vs target 118.5; PHI 114.184 vs 114; OKC 115.497 vs 115.5;
SA 117.302 vs 117. Regulation ties remained 2.8% and 2.5% respectively.
This validates input plumbing and market targeting on the actual salary pool;
it does not establish player mean calibration or live-build readiness. Overtime,
external player projection anchoring and ownership verification remain pending.

### Bounded overtime in the pregame adapter

Rotation scheduling now supports explicit period lengths, including five-minute
OT schedules with 25 player-minutes and five distinct players per minute. The
pregame adapter supplies four OT periods per scenario, using proportional provider
minute shares as an explicit experimental rotation assumption. This is not a
learned clutch/coaching model. Market calibration and evaluation both include
the supplied overtime, preserving all stat-based player scoring. Ties beyond the
bound remain unresolved in reports; no forced winner or invented points are used.

A repeated 1,000-scenario check on the actual 83-player uploaded slate needed OT
in 2.8% (NY/PHI) and 2.1% (OKC/SA) of scenarios; none remained unresolved.
Evaluation team means were 117.969/113.882 and 114.808/117.920, within 0.92
points of their market targets. scripts/nba_provider_check.py reproduces the
input-to-engine check from cached provider player/projection JSON and the upload.
The prior regulation-only tie figures above describe the earlier implementation.
External player-mean anchoring and verified ownership still block live builds.

### External player-mean anchoring

simmah_nba_projection_anchor fits role allocation weights to positive external
fantasy-point projections using a fixed pilot seed and a separate diagnostic seed.
It adjusts bounded team assist probabilities (.05–.95) to align aggregate fantasy
scoring budgets. This is an explicit modeling assumption, not an externally
projected assist count. Final fantasy points always derive from credited events;
no score multiplication or point offsets are applied. Market shooting calibration
runs again after player fitting, and both player and team residuals are reported.
Arbitrary inconsistent target vectors are not guaranteed attainable.

PregameEngine caches the fitted profiles and event rates for its immutable input
snapshot, reusing them across independent construction, field and evaluation
seeds. Recreate the engine when projections, rotations or markets change. The
cache does not reuse simulated outcomes. scripts/nba_provider_check.prepare_inputs
now makes the cached-provider input path reusable for diagnostic scripts.

Actual uploaded 83-player slate, 10,000 scenarios, 1,024-scenario fitting pilots:
NY/PHI player mean MAE .154, max .504; OKC/SA MAE .137, max .382.
Team scoring residuals were +.076/+.022 and -.447/-.031 points; no unresolved ties.
The first two-game run including fitting took 14.822 seconds locally. A second
independent 10,000-scenario run reused only the fitted parameters and took 4.932
seconds, with player mean MAE .162 and .167 (max .475 and .360).
These quantify target alignment, not predictive accuracy or tournament edge.
Projected minutes remain fixed, and verified ownership is still unavailable.

### Explicit relative-popularity estimate mode

The RotoWire discrepancy persists after matching the uploaded eligible pool: all
43 positive-projection, positive-minute players sum to 1340.7%; excluded players
contribute zero. This is not explained by OUT or duplicate source rows.
sample_popularity_field therefore offers a separate, explicitly estimated mode:
a legal roster's log weight is .5 times summed log raw popularity scores, with a
0.1 floor. This treats raw RST only as relative popularity under an assumption,
not as verified percentages or proportionally normalized ownership. Expected and
sampled legal-field marginals total 900%; effective support and largest roster
probability are reported. The pipeline's projected-target mode stays distinct.

An actual-upload pipeline run used 10,000 scenarios for each independent set,
5,000 candidates, up to 10,000 independent field-support rosters, the supplied
259,740-capacity contest and its $15,000 payout schedule, and selected 20 entries.
Runtime was 41.319 seconds locally. The 259,739 modeled opponents compressed to
8,165 unique sampled rosters with integer copies; estimated ownership summed to
900%. This is a successful integration run, not evidence of realistic opponent
ownership or calibrated ROI. Live UI integration remains pending.

The user-supplied contest preset is retained under data/nba_contests. Its loader
checks contest ID, slate date and fee, contiguous descending paid tiers, capacity
and prize-pool total. No unrelated or historical contest gets the preset by name.

### NBA workspace and lineup monitor

The experimental NBA build route is now connected to the supported uploaded
FanDuel contest preset. The right panel builds the tested pipeline, saved
candidates appear in Build, and Lineups shows the selected portfolio, estimated
ROI, exposures and the FanDuel edit-entries download. Diversity/ranking reselect
saved candidates. Changed numerical inputs or minimum salary preserve the prior
results visibly while disabling stale exports. Confirmation labels alone are not
numerical model inputs and do not force a rebuild.

A responsive game strip above the tabs shows market-implied scores and separate
team lineup badges. Confirmed requires exactly five source-identified starters
with explicit true confirmation flags and no OUT starter; five unconfirmed
starters are Expected. Missing or partial data is not displayed as confirmed.
The lightweight RotoWire NBA player/lineup feed is checked in a 60-second
Streamlit fragment, independently of projection/engine execution, and links to
RotoWire's NBA starting-lineups page. Team status and starting-five identity are
compared against the applied snapshot for the current slate. The existing sticky
refresh button turns red on a status or starter change and remains red until a
successful refresh applies fresh RotoWire data. An unavailable source does not
produce a false change or retain a stale green confirmation indefinitely.

The supported NBA preset now permits experimental builds, superseding earlier
notes that the button was disabled. Ownership remains an explicitly estimated
relative-popularity model, minutes are fixed provider budgets, and ROI remains
unvalidated. Streamlit AppTest covers game badges, confirmation change/red alert,
refresh acknowledgment, build, exposure re-selection without engine reruns,
entry-file preparation and stale-export blocking. It does not establish
Streamlit Cloud's live network availability or downstream FanDuel acceptance.


### Fast NBA late swap

The Lineups tab now accepts a fresh filled FanDuel NBA entries CSV in the
NBA LATE SWAP expander, independently of the full-build preflight or saved
contest ROI. Refresh projections first, upload current entries, run FAST LATE
SWAP, review changes, then download and promptly upload the edit-entries CSV.
Only the selected contest is changed. Entry IDs and reference cells are preserved.

A bounded SciPy/HiGHS assignment optimizer uses current external projections,
a soft exposure penalty, positional eligibility, the $60,000 cap, selected
minimum salary and maximum four per team. It does not rerun simulations or claim
live ROI. Already-started players remain in their exact uploaded slots, even
when OUT or lacking a projection. Newly added players must have positive
projections, be active, and have a future start. Team start times are inherited
from consistent RotoWire player records; absent/conflicting clocks block swaps.
Naive source times mean Eastern. Scheduled tipoff is a conservative lock, not
a live FanDuel lock feed; use only for contests permitting late swap.

Search allows up to 0.5 seconds per entry within a 10-second overall solver
budget. Failed or remaining entries stay unchanged and are reported. New
solutions exclude previously selected player sets; unchanged originals can
still duplicate. The export is revalidated against current time every five
seconds while connected; files already downloaded cannot be revoked, so upload
before the next tipoff. No actual FanDuel upload acceptance has been tested.
A 20-entry synthetic local benchmark took 0.17 seconds; hosting and slate size
affect runtime. Tests cover exact tipoff, missing/conflicting clocks, locked
OUT players, open OUT replacement, cross-slate rejection, timeout preservation,
newly locked export rejection and preservation of other contests/reference data.

### Fast NBA late swap

The Lineups tab includes a separate fast late-swap panel, available without a
saved pregame simulation or known payout preset. Upload the latest filled
FanDuel entries CSV. The selected contest is updated by entry ID; other contests
and reference-table cells remain intact. Scheduled game times are grouped by
team, with missing/conflicting clocks blocking the operation. At tipoff, existing
players are frozen in their exact slots, including players subsequently marked
OUT or without projections; no started player can be newly added.

The SciPy/HiGHS assignment optimizer updates only unlocked slots against refreshed
external projections, with a sequential exposure penalty controlled by diversity.
It respects the $60,000 cap, minimum salary, positions, unique players and team
limits. This is projection-based emergency optimization, not a fresh contest
simulation or live ROI calculation. New duplicate roster sets are excluded;
existing entries remain unchanged if no replacement is found within the search
budget (0.5 seconds per entry, 10 seconds total search). The report identifies
unchanged entries. Validation is repeated for export; a lightweight 10-second
fragment rechecks locks while connected. Downloaded files must still be uploaded
before the next tipoff; FanDuel is authoritative about actual lock eligibility.
Contests must permit late swap. Current app support is FanDuel nine-slot NBA.

Verification: 76 NBA tests passed, including started OUT preservation, open OUT
replacement, exact-tipoff clocks, invalid/missing clocks, new locked-player
rejection, timeout preservation and CSV entry/reference-cell preservation. A
small synthetic 20-entry case completed in 0.187 seconds locally; this is not a
production latency guarantee.
