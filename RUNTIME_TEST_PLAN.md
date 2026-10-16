# Simmah runtime test gate

Immediate test target:

1. Build 5,000 competitive Showdown candidates.
2. Run those candidates through Contest Sim.
3. Apply Portfolio or user-selected Min Uniques only after Contest Sim.
4. Record candidate-build elapsed time separately from Contest Sim elapsed time.
5. If exhaustive candidate generation is too slow in the deployed Streamlit environment, replace only candidate generation with the weighted 5,000-candidate builder; keep the Contest Sim, EV, payout/duplication, and post-sim diversification pipeline unchanged.

This branch is the isolated runtime-test branch; main is not targeted.
