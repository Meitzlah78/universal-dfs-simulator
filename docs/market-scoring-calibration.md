# Market scoring calibration

New player simulations use the current slate's valid pregame spread and total as implied team-score targets. External projections still supply the individual opportunity and efficiency fit. A separate deterministic pilot then fits a bounded team yardage-efficiency multiplier (0.65–1.50) toward each implied score. Three updates use 1,024 pilot outcomes by default. Evaluation and construction retain their own distinct seeds and 10,000 outcomes each.

The multiplier changes positive play gains before first downs, touchdowns, passer/receiver stats, field position, and opposing defense scoring are recorded. Fantasy-point arrays are never multiplied afterward. This is an approximate scoring-environment calibration, not a claim that the full outcome distribution, win probabilities, or ROI have been validated. Pilot means and bound hits are exposed in the Market scoring calibration panel. Team targets may not be reached, especially for extreme lines or constrained player inputs.

Market targets are part of the prepared-simulation cache key. Identical inputs reuse prepared outcomes. Changed spreads/totals require new simulation preparation; an exposure-diversity change does not. Missing markets leave the original event model unchanged. Public lines are selected only for matching pregame matchups and dates, with optional manual overrides.

Validation includes direction of calibration on an independent seed, shared passer/receiver yard conservation, target-sensitive cache identity, warm cache reuse, and rejection of mismatched markets during BUILD. Held-out real-contest validation remains outstanding.
