"""Speed guard for the exhaustive DK Showdown prescreen."""
import time
import numpy as np
import pandas as pd
from dk_showdown_exhaustive import fast_exhaustive_showdown_candidates

rng = np.random.default_rng(20261016)
n = 40
players = pd.DataFrame({
    "Name": [f"P{i}" for i in range(n)],
    "Salary": rng.integers(2000, 12001, size=n),
    "Team": ["A" if i % 2 else "B" for i in range(n)],
})
sim = {}
own = {}
for i, name in enumerate(players["Name"]):
    mean = float(rng.uniform(2, 24))
    sim[name] = {
        "Mean": mean,
        "P95": mean + float(rng.uniform(4, 14)),
        "P99": mean + float(rng.uniform(8, 22)),
        "StdDev": float(rng.uniform(2, 10)),
    }
    own[name] = float(rng.uniform(2, 45))

start = time.perf_counter()
result = fast_exhaustive_showdown_candidates(players, sim, own, keep=5000)
elapsed = time.perf_counter() - start
examined = result.attrs["examined_lineups"]
rate = examined / max(elapsed, 1e-9)
print(f"examined={examined:,} legal={result.attrs['legal_lineups']:,} retained={len(result):,} elapsed={elapsed:.3f}s rate={rate:,.0f}/s")
assert len(result) <= 5000
# CI guard is intentionally generous; its purpose is to catch accidental return
# to per-lineup pandas/Python scoring, not to enforce workstation-specific speed.
assert rate >= 100_000, f"exhaustive prescreen too slow: {rate:,.0f} lineups/s"
