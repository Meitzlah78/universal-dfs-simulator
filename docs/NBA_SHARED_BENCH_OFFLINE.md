# Shared bench-minute dependence experiment

This branch is offline research. No production module imports the experimental
sampler. Live settings, selector policy and PR #77 are unchanged.

The control reproduces production `draw_wider_minutes` exactly. The treatment
retains its amplitudes, reserve/donor pairing, 20% positive-transfer probability
and mean-neutral negative transfer. It shares only the transfer sign across
disjoint pairs on one team. This changes dependence while preserving each
player's minute law in distribution. It is a latent-regime ablation, not a fitted
blowout, substitution or foul-trouble model.

The policy was fixed before the multi-build replay. Eight saved DK/FD builds
span four dates and 24 physical games. Source manifests and observed pre-tip
cutoffs are checked; actual-OT games are withheld from regulation-minute scores.
Primary comparison deduplicates team snapshots across sites, choosing the latest
observed pregame capture and bootstrapping paired losses by physical game.
Missing actuals remain unmatched. These are development cases, not fresh holdouts.

Reproduce the sampler/pregame diagnostics with:

```
python scripts/audit_shared_bench_offline.py BUILD_DIRECTORY AUDIT_ZIP OUTPUT_DIRECTORY
```

The optional known-lineup full-game check verifies source-code equality against
the frozen production implementation, reuses its saved baseline, and runs the
shared arm construction-first before independent evaluation. It does not use a
simulation cache, regenerate candidates, rerank portfolios or optimize parameters
against the hindsight-known lineup:

```
python scripts/check_shared_bench_full_game_offline.py BUILD_ZIP LINEUP_JSON OUTPUT_JSON
```

Initial results are promising for minute dependence but not promotion-ready:
joint-tail proper scores improved on average, game-cluster confidence intervals
included no improvement, and the fully shared treatment overpredicted joint
upper-minute events. Individual minute interval coverage stayed unchanged, as
expected for a dependence-only change. Saved fantasy intervals covered roughly
82–84% when actual minutes were within two of projection; that diagnostic does
not support blanket widening of per-minute production distributions.

The November 13 diagnostic increases the known lineup's P99 only from 302.25 to
305.75. Two versus three tail hits in 10,000 draws is not evidence of a reliable
probability increase. Keep the experiment offline. Future conditioning should
be learned from earlier data and tested on untouched slates, with player/team
mean checks and proper distribution scores. Do not tune to make a known winning
lineup rank highly, or confuse joint event frequency with regime probability.
