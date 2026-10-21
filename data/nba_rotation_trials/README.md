# NBA empirical rotation ingestion — offline pilot

The importer reads the CDN NBA event CSV archives from
https://github.com/shufinskiy/nba_data (Apache-2.0 repository).
The sample source URL, immutable upstream commit and downloaded archive SHA256
are recorded in sample-audit.json. Original data is derived from NBA event feeds.

The archive named cdnnba_po_2025 contains games played in 2026: filenames identify
season start years, not necessarily calendar years. Cutoffs use actual event
UTC dates, exclusively before the supplied date. This sample uses 2026-10-21.

Run:

    python scripts/audit_nba_rotations.py path/to/cdnnba_po_2025.tar.xz --before 2026-10-21 --output audit.json

No network request or historical reconstruction runs in the Streamlit build path.
The CLI writes full reconstructed intervals, joint substitution transitions,
co-occurrence seconds, sample counts and empirical replacement frequencies.
The committed sample retains counts, the top 20 pattern/pair examples and rejection reasons.

Initial results: 60 source games, 45 structurally accepted, 15 rejected;
1,946 joint team substitution transitions. Five players must be on each floor;
every complete regulation game conserves 240 player-minutes per team and adds
25 per overtime. Initial floors are inferred from first substitution directions
and on-court action evidence. Ambiguous starters, nonmonotonic clocks,
unbalanced substitutions and impossible floor membership reject the whole game.
Several substitutions at the same clock form one transition: no arbitrary
one-to-one replacement assignments are created. Intervals are split at event
clocks, so interval count is not a count of unique five-player units.

These are CANDIDATE rotations, not verified training labels. Conservation alone
cannot prove correct player attribution. Still required: reconcile player minutes
with independent official box scores; inspect same-clock event ordering and
period boundaries; audit score/foul context; cover regular-season rotations,
trades and coaching changes. Whole-game absences differ from routine substitutions.
Raw replacement frequencies are not causal injury effects. Co-occurrence is not
an automatic exclusion rule. No offensive efficiency or net-rating penalty is
inferred from these counts.

No live simulation, projection, exposure or late-swap parameter is changed.
Use a time-separated validation set before activating learned rotation rates.

## Player-minute reconciliation and trigger evaluator

Run the saved-box-score audit offline:

    python scripts/reconcile_nba_rotations.py audit.json path/to/boxscores --output reconciled.json

Files must be named boxscore_0042500101.json (ten-digit official game ID).
The validator requires final NBA CDN game status, matching official game/team/player
IDs, complete regulation/overtime team minutes and bounded player-level residuals.
Absent files remain pending. Unknown final player rows are not converted to zeros.
Only explicitly recorded DNPs may supply zero minutes without a minutes field.
Failed player attribution quarantines the game. The CLI records input hashes.

On October 21, the pinned archive was reproduced: 60 games, 45 structural accepts.
An official NBA CDN box-score request returned HTTP 403; real player-minute
reconciliation remains pending. Unit fixtures are not historical validation.

simmah_nba_rotation_triggers.py provides an offline, configurable priority table.
Rows specify outgoing/incoming player IDs and optional foul, period, margin and
remaining-game-clock thresholds. It uses dead-ball opportunities, rule cooldowns
and legal five-player floors. Missing foul counts do not fire foul rules. A base
rotation must be supplied explicitly; this does not infer a coach's schedule.
The example thresholds in tests are synthetic, not fitted coaching tendencies.
No hardcoded 90-second cycle, empirical substitution model or efficiency penalty
has been activated. Staggered base schedules still require validation against
observed stints, including rotation context and substitution opportunities.

## Official public-page box-score audit — October 21, 2026

The direct NBA CDN endpoint returned HTTP 403, but public NBA game pages
exposed final player/team IDs and box-score minutes in __NEXT_DATA__.
The optional offline downloader reads those public game pages. It does not
run in Streamlit or change projections:

    python scripts/reconcile_nba_rotations.py audit.json boxscores --fetch-official-pages --output reconciled.json

All 45 structurally accepted games now reconcile at player level within the
explicit two-second tolerance. The other 15 of the 60 source games remain
structurally rejected; they are not silently repaired or counted as validated.
See official-boxscore-audit.json for per-game final-source URLs, normalized
box-score hashes and residuals. Downloaded normalized box scores are reusable
CLI inputs; raw source pages and normalized payloads are not committed.
Official page MM:SS minutes are converted to ISO durations; displayed :60
rounding carries into the next minute. Explicit DNP and DND records supply
verified zero minutes; unexplained blanks remain unknown.

This supersedes the earlier pending box-score status for these 45 games only.
It validates historical player-minute reconstruction, not all event ordering,
foul/score trigger thresholds, injury redistribution, a learned coaching model,
pregame projection accuracy, profitable lineups or regular-season coverage.
No live rotation behavior is enabled.
