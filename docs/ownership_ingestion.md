# Offline predictive role-ownership ingestion

`simmah_ownership_ingest.ingest_ownership` and `scripts/ingest_role_ownership.py` accept canonical ID-only CSV/JSON data and endpoint provenance. They do not fetch providers, change the live app, infer names, split combined ownership, fill unknowns, normalize totals, relax targets, or execute a solver. A provider-specific adapter is still required if source columns differ.

## Canonical record contract

Every row has exactly `site_id`, `slate_id`, `game_set_id`, `player_id`, `target_ownership_cpt`, `target_ownership_flex`. `target_ownership_cpt` denotes the special role (CPT for DK, MVP for FD); a separate output label makes this explicit. `site_id` is exactly `dk` or `fd`; IDs are exact nonempty strings, preserving leading zeros. JSON input is an array of objects. CSV requires a unique canonical header. Extra or combined-only columns fail instead of being interpreted ambiguously.

Declared global `unit` is exactly `probability` or `percent`. Source units and bytes stay unchanged in the archive. Normalized probabilities are separate derived values, with the conversion factor recorded. Probability input is bounded [0,1], percent [0,100]. No guessing based on magnitudes. JSON null and blank CSV cells mean unknown; missing site-player records become unknown too. Zero means explicitly predicted zero. Malformed numeric text, boolean values, NaN/Infinity tokens and invalid IDs fail rather than being silently coerced to missingness. An external adapter can map a provider's documented null token explicitly before canonical ingestion, but must preserve the original bytes and transformation provenance.

Site context JSON supplies `site_id`, `slate_id`, `game_set_id`, `expected_game_set` (unique exact game IDs), ordered `player_ids` from the complete site salary slate, and optional `candidate_excluded_ids`. All feed IDs must belong to the site list; foreign IDs are fatal even if their target is zero. Duplicate feed IDs are fatal. Site-player rows omitted by the forecast remain present as null targets. Every site ID stays in opponent support independently of the candidate projection filter; positive targets for excluded candidates are logged as retained-in-support exceptions. This is an input-ID coverage check, not an enumeration coverage claim.

## Endpoint metadata

The metadata object has exactly these fields; nullable timestamps must be present explicitly as null when unknown:

- `site_id`, `slate_id`, `game_set_id`, `observed_game_set`.
- `feed_name`, `source_url_or_id`, `source_slate_key`, `matching_logic_version`.
- `unit`: `probability` or `percent`.
- `target_kind`: `projected` or `actual`.
- `request_status`: `success`, `error`, or `unknown`.
- `request_started_utc`, `request_completed_utc`.
- `last_successful_received_utc`: when the values actually used were last obtained, including retained cached data after a failed refresh.
- `provider_updated_utc`: only when supplied by the provider; otherwise null.
- `lock_time_utc`: recorded lock, or null if unknown.

All non-null timestamps require an explicit UTC offset. Ingestion time is recorded independently when this utility runs; it is never substituted for any retrieval/provider timestamp. Retrieval age, provider age, and minutes before lock at actual receipt are separate diagnostics. Request completion does not freshen old retained ownership. Future timestamp anomalies block the predictive gate. Unknown provider update time remains unknown. There is no invented staleness threshold or claim of authenticated provider provenance; metadata are caller-supplied evidence.

An optional expected raw SHA-256 must match exactly. Raw feed bytes, raw metadata and raw site context are archived, along with derived normalized records. Provenance belongs to this ownership endpoint, not to some successful projection or minutes endpoint.

## Pre-calibration gates

Known targets are checked against probability bounds, per-player special+FLEX exclusion, special sum 1, and FLEX sum 5. The configured numerical tolerance is recorded (default 1e-6 probability). No rescaling occurs. With missing values, known sums and unknown counts are reported, but the incomplete sum residual is null rather than pretending to be a complete forecast. Inputs with skewed totals remain inspectable but cannot advance. Current dual backends require complete targets; null is never reinterpreted as zero or as an unconstrained solver feature.

`require_calibratable` blocks incomplete or inconsistent targets. Its predictive mode also requires projected classification, recorded prelock receipt, known lock and no future timestamp anomaly. This is an input gate, not a prediction-accuracy guarantee. A stale retained feed can have recorded prelock evidence; use the reported age and an explicit research freshness policy. No automatic freshness cutoff is imposed here.

Only eligible projected inputs get `calibration_targets.json`, compatible with `scripts/calibrate_single_support.py`. That artifact still needs a compatible support and a separate feasibility check. The import function returns aligned vectors for explicit integration by an offline caller.

**Full-universe feasibility limitation:** the earlier actual-ownership oracle obtained a HiGHS witness on observed rosters already known to be contained in the full support. That is a valid feasibility certificate for those actual targets. It is not a general predictive feasibility oracle over 237 million implicit lineups. A future restricted-support predictive LP cannot certify full-universe infeasibility without complete support or a valid pricing/separation method. Unknown feasibility, infeasibility and nonconvergence must remain distinct. A generic HiGHS infeasibility status also does not identify a unique causal set of player violations. No such attribution is fabricated by ingestion.

## Immutable archive command

```sh
python scripts/ingest_role_ownership.py \
  --feed canonical_forecast.csv --format csv \
  --metadata ownership_endpoint.json --slate complete_site_slate.json \
  --output new_ownership_ingestion.zip
```

Output is built on the destination filesystem and published using an exclusive atomic hard link. An existing output is never overwritten. The ZIP retains the raw inputs, normalized payload when parseable, report, status and SHA-256 manifest excluding itself. Malformed input produces a failed archive and nonzero exit; incomplete targets produce an inspectable blocked archive. Missing input files cannot be archived and cause an immediate error. This is an input audit artifact, not a complete staged build snapshot or a production export.

Exit codes: 0 = predictive input gate passed, 1 = ingestion failed, 2 = parsed but blocked. Every outcome records feasibility as `not_run` because this command deliberately does not execute LP or dual optimization.

## Current source availability

The saved Library ownership snapshots inspected during this work are DraftKings Classic files with no separate special/FLEX role targets or site player IDs. One contains projected combined ownership and a source update time; the other contains only player/salary columns. They are not eligible single-game predictive inputs. The archived WAS–SF pilot has 29 model-generated player forecasts and is not an independent provider feed covering the complete site slate. Actual contest standings and point-projection tables cannot substitute for a pre-lock role-ownership forecast.

No eligible independent third-party role forecast for WAS–SF or GB–DAL was located in the sources searched. Therefore no real-feed invariant pass/block or predictive HiGHS result has been measured. Tests use explicitly synthetic fixtures and do not establish forecast quality. Live generation/ranking remains unchanged.
