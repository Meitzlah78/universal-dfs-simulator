# NBA remediation: offline foundations

This branch repairs research tooling and adds isolated mechanics/policy challengers. It does not change the live NBA engine, UI selection policy, provider role precedence, or production parameters.

## Implemented

- Separate ESPN rotation reconstruction from the newer NBA CDN parser. Preserve explicit unresolved periods rather than guessing starters. Both research callers use the correct format. Validate complete period coverage and monotonic clocks.
- Update the ownership-upload UI regression to the current two-provider label.
- Add a saved-build selector ablation with source-hash verification. Hold candidates and pregame scores fixed; compare diversity/caps independently. Also exercise the existing 5% budget selector offline, preserving explicit infeasibility and certification-timeout outcomes.
- Add research primitives for conserved stochastic named-player minutes, personal fouls, six-foul disqualification, foul-trouble and optional score-aware blowout priorities, player-specific shooting splits, one/two/three-shot FT handling, and possession/period/24/14-second clocks.
- Couple minutes and foul state in a regulation-only six-second-grid integration harness. Source provisional foul intensities strictly from saved PBP box scores before November 6, 2026. This is not a complete scoring/possession or overtime simulation.
- Add an offline stale-provider blend policy. Unknown freshness and fresh provider roles remain intact; only dated stale rows may blend approved archive components. Future provider timestamps are rejected. No source fantasy projections or minute targets change.

## Measured selector result

On the six previously uncapped builds, diversity 25 reproduces saved selection quality. Diversity zero increases summed pregame Top-1% scores by 32.2–85.4%; removing automatic caps alone has no effect. This isolates the diversity objective rather than correlation generation or stacking rules.

A three-second-per-stage 5% budget experiment succeeds on all six uncapped portfolios. Actual loss versus certified feasible quality optimum is 0–4.98%. Two second-stage searches retain the optimum after timing out; uncapped concentration can reach 100%. No cap was relaxed. Historical Nov 6 capped cases are not comparable to current policy: DK is infeasible under current limits; FD's optimum is not certified within three seconds. These are development results, not profit or promotion evidence.

## Limits and next integration

The broad six-foul rule has a rare exhausted-roster exception under NBA Rule 3. The research harness deliberately reports fewer than five eligible players as unsupported; it does not implement that exception or silently reuse a disqualified player. Other complex shot-clock reset/shot-in-flight rules remain outside the primitive. Independent Poisson foul timing and deficit-based coaching priorities are hypotheses, not trained NBA behavior.

No coverage improvement is claimed. Minutes standard deviations in the harness are assumptions; the archive lacks explicit competition labels. Full-game event/clock/rotation integration, component fitting, point-in-time minutes residual training, independent calibration validation and fresh selector holdouts remain necessary before promotion. The original eight slates are development cases only.

Official references:
- https://official.nba.com/rule-no-3-players-substitutes-and-coaches/
- https://official.nba.com/rule-no-7-24-second-clock/
- https://official.nba.com/rule-no-9-free-throws-and-penalties/

Reproduce tests with `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=.:tests python -m unittest discover -s tests -p 'test_nba*.py'` and `python scripts/check_nba_build.py`.
