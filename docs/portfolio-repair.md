# Portfolio repair timeout recovery

Large saved candidate pools could reach the bounded integer-search limit without finding a valid portfolio. The previous retries used the full pool or a fixed subset of top-ranked/evenly spaced rows. A timeout does not prove that hard exposure limits are impossible.

For pools larger than 512 candidates and portfolios of at least 20 entries, repair now first solves a bounded continuous relaxation under the same count and exposure constraints. Its nonzero support identifies a much smaller quality-informed integer problem. Integral solutions are returned only after checking cardinality, uniqueness, finite ranking eligibility, every lower bound and every upper bound. Fractional solutions are never rounded into an exported portfolio.

Both relaxation and supported integer search have two-second budgets. A timeout, missing incumbent, invalid incumbent or infeasible restricted support returns to the existing full-pool repair. Restricted-support failure never proves full-pool infeasibility and never authorizes cap relaxation. Existing rules governing automatic preference relaxation remain unchanged; manual caps, role caps, minima and locks remain hard. Repaired portfolios still pass the shared exposure audit and retain the bounded diversification pass.

A 600-candidate regression with simulated integer-solver timeouts reproduced the prior error while a valid 20-entry portfolio existed. The new path returned 20 unique entries satisfying all limits in 0.033 seconds. Direct repair of two archived 5,000-candidate NBA pools returned 101 distinct valid indices in about 0.044 seconds for FanDuel and 0.041 seconds for DraftKings. These are repair-only timings on the test machine, not whole-build timings or a guarantee for tonight's unseen input.

The exact failed live slate has not been captured in this test. An actually infeasible pool or a more difficult bounded search can still stop. No cap, sample-size, duplicate or validation bypass is introduced. Selection version is `quality-role-exposure-v4-lp-repair`; successful greedy selections use the same objective as before.
