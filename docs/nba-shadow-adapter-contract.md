# Canonical-ID roster, role and bound adapters (draft)

## Status and exit criterion

The single team-game **synthetic mechanics test** passes through the real freeze, raw persistence and subprocess sidecar. Eight eligible synthetic players receive 30 minutes each (240 total). With one explicitly ineligible player, learned upper bounds sum to 210 and the sidecar records an exact 30-minute deficit with no relaxation.

This is **not** the real pre-tipoff milestone. Only synthetic fixture source profiles are approved in code. No live NBA/RotoWire/ESPN feed has been promoted to a complete, game-specific eligibility contract; no real capture has qualified. All synthetic results have `qualified_for_evaluation=false`. PR #81 remains draft, default-off and undeployed. Production and PR #77 remain unchanged.

## Interfaces

`source_pool.attrs['nba_shadow_adapter_requests']` optionally provides a list of team-game requests at the build boundary. Freeze serializes and detaches that list under the capture ID before any background work. Each request supplies:

| Field | Contract |
| --- | --- |
| `game_id` | NBA canonical game ID, string of 10 ASCII digits; leading zeros retained |
| `team_id` | NBA canonical team ID, string of 10 ASCII digits |
| `roster_sha256` | Digest of an included raw roster response |
| `history_sha256` | Digest of an included canonical regulation-history response |

Player IDs are canonical NBA person-ID digit strings. Display names are ignored. No ESPN/DFS/transient ID is converted by name; those sources need a separately verified stable-ID crosswalk before supplying this contract. Identifier syntax alone does not prove identity: the approved source profile must establish canonical identity semantics. Caller-supplied approval booleans cannot register a source profile.

Approved profiles currently consist only of `fixture://nba-roster/v1` and `fixture://nba-history/v1`. These always yield synthetic provenance. A real profile needs a reviewed source contract, source-to-player lineage, full-roster membership verification and exact game-status semantics. It must be approved before capture: adapter/worker code hashes are frozen and checked again by the child; a changed or absent model hash blocks execution.

## Roster evidence payload

The canonical JSON contains `kind=team_game_roster_v1`, `id_namespace=nba`, `game_id`, `team_id`, `season_id`, timezone-aware `scheduled_tipoff`, `complete_roster=true`, a unique `member_player_ids` manifest and exactly matching `players` records. Every record carries matching `game_id`/`team_id`, `player_id`, explicit `eligibility` (`eligible` or `ineligible`) and timezone-aware `status_observed_at`. Eligible players also need `role_context` (`normal` or `injury_promoted`) and pre-capture `role_context_observed_at`.

Receipt `observed_at < frozen_at < scheduled_tipoff` is mandatory. Each status/context observation must be no later than its receipt and strictly before capture. Equality at capture fails. Naive timestamps fail; no assumed timezone. Unknown status, missing mapping, incomplete manifest or duplicate identity blocks the entire team-game. Confirmed ineligible players remain in the roster evidence and output ID list; they need no numeric role prior.

Scheduled tipoff is not proof of actual tipoff. Every result remains pending actual-tipoff verification and post-game reconciliation; actuals may later invalidate a seemingly pre-scheduled-start capture.

## History evidence payload

The canonical JSON contains `kind=regulation_history_v1`, `id_namespace=nba`, and `records`. Each record carries stable game/team/person IDs, `season_id`, `season_type=regular`, aware `game_start_time`/`game_end_time`, `regulation_only=true`, numeric `minutes`, boolean `started`, explicit participation (`played` or `confirmed_dnp`), role context and its pregame observation time.

* Only the target season's regular-season records enter the model.
* `game_end_time < frozen_at` and `game_end_time <= receipt.observed_at` are enforced. Target-game records are excluded even if incorrectly labelled completed.
* Unknown participation/zero without confirmed DNP stays excluded and counted, not converted into a zero. Positive played minutes and confirmed-DNP zero must agree with their labels.
* Missing starter flags, unverified regulation minutes and unknown historical role contexts are excluded with counted reasons. Duplicate player/team/game observations block the input rather than doubling weight.
* Historical role-context observation must precede that historical game's start.

The source profile must validate these meanings; raw postgame attributes cannot simply be relabelled pregame context.

## Fixed experimental role and bound rules

Player role history is scoped to the same canonical person ID **and team ID**. At least three explicit earlier observations are needed; historical starter/reserve classification uses starter rate >=0.5 in the last five observations. No numeric cold-start prior is emitted for rookies, traded players without new-team history, or missing history.

For every training label, its role is derived from that player's earlier games ending before the label game's start. Current-role training uses only label outcomes completed before capture. Normal and injury-promoted context groups are separate: no normal-bound substitution on injury-heavy slates. Minimum support is 20 records across at least five distinct game IDs per role/context. These are fixed research guardrails, not tuned promotion thresholds.

The role prior is the earlier conditional league mean. Personal history is shrunk toward that prior using absolute calendar evidence mass (14-day half-life, prior strength 3). Learned 5th/95th percentile bounds and per-role standard deviation (floor 1) determine a bounded weighted projection to 240 regulation minutes. No universal 38-minute cap, fabricated replacement minutes or silent bound relaxation exists. These parameters remain experimental, not validated accuracy claims.

## Terminal states and reconciliation keys

Inputs are gated **before** allocation. Unsupported inputs produce `uncertified_pool` and a structured reason/detail record; they are not allocation conflicts. Qualified team inputs yield exactly one of:

* `forecasts`: one `predicted_minutes` record for every eligible canonical player, totaling 240 within numerical tolerance and within its learned bounds.
* `allocation_conflict`: no partial predictions; exact lower sum, upper sum, lower excess, upper minute deficit, physical deficit and eligible count, with `bounds_relaxed=false`.

Both qualified outcomes preserve all derived role priors/bounds in `frozen_player_parameters`, eligible/ineligible player IDs, canonical namespace, team/game IDs, scheduled tipoff, season, capture ID/time, source digests, model-version provenance and historical cutoff maxima. These are linked to the immutable capture SHA-256. The role/bound values are deterministically derived in the sidecar from frozen history and pinned code; no later observations enter them. The output JSON is exclusive-create. Duplicate team requests are explicitly unsupported, not evaluated twice.

For a multi-team bundle, the wrapper stores `team_game_results`; each team has its own terminal status. Wrapper success does not certify all teams. Actual-tipoff/actual-minutes attachment is still unimplemented. A future reconciler must check stable ID namespace, identity, actual tipoff and non-synthetic provenance before any evaluation inclusion. No synthetic forecast is eligible for residual metrics, readiness rates or the real-capture exit gate.

## Failure reason vocabulary

Runtime reasons include: `INVALID_OR_NAIVE_TIMESTAMP`, `INVALID_STABLE_ID`, `UNAPPROVED_SOURCE_PROFILE`, `SOURCE_NOT_OBSERVED_BEFORE_CAPTURE`, `SOURCE_CONTRACT_OR_NAMESPACE_MISMATCH`, `GAME_OR_TEAM_ID_MISMATCH`, `CAPTURE_NOT_BEFORE_SCHEDULED_TIPOFF`, `INCOMPLETE_ROSTER_MEMBERSHIP`, `INVALID_ROSTER_MANIFEST`, `ROSTER_MANIFEST_MISMATCH`, `PLAYER_TEAM_OR_GAME_MISMATCH`, `STATUS_NOT_OBSERVED_BEFORE_CAPTURE`, `UNRESOLVED_ELIGIBILITY`, `UNRESOLVED_ROLE_CONTEXT`, `ROLE_CONTEXT_NOT_OBSERVED_BEFORE_CAPTURE`, `COLD_START_ROLE_HISTORY`, `INSUFFICIENT_CONTEXT_TRAINING`, `DUPLICATE_HISTORY_OBSERVATION`, `INVALID_HISTORICAL_GAME_TIMES`, `CONTRADICTORY_PARTICIPATION`, `INVALID_NUMERIC_EVIDENCE`, `MISSING_SEASON_ID`, `MODEL_VERSION_NOT_FROZEN`, `AMBIGUOUS_RECEIPT_HASH`, `DUPLICATE_TEAM_GAME_REQUEST`, `MISSING_OR_INVALID_SOURCE_PAYLOAD`, `MALFORMED_ADAPTER_REQUEST_LIST`, `MALFORMED_ADAPTER_REQUEST`, `MALFORMED_ADAPTER_INPUT` and `ALLOCATION_NUMERICAL_FAILURE`.

These are structured codes, not automatic fallback decisions. Receipt tampering is an integrity failure: the worker produces no forecasts and the capture runner records worker-failure telemetry.

## Test evidence

The complete 101-test integration/regression run passed (NBA source parsing, Streamlit build/export and saved-lineup recovery, the real small-scale build contract, plus the adapter path). After adding one malformed-roster test and final metadata/type guards, all 32 adapter/runner checks passed again. Cases cover exact timestamp equality rejection, naive times, future/target-game outcome invariance, canonical namespace/ID failures, duplicate/omitted members, unknown participation, trade/rookie cold starts, injury-context support, model-hash mismatch, raw tampering and immutable saved live state. These counts are overlapping test runs, not independent validation observations.
