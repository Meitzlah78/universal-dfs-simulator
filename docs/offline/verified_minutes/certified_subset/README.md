# Certified subset result and prospective shadow contract

## Exact subset

| Coverage | Count |
| --- | ---: |
| Verified regular-season archive games | 159 |
| Archive team-games | 318 |
| Archive games with saved build inputs | 31 |
| Archive games without saved build inputs | 128 |
| Distinct archive team-games with saved inputs | 62 |
| Archive team snapshot versions (DK/FD counted separately) | 122 |
| Archive snapshots with complete historical role priors | 13 |
| All saved team snapshot versions, including six additional Nov 13 games | 144 |
| All saved snapshots with complete historical role priors | 20 |
| Saved snapshots with complete certified capture-time status | 0 |
| Certified team snapshot versions / certified archive team-games | 0 / 0 |

The 1,891 supported player role priors do not form a certified team-game pool. Full team/game membership and status verification are independent prerequisites. Every roster member remains in the gate denominator, including missing priors or unknown statuses. No subset can be created by removing unsupported players. The historical certified subset is empty, so there is no residual comparison or genuine allocation-conflict rate. Missing-input failures are not allocation conflicts.

`team_snapshot_gate.csv` contains one row per saved team snapshot. `archive_coverage.csv` retains all 159 archive games, including those with no saved inputs. No postgame participant list was substituted for an eligible pregame pool.

## Cold-start rule

For the current prototype, unsupported role history produces `uncertified_pool` with **no numeric minutes fill**. It does not create a zero-minute observation, silently drop a player, or substitute an unvalidated contract/depth-chart estimate. A contract/depth-chart fallback would require dated pregame evidence plus separately learned and validated tier priors before it can become a certified numeric input. Live forecasts are untouched by an experimental shadow input failure.

## Shadow hook implemented, not activated

`simmah_nba_shadow_minutes_offline.write_shadow_capture` provides append-only local capture records with UUID identities, runtime capture timestamps, source-observation receipts, content hashes and raw payload files. A caller cannot backdate a newly written capture. The input gate requires a verified full team/game membership manifest, independently verified eligibility semantics, a verifier reference, all roster identities, source observations no later than capture and supported pre-capture role priors for every eligible player. Ineligible players need no role prior; unknown status blocks the pool instead of removing the player.

A source receipt demonstrates that bytes were observed; it does **not** certify source semantics or complete roster coverage. An approved parser/source profile must provide that evidence. Source payload fetch boundaries must supply truthful timezone-aware observation times. Recorded hashes detect content changes; they do not authenticate the upstream publisher.

Schema fields: `schema_version`, `mode=shadow`, `capture_id`, `captured_at`, `game_id`, `team`, `scheduled_tipoff`, `receipts[]`, `pool_evidence`, `players[]`, and `input_gate`. Each player carries its eligibility/source ID and independent role-prior provenance. Pool evidence carries the full membership manifest and source-verification reference. The caller may also preserve frozen baseline predictions, candidate model/version, bound inputs and experimental outputs in the record; the hook never writes to live lineup state.

Certification for completed-game evaluation additionally needs actual tipoff verification. A capture may pass the pregame input checks but remain pending actual tipoff; an earlier-than-scheduled actual start invalidates a late capture. Allocation infeasibility is a separate later stage under the frozen candidate and must be recorded separately from input-blocked cases.

The hook is **not imported into hosted Simmah**, no collector/service is running and no new live snapshots have been claimed. This work supplies tested gates and storage plumbing; connecting an approved live source/parser and incoming build inputs remains required to start prospective collection. PR #77 and production are unchanged.

## Validation

112 targeted tests pass. Added cases cover one unknown status blocking the team, missing priors remaining in the denominator, complete-roster manifest matching, scheduled versus actual tipoff, late source receipts, no numeric cold-start fill, immutable writes and prevention of backdating. The one historical injury-heavy team-game is not a tuning target.
