# App idle-work audit — November 18, 2026

Scope: recurring Streamlit fragments, browser timers, export/save completion,
calibration status, NBA live lineups and late swap, provider IO entry points,
UI player views and diagnostic serialization. Static review plus controlled
regressions; this is not a live-host CPU profile or a guarantee that every
possible bottleneck has been eliminated.

| Path | Finding | Action |
| --- | --- | --- |
| Saved export history | Every download installed an unconditional one-second history timer, including empty/static histories. | Put download/history in the same isolated fragment. Arm a one-shot browser poll only for matching pending export jobs. Publish completion with one app refresh; idle history has no poll component. |
| Shared backup monitor | Export jobs can finish here before their own history controller sees completion. | Refresh the app once after publishing completed exports, keeping history and saved downloads current. The prior busy-only backup polling remains intact. |
| Calibration status | Its five-second fragment remained scheduled after the initial job finished. | Detect that no queued/running/paused job remains, refresh once to remove the timer and expose results. A new job re-enables monitoring. |
| Automatic NBA late swap | Downloaded projections before discovering the entire slate was locked. | Check clocks first. Fully locked slates install no monitor or fetch; a monitor reaching the last tipoff refreshes once to remove itself. Partial slates still refresh. |
| Repeated NBA lock checks | Team grouping and row reads copied raw provider evidence. | Read metadata-free values while preserving original salary clocks, timezone validation and conflicting-clock rejection. |
| NBA auto-swap and player display | Row iteration and display-only table construction propagated provider metadata. | Use metadata-free temporary views. Preserve original projections, names, IDs, uploaded inputs and provider evidence. |
| Diagnostic JSON rows | DataFrame record conversion propagated raw evidence into temporary Series. | Convert rows through metadata-free views; retain original attrs and raw provider payload in the diagnostic bundle. |
| Calibration table | Deprecated width argument emitted warnings. | Use width='stretch'. |

## Retained work and limits

- NBA starting-lineup fragment: 60 seconds, background source IO and cheap value
  views (PR #112); retain automatic news updates. A pending fetch can become
  visible on a following check. Manual Refresh remains available.
- NFL projection/injury check: 15 minutes; targeted sources are cached, failed
  lookups are cached, and verified injury changes can request an app rerun.
- NBA provider completion: one-second polling only while sources are pending,
  followed by an app rerun to apply ready or timed-out results. No pending
  sources means this monitor is not installed.
- Manual late-swap export: five-second lock revalidation retained to avoid
  showing CSVs that move newly started players. Underlying clock reads are now
  cheaper. Rendering/export generation is still a possible follow-up profile.
- Automatic late swap: retain its explicitly enabled 60-second news check while
  games remain open. This patch does not submit entries or change solver rules.
- Archive transfers, recovery acknowledgements and storage probe timeout/lag
  timers are purpose-bound; do not remove durability or failure detection.
- Engine preparation, solver work, first-time imports, network outages, workspace
  recovery and host CPU throttling can still delay a page. No fresh live build
  was run during this audit; don't equate local tests with live responsiveness.

## Verification

Regression coverage exercises first-click export/history wiring, completion
refresh without another click, absence of an idle history poll, browser timer
termination/rearming, calibration completion/restart, fully and partially locked
slates, and metadata-free clock/display reads. Existing NBA build/export,
workspace recovery, export provenance and archive tests remain required.

Simulation distributions, ownership normalization, ranking/exposure settings,
lineup legality, game-lock constraints and production model parameters were not
changed.
