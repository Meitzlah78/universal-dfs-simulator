# Opt-in NBA build capture — draft integration

This branch starts from production main and does not include PR #77 or research-model changes. Nothing is enabled by default. No merge, deployment or live capture is claimed.

## Implemented boundary

Existing RotoWire NBA projection/player/ownership requests, RotoWire lineup refreshes, official NBA dated lineup downloads and DFF projection responses retain original response bytes before parsing when `SIMMAH_NBA_SHADOW_CAPTURE=1`. No network requests are added. The observation time and SHA-256 are captured at response-read completion. Disabled mode keeps ordinary parsing and stores no receipts.

A process-local receipt cache retains at most 64 latest URLs and 16 MiB. Over-limit sources and capture failures are counted. It is an observed-source cache, **not a certified per-player transformation lineage**. Cache hits after process restarts may have no raw receipt; cached responses are not re-fetched or fabricated. Recovered rosterStatus values are not automatically certified. Only the named existing ingestion paths are hooked; other feeds and uploads are not claimed as raw-source-covered.

At BUILD NBA LINEUPS, before run_pipeline draws scenarios, immutable JSON freezes the pre-workspace-transform DFS pool, prepared pool, provider baseline points/minutes, settings/markets/payouts/ownership, model rates/identity/reconciliation and relevant source-code hashes. Actual freeze time and a UUID capture_id are bound to available receipts. The pool is a DFS salary pool, **not a certified complete NBA roster**. The baseline role_priors/bounds slots stay null; an optional frozen canonical adapter request can now derive role priors/bounds in the sidecar from approved frozen evidence. Only synthetic source profiles are currently approved; ordinary production sources remain unsupported. The original upstream bytes remain separate hash-addressed compressed artifacts; no synthetic raw response is created from a transformed pool.

A bounded two-job queue and one I/O worker persist snapshots and raw bytes. A separate Python sidecar verifies receipt hashes and writes structured results. Without approved canonical adapter inputs it records `uncertified_pool`; approved synthetic fixtures now exercise the experimental minutes allocator, yielding forecasts or quantified bound conflicts. These synthetic results are never evaluation-qualified. The sidecar does not import PR #77 or mutate Streamlit state/live engines/RNGs/lineups. Child execution times out at 20 seconds. Queue-full, freeze/submit failures, persistence/worker failures and timeout counters are visible; background failures attempt a capture-linked failure JSON. Disk failures remain non-fatal even if the failure log itself cannot be written.

When a build succeeds, its result carries shadow_capture_id; the latest ID is separately visible in health. Export validation still precedes replacement of saved lineups. A failed build does not overwrite the last successful portfolio. No experimental failure changes the production build outcome.

## Storage and observability

Default local directory: data/nba_shadow (gitignored). An operator can override it with SIMMAH_NBA_SHADOW_DIRECTORY. Hash-addressed raw bytes are reused, captures/results are exclusive-create and append-only. A conservative 128 MiB pre-write quota stops new capture payloads without deleting existing files; small failure telemetry may still be recorded. These files are private runtime artifacts, never git assets. Durable cloud backup / restart recovery is not implemented by this module and must be verified before relying on retention.

Build UI includes a Shadow capture health expander: enabled state, observed-source count, attempted/queued/persisted counts, persisted-per-attempt ratio, uncertified-pool count and categorized failures. Pending jobs affect the ratio until settled. Counters are process-local, reset after restart and are not slate-level completeness estimates. Certified-pool count is explicitly zero until a qualified roster/role adapter is connected. The panel does not claim a complete eligibility percentage from receipt presence. Health/render failures cannot disable the live build.

## Activation and remaining work

Do not enable by default. After this draft is reviewed, an operator would deploy the branch and set SIMMAH_NBA_SHADOW_CAPTURE=1 before source fetching. A refresh through existing UI paths would then observe new responses; a build would freeze them. This document is not evidence of hosted activation.

Next PRs need (1) source-to-player lineage and source semantics/full-roster verification, independent point-in-time role/bound adapter, (2) verified actuals attachment by stable game/player IDs and actual-tipoff checks, (3) certified-only residual/conflict metrics plus durable storage and per-slate health. Capture success is not evaluation qualification. The sidecar now has a synthetic-tested canonical adapter/allocator path; it remains an input-blocker recorder for unapproved real sources and is not a validated forecaster. See nba-shadow-adapter-contract.md for the contract and remaining real-capture milestone.

Synchronous freezing/serialization is small but not free; no hosted latency guarantee is made. Source response copies are bounded and asynchronous I/O/child work is off the production simulation path.

## Validation

78 targeted tests passed across receipt capture/sidecar, NBA source parsing and reserve recovery, Streamlit build/export flows, saved-lineup recovery and a real 64-simulation / 500-candidate build-to-export contract. Streamlit 1.67.0 was installed in the research runtime to execute the UI checks; no dependency file was changed. A follow-up UI test forces both capture and health failures together and confirms live build completion plus preservation of the previous saved portfolio when export fails.
