# NBA page responsiveness audit

Changing a minutes setting or pressing refresh enters the NBA import route before the build controls render. The projection source previously waited synchronously for up to 12 seconds. The optional fallback game-context source could add a separate synchronous network wait. Both are now background IO, isolated by session, platform, date and salary-pool identity.

The page returns with the last successful same-slate provider data while refresh is pending. A small fragment polls only its active requests and triggers one full rerun when a result is ready or times out. Completed requests are consumed once. Obsolete requests cannot trigger repeated app reruns, and old-slate results cannot overwrite a newly selected slate. Only the app thread updates session state; workers receive a detached player-pool snapshot. In-flight requests are deduplicated, provider concurrency is capped at four, and pending bookkeeping is bounded. Successes retain the existing 15-minute refresh interval; failures retain the 60-second retry pause. Explicit refresh bypasses freshness/backoff, while an already running request is reused.

The fallback game-context source uses the same mechanism and refresh interval. Source errors preserve last successful matching data. Initial loads without successful data continue to show incomplete-input validation until the first refresh finishes; no projections, minutes or ownership are invented. Starting-lineup refresh acknowledgement waits for completed projection IO instead of treating a pending old snapshot as newly refreshed.

## Flow audit

| Stage | Finding / verification |
|---|---|
| Entries and slate identity | Existing import and workflow regressions validate preserved entries, clocks and site identities. |
| Projections and market fallback | Removed synchronous network waits; tested success, timeout, failure retention, retry, request deduplication and session/slate isolation. |
| Settings and page updates | Fragment polls only active jobs; no permanent full-page refresh loop from obsolete completed jobs. |
| Simulation preparation and build | Expensive simulation remains behind BUILD; existing deterministic scenario cache and bounded CPU/memory-aware process workers remain in place. No numerical engine changes. |
| Lineup selection and display | Existing unchanged-selection cache and opt-in candidate/engine reports are retained; UI and cash-check regressions exercised. |
| Exports and late swap | Existing legality, current-status, reserved-entry and non-roster preservation checks exercised. |
| Save, restore and slate switching | Existing asynchronous backup/export jobs and detached checkpoints exercised with navigation/restore tests. |

One existing navigation assertion still expected the removed `Build Settings` heading. It now checks the current `Build lineups` heading in the build controls while preserving the other routing assertions.

## Local evidence

- Loading/build/UI/export regression group: 74 passed, six subtests passed; full-scale opt-in initially skipped.
- Navigation/save/restore/parallel group: 32 passed, two subtests passed.
- Final background refresh suite: eight passed, including filtering obsolete job completions. Six of these overlap the first group.
- Explicit full-size build/export: passed (10,000 scenarios per phase, 5,000 candidates, 10,000 requested field-support rosters, 20,000 contest places).
- Controlled 250 ms provider-wait benchmark: old page path 250.62 ms; new page path 0.68 ms. This measures removal of the blocking call, not live-host latency or the duration of an entire simulation.

The frozen `nba-margin-blind-v3` candidate, its grader and holdout registry are unchanged. These fixes target the app route on current main. Deployment/runtime confirmation remains necessary; local verification does not prove the live Streamlit app has updated.
