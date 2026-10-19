# Simulation preparation backend

`simmah_simulation_store.py` separates outcome preparation from candidate search
and contest evaluation. It imports no Streamlit code and makes no network calls.
The Streamlit scorer delegates to the same pure `simmah_nfl_scoring.py` function.

## API

```python
prepared = prepare_simulations(
    confirmed_player_pool, frozen_historical_roles, "DraftKings", cache_root,
    weather_by_team=frozen_weather,
)
# Default: 10,000 independent evaluation outcomes AND 10,000 construction outcomes.
key = prepared["metadata"]["key"]

# BUILD can later load the two matrices without a fit or simulation call:
prepared = load_prepared(cache_root, key)
candidates = build_candidates(pool, prepared["construction"], roster, target=5000)
# Rank candidates using prepared["evaluation"], never the construction sample.
```

Only reuse the preparation key for the corresponding frozen slate inputs.
Salary, ownership, entry counts, sim diversity and lineup rules belong to later
stages; changing those does not change player outcomes. Changing player names,
row order, projections, teams, opponents, positions, historical roles, scoring
site, weather, correlation settings, sample counts, seeds or relevant model code
invalidates the appropriate cache entry.

Fitted event parameters have a separate cache. Changing seeds/counts/weather
reuses the fit when its neutral-weather fitting inputs remain unchanged.
Evaluation and construction use distinct explicit seeds; equal seeds are rejected.
No outcome resampling, scaling or altered scoring is used to manufacture speed.

## Offline command

```bash
python simmah_simulation_store.py \
  --players confirmed-players.csv \
  --roles historical-roles.json \
  --weather weather.json \
  --starters confirmed-starters.json \
  --platform DraftKings \
  --cache-root /tmp/simmah-outcomes \
  --output preparation-metadata.json
```

Both role and weather JSON files are required. An empty mapping explicitly chooses
model defaults; it does not reconstruct missing pregame evidence. Starter choices
are required when the supplied projections contain multiple QBs for one team.
No completed-contest result can supply or automatically choose a starter.

## Integrity and storage

- Content-addressed keys include model source fingerprints.
- SHA256 checks protect stored matrices and reports from accidental corruption.
- NumPy loads disable pickle. Matrices must have correct names, shapes and finite values.
- Atomic writes publish the manifest last; incomplete writes are never accepted.
- OS process locks prevent simultaneous workers preparing the same key.
- Process locking currently targets Linux, including the Streamlit deployment host.
- Cache survives application-process restarts only while its filesystem remains.
  Ephemeral host replacement can erase it. Durable external storage and retention
  policy are still needed before promising reuse across every deployment/reboot.

## Current integration boundary

The pure scoring extraction is connected to the app. Persistent preparation and
load-only APIs are tested offline; the live SIM/BUILD workflow has NOT yet been
switched to use them. Its existing session workflow remains until that integration
is tested. This checkpoint alone does not speed the live app.

The next integration must associate a frozen input key with the slate, prepare both
matrices as a separate stage, and make BUILD load that key. It must reject a missing
or stale preparation rather than silently performing another expensive simulation.
