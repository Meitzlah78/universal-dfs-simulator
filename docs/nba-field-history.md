# Completed NBA contests in the opponent field

The NBA build path now loads anonymous completed-contest habits before drawing
opponent copies. This is separate from the experimental exact C solver. Current
player projections, minutes, source ownership values and candidate construction
are unchanged. History reweights the existing legal opponent support; it cannot
recover lineups missing from that support.

## Imported evidence

DraftKings contest `197070607`, October 24, 2026, $0.25 entries, five games:

- 16,812 exported entries; all have zero time remaining.
- 20 user entries excluded by template entry ID.
- 80 blank lineup rows unavailable, never interpreted as empty/zero lineups.
- 16,712 usable opponents, 13,007 distinct physical rosters.
- Duplicate-entry fraction 22.17%; most repeated roster has 143 copies.

Every recorded lineup passes the existing Python roster validator against its
own historical salary template. Alternative flexible-slot assignments canonicalize
to one player set; actual duplicate entries retain their weight. The position
side table's `%Drafted`, actual scores and finishing ranks are not training data.
Only anonymous aggregate histograms, coverage counts and provenance hashes are
committed. The source ZIP and salary template are not published.

## Runtime selection and model

Compatible history is applied automatically through `run_pipeline` and the NBA UI:
same platform, same fee bucket ($0–1, >$1–10, >$10), same slate-size bucket (1–3,
4–7, 8+ games), at least 1,000 usable opponents, and a **strictly earlier slate
date**. Missing dates, same-day/future contests, FanDuel and incompatible buckets
do not use this DraftKings profile. The UI states when history applies; saved
build identity includes its content hash, so changed history requires a rebuild.

Features are salary left (0.5% of salary-cap bins, with a separate exact-cap bin),
maximum players from one team, and maximum players from one game. Smoothed
historical distributions are compared with the current popularity-weighted
support. Clipped density ratios produce an additive lineup log-prior with maximum
strength 0.5 and bounded odds. These conservative hyperparameters are assumptions,
not fitted performance claims. Projected-ownership mode still fits its original
targets with this prior; relative-popularity and fallback modes retain their
existing source values and labels. All modes preserve legal support and field size.

Duplicate statistics are recorded and replayable, but this version does not fit
duplicate rates separately. It does not learn specific player pairings, contest
entrant identities, a new ownership forecast, or a new projection/minutes model.
Future-contest improvement remains unverified; one training contest is insufficient.

## Add another completed DraftKings contest

Use its own entries/salary template, not today's salary file. `--expected-entries`
must be the exact full standings count. Unknown players, ambiguous names,
unfinished games, repeated entry IDs or absent user entries block import. Blank
non-user lineups are counted as unavailable. Existing output files cannot be
silently overwritten.

```sh
python scripts/import_nba_field_history.py \
  --standings contest-standings-197070607.zip --template 'DKEntries(5).csv' \
  --contest 197070607 --expected-entries 16812 \
  --output data/nba_field_history/dk-197070607.json
```

## Replay against actual opponents

Preserve `DOWNLOAD OPPONENT FIELD` before tipoff for the selected contest. Compare
that CSV with its final standings and matching historical salary file:

```sh
python scripts/replay_nba_opponent_field.py \
  --standings completed.zip --template entries.csv --contest CONTEST_ID \
  --expected-entries EXACT_COUNT --field saved-opponent-field.csv --output replay.json
```

The report gives ownership MAE, pair-inclusion MAE (percentage points), salary and
team/game distribution total variation, and duplicate-entry fractions. Use saved
baseline and history-enabled fields on independent later contests for an A/B
comparison. Rebuilding a forecast after games is not prospective validation.
No saved before-tip modeled field was provided for contest 197070607; no predictive
gain is claimed from its import. The separate RotoWire/Lineups prospective study
and its frozen snapshots are not used or changed here.

```sh
PYTHONPATH=tests:. python -m unittest test_nba_field_history -q
```
