# DraftDashboard attributes and experimental Simmah player score

## Explicit attribute meanings

The NBA ownership snapshot importer accepts optional DraftDashboard fields on a
complete matching site/date/team snapshot. Complete ownership imports retain raw
values and normalize eligible field targets to 900% on FD or 800% on DK. Partial pasted lineups are reference portfolios, not ownership
snapshots; their exposures must never become projected field ownership.

| Input | Stored meaning |
| --- | --- |
| PRO / Projected Points | Projected fantasy points for the selected site |
| MIN / Projected Minutes | Projected minutes, explicitly confirmed by the user for this DD input |
| USE | Usage percentage while on the floor |
| OWN | Projected main-slate field ownership percentage |
| DashRank | Provider rating from 0 to 100 |
| Opponent Rank | Opponent team defensive rank, integer 1–30 |
| Position Rank | Opponent defensive rank against position, integer 1–30 |
| FPPG | Historical fantasy points per game, separate from PRO |
| PPM / FPPM | Provider fantasy points per minute |
| VAL | Projected fantasy points per $1,000 salary |
| HIT | Provider probability of reaching 5x salary value |
| VS OPP | Provider player-versus-opponent statistic |
| Game Total / Team Implied Points | Separately labeled DD market context |

Invalid values and conflicting aliases reject the import without changing the
original pool. Explicit zero projections/minutes remain zero. Provider ratings,
usage and matchup ranks are retained as context, not applied as an extra boost
to projections. DD market context does not overwrite trusted market inputs.
Imported points/minutes keep their source labels through automatic news refresh;
fresh injury updates still apply and OUT players remain excluded.

DD attributes `.csv` files and copied `.txt` tables have a separate upload. CSVs
require Player, Team, Opponent, Salary, PRO, MIN, Site, Sport, Source and Slate Date;
site, NBA sport, DraftDashboard source and date must match. Optional DD fields use
the same typed mappings. Copied text accepts
the actual pasted-table layout, verifies the opposite-site salary-comparison
labels, requires explicit confirmation of the selected date (the text is undated),
and checks player/team identity, salary and opponent against the salary slate.
Every currently eligible player must be covered. Valid uploaded OWN takes precedence
over provider ownership, including on the attributes upload. Original display
strings remain available. `<1%` uses 0.5% as a labeled interval-midpoint estimate;
`...`/blank is unreported and uses the existing selected ownership source only for
that player, with an explicit warning and a list of estimated players. Unknown
fallback values reject application. Tables with no exact eligible ownership
values retain the existing source with a warning. Explicit 0% stays zero.

The field receives proportional targets totaling 900% (FD) or 800% (DK); this is
an estimate, not a new provider forecast. Reported values remain unchanged.
Raw totals over 950% (FD) or 850% (DK) trigger warnings. Totals below half the
required roster total, invalid values, or normalization above 100% for any player
reject the import. Complete dedicated ownership snapshots use the same field
normalization. Incomplete dedicated snapshots retain the existing small-residual
policy and cannot be rescued by arbitrary scaling. Removing over 10% of the
original eligible ownership mass disables proportional target fitting and uses
the existing relative-popularity fallback.
Last-three games/minutes/usage are retained separately. A changed text snapshot
invalidates saved-build inputs. It does not bypass injury or manual exclusions.
Copied-table/attributes uploads retain DD projected MIN as its own labeled field
by default and preserve existing simulation minutes. The explicit "Use DD projected
MIN for simulations" checkbox enables replacement, with existing rotation-budget
checks still enforced. The supplied snapshots contain team totals from 216 to 291
minutes, so silently replacing or normalizing all rotations would be inappropriate.

## Simmah player score v1

This is an **unvalidated display heuristic**, not a probability, trained model,
ownership estimate, or selector objective. Scores are relative to active players
on the same saved site/slate; do not compare DK scores directly to FD scores.

From independent evaluation fantasy-point draws, compute each player's mean,
P90, P99 and 5x hit frequency. Rank active players by mean, P90 and P90 per $1,000
salary. Convert each average rank to 0–100 with `(rank - 1) / (n - 1)`; a singleton
is 50. The score is 40% mean rank + 35% P90 rank + 25% P90 salary-value rank,
rounded to one decimal. Inactive players have no score. Weights are provisional.

No new random draws or changes to fantasy outcomes, candidate generation,
portfolio selection, exposure caps, timeout handling or saved-lineup recovery
are introduced. Provider ranks and ownership are visible context, not directly
weighted again. The roster tab exposes the score after a rebuild and warns when
the saved build is stale. Diagnostic exports include scores and the definition.
Experimental full-game mechanics in PR #77 remain offline.


## Provider audit evidence

New NBA diagnostic bundles include `inputs/provider/rotowire.json`, also retained
in player-pool attributes. It contains the selected RotoWire slate ID and slate
object, site/date/scope, parsed raw JSON payloads keyed by requested endpoint,
request start/completion timestamps in UTC, optional endpoint errors, cache fetch
time, and refresh failure metadata. These are fetch times, not claims about the
provider's ownership-update time. Cached data retains its original fetch times.
The exact-slate and broader-slate minutes-only paths are distinguished; the latter
never supplies ownership. Request headers, credentials and environment are not
captured. Older builds explicitly lack this evidence and cannot be reconstructed.
