# NBA ownership source investigation — 2026-10-20

RotoWire's public NBA optimizer JavaScript requests
`/daily/nba/api/rostership.php?slateID=...&rstSource=RotoWire` separately from
`players.php`. Simmah previously used the player-list `rostership` metadata as
relative popularity. The corrected loader reads the dedicated source only when
`access` is true and the source is RotoWire; denied/malformed ownership never
erases valid point projections or minutes. Player metadata remains available
for diagnostics but no longer drives opponent weights.

Fresh public endpoint probes returned access=true. FD slate 29793 summed to
1410.1% across its complete response and 998.2% across positive eligible players
matched to the uploaded pool; DK slate 29798's full response summed to 799.9%.
These are new fetches, not certified frozen inputs to the earlier exported run.
See `source-audit.json` for URLs and diagnostic results.

## Field policy

Use external ownership as marginal field targets only if every eligible player
has a finite 0–100 value and the eligible total is within 1% of the site's slot
budget (900% FD, 800% DK). Rescaling is limited to that rounding-sized tolerance,
is disclosed in the source label, and must not push anyone above 100%. Existing
legal-support field fitting still checks maximum marginal error.

If validation fails, build an explicitly labeled scenario-derived field with
equal weights across independently generated legal support rosters. Do not
multiply invalid/unknown RST across the roster. This is an estimated fallback,
not calibrated real contest ownership or a claim of better ROI. Current input
identity and provider caches are versioned so old builds are marked stale and
ownership is refreshed once after deployment. No fantasy projections, injuries,
minutes, salary limits or independent evaluation seeds are changed.

A diagnostic on the OLD exported support found weighted projection 287.41 and
equal-support projection 286.37. Thus equal weighting alone does not resolve the
large gap to the selected portfolio. Field strength, support generation and
model distributions still need calibration against real contest data. Do not
interpret this source correction as a validated fix for the reported 3134% ROI.
