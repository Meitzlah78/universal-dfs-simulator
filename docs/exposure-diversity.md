# Final lineup exposure diversity

The main Lineup exposure diversity slider selects the final portfolio from existing candidates. It no longer refers to how many construction scenarios are averaged for each candidate. That separate existing control is available under Advanced: candidate construction, with its own unchanged session key and construction behavior.

Preferred automatic overall player cap = 100 - 0.4 * diversity percent. Thus 0 -> 100%, 50 -> 80%, 100 -> 60%. The roster-overlap penalty rises linearly from 0 to 0.7 normalized utility units. At zero, unconstrained selection follows ranking order. These are transparent heuristic preferences, not a proprietary optimizer or a promise of monotonic diversity when candidate support, manual limits, and locks constrain the solution.

Manual minimums, maximums, player locks/fades, and explicit Captain/MVP limits remain authoritative. Automatic caps may relax in five-point steps only after the integer solver proves the tighter bound infeasible; manual limits never relax. The UI reports relaxation. Identical roster duplicates never pad the portfolio, and CPT/MVP identity remains part of roster uniqueness.

DK Classic, DK Showdown, FD Full Roster and FD Single Game now use the same selector. FD Single previously took the first displayed rows and could repeat rows to fill entries; it now selects the reserved-entry count from all candidates under exposure constraints. DK Showdown's legacy separate overlap selector is replaced by the shared implementation. Changing the diversity slider reselects without running player simulations or rebuilding candidates. No simulation counts or scoring rules are changed.

Tests cover reduced concentration at higher settings, rank order at zero, candidate preservation, both special-role limits, hard-limit repair, all format call sites and independent construction/exposure widgets in real Streamlit AppTest.
