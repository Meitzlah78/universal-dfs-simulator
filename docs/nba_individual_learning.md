# Individual-rate learning rollout

The existing approved historical learner replaces generic position priors only.
The new individual challenger is a separate approval path. Legacy fallback
approvals never authorize replacing provider individual rates.

## Comparison

New builds freeze incoming individual rates before learned updates, with a UTC
capture timestamp and each player's dated game start. Started games are omitted.
The snapshot is retained in player-pool attrs, therefore in saved calibration
bundles and saved workspaces. Refreshes recover original source rates before
reapplying a challenger; newly fetched provider rates replace those originals.

Import timestamped bundles into the nightly learner's repository checkout:

```
python scripts/import_nba_rate_snapshots.py saved_bundle.zip
```

Commit `data/nba_models/individual_rate_snapshots/` with the imported snapshots.
The overnight learner consumes that directory alongside the completed-game
archive. Old bundle export timestamps are not treated as provider capture times.

A player's candidate is fitted strictly before the earliest evaluation day.
Only games with that player's valid pregame source snapshot are compared.
At least four later player game dates are required: two selection and two
confirmation observations at minimum. Each stat must lower count MAE by at least
1% in BOTH periods, compared with the exact frozen individual source rate for
that game. Other stats retain the current provider rates. Player identities must
match unambiguously in training and evaluation. Actual minutes are used to
measure stat-rate errors; these are not minutes, fantasy-point or ROI forecasts.
Four games is a minimum evidence floor, not proof of reliable long-run gains.

The dated, checksum-verified individual model is applied in the shared build and
late-swap path. It reports `nba_individual_learning.matched_players` separately
from fallback learning. Provider point projections, minutes and ownership remain
unchanged. No snapshots or insufficient confirmation produces `pending`.

## Remaining integration before unattended rollout

The Streamlit workspace and nightly GitHub runner are different machines.
Snapshot capture in saved bundles does NOT automatically transfer those bundles
to the repository. This change includes explicit ingestion, but automatic private
snapshot transport still needs to be connected and tested before claiming an
unattended learning loop. Do not deploy this draft as a completed automatic fix.

The 217-game existing archive contains no frozen pregame individual-rate
snapshots. It correctly returns `pending`; no individual replacements have been
approved from it. Further future results and genuinely pregame snapshots are
required. Existing fallback models cannot be repurposed as individual approvals.
