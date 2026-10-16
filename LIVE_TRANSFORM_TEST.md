# DK Showdown live transform test

This branch is reserved for the permanent `dfs_app.py` install and CI verification of the already-validated exhaustive-build and post-Contest-Sim diversification transforms.

Baseline before app replacement:
- source branch: `install/dk-showdown-production-transforms`
- candidate build currently still uses the legacy weighted/random generator
- post-sim portfolio currently still contains the hidden 90% exposure and two-unique rules
- `main` is intentionally untouched

The next app commit must replace only the validated Step 2 candidate-build region and post-sim portfolio-selection region, then pass syntax and DK engine regression checks before promotion.
