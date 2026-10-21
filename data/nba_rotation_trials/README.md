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
