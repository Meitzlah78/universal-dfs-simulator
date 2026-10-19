# Candidate-relative leverage

All four NFL formats show Candidate Best %, Leverage (pp), Leverage Signal,
Leverage Ownership Source and status in the player pool after a candidate build.
CPT/MVP and FLEX shares and leverage are separate when applicable.

For every independent evaluation outcome, score every unique generated
candidate and divide one selection equally among the highest-scoring tied
lineups. Candidate Best % is the player's inclusion share in those selections.
Captain/MVP scores receive their 1.5 multiplier. Classic shares total 900%;
single-game shares total 600%, with special-role shares totaling 100%.

Overall leverage is candidate-best share minus valid projected ownership. When
projected ownership is missing, use simulated opponent field ownership and label
it explicitly. Role-specific leverage uses the matching simulated-field role
ownership. Missing inputs remain pending, including absent or stale-player
simulation data. Zero ownership remains a valid zero; no division by ownership
is used.

This is not a global optimal-lineup probability. The candidate search, player
pool, locks, fades, salary range and stacks all condition the result. Positive
leverage means underownership relative to this restricted candidate set and
model, not a guarantee of profit or an instruction to increase exposure. It
adds an inspectable signal without imposing an extra ownership penalty or
changing Top 1% ranking, simulation counts, candidate count or exposure limits.

The pure calculation uses all supplied outcomes in bounded batches. Streamlit
caches results by outcome and candidate data so ordinary control/ownership
changes can reuse opportunity shares. Changed inputs trigger recomputation.
