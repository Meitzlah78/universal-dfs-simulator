# Opponent proposal correction

When ownership is absent, fallback weights now preserve posted projection
magnitude and salary efficiency. The old positive rank floor gave near-zero
backups substantial weight. New weights are proportional to projection squared
times projection per salary. These are sampling preferences, not projected
ownership percentages. They do not use player identity, actual points or settled
ownership. Existing market factors remain applied by the app.

External ownership retains priority. Valid uploaded zeroes stay valid. Blank or
entirely invalid ownership columns no longer block automatic loading. Unlisted
Footballguys rows use the same explicitly labeled fallback.

FD full-roster proposals now receive the projected-strength preference already
present in DK, using its existing coefficient 0.85. Historical salary frequencies
normalize strength weights within salary buckets before rejection. Learned
joint stack/bring-back quotas and natural duplicate rosters remain supported.
User lineup rules, point projections and final opponent counts are unchanged.

The final ownership selector uses a direct capped-proportional quota solve,
replacing a bounded normalization loop that could stop before reaching feasible
capacity with concentrated weights. Tests cover exact counts, quotas and no
reused proposal rows.

Three fixed seeds on the saved FD slate improved opponent strength; a residual
average-score gap remains. The contest supplied construction training data, so
these are diagnostics, not independent accuracy or profitability validation.
Full results are in benchmarks/fd-opponent-fix-comparison.json. The repeatable
scripts/compare_fd_field.py uses supplied frozen inputs with default historical
roles and neutral weather, not reconstructed original app conditions.

The game engine links offense with defense scoring, but this change does not
add measured defense-versus-position ratings. That requires a separate dated
pregame matchup data pipeline and projection-anchoring validation.
