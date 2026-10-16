"""Production adapter for fast exhaustive DraftKings Showdown candidate builds."""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from dk_showdown_exhaustive import fast_exhaustive_showdown_candidates


def build_showdown_candidates(
    players: pd.DataFrame,
    player_sim: Mapping[str, Mapping[str, float]],
    ownership_proxy: Mapping[str, float],
    controls: pd.DataFrame | None = None,
    candidate_count: int = 5000,
    salary_floor: int = 0,
    salary_cap: int = 50000,
    p95_weight: float = 0.30,
    p99_weight: float = 0.55,
    mean_weight: float = 0.15,
    stddev_weight: float = 0.10,
) -> pd.DataFrame:
    """Build the strongest legal candidate pool without portfolio diversification.

    Only hard eligibility controls are applied here. Exposure spreading and Min
    Uniques belong after Contest Sim, not in candidate generation. The returned
    schema intentionally matches the live Showdown candidate table so Contest Sim
    can consume this builder without a second translation layer.
    """
    pool = players.copy()
    required = {"Name", "Salary", "Team"}
    missing = required.difference(pool.columns)
    if missing:
        raise KeyError("missing player columns: " + ", ".join(sorted(missing)))

    locked_players: set[str] = set()
    captain_eligible: dict[str, bool] | None = None
    if controls is not None and not controls.empty and "Name" in controls.columns:
        ctl = controls.drop_duplicates("Name", keep="last").set_index("Name")
        if "Fade" in ctl.columns:
            faded = set(ctl.index[ctl["Fade"].fillna(False).astype(bool)])
            pool = pool[~pool["Name"].isin(faded)].copy()
        if "Lock" in ctl.columns:
            locked_players = set(ctl.index[ctl["Lock"].fillna(False).astype(bool)])
        if "Captain Max %" in ctl.columns:
            cpt_max = pd.to_numeric(ctl["Captain Max %"], errors="coerce").fillna(100.0)
            captain_eligible = {str(name): bool(value > 0) for name, value in cpt_max.items()}

    result = fast_exhaustive_showdown_candidates(
        pool,
        player_sim,
        ownership_proxy,
        keep=candidate_count,
        salary_cap=salary_cap,
        salary_floor=salary_floor,
        p95_weight=p95_weight,
        p99_weight=p99_weight,
        mean_weight=mean_weight,
        stddev_weight=stddev_weight,
        require_two_teams=True,
        locked_players=locked_players,
        captain_eligible=captain_eligible,
    )
    if result.empty:
        return result

    # Keep the exhaustive diagnostics before adding derived columns; pandas can
    # otherwise drop attrs during intermediate dataframe operations.
    diagnostics = {
        "examined_lineups": result.attrs.get("examined_lineups", 0),
        "legal_lineups": result.attrs.get("legal_lineups", 0),
        "retained_lineups": result.attrs.get("retained_lineups", len(result)),
    }

    # The old handoff iterated 5,000 Python rows three separate times after the
    # exhaustive search had already completed. Build a compact numeric lookup and
    # calculate all three metrics in vectorized arrays instead. This reduces the
    # post-build CPU/object churn at the exact Streamlit handoff boundary.
    roster_cols = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
    multipliers = np.asarray([1.5, 1.0, 1.0, 1.0, 1.0, 1.0], dtype=np.float64)
    roster = result[roster_cols].to_numpy(dtype=object, copy=False)
    unique_names = pd.unique(roster.ravel())
    name_to_index = {str(name): i for i, name in enumerate(unique_names)}
    indices = np.fromiter(
        (name_to_index[str(name)] for name in roster.ravel()),
        dtype=np.int32,
        count=roster.size,
    ).reshape(roster.shape)

    for output_col, metric in (("SimMean", "Mean"), ("SimP95", "P95"), ("SimP99", "P99")):
        lookup = np.asarray(
            [float(player_sim.get(str(name), {}).get(metric, 0.0)) for name in unique_names],
            dtype=np.float64,
        )
        result[output_col] = (lookup[indices] * multipliers).sum(axis=1)

    result["Score"] = pd.to_numeric(result["CandidateScore"], errors="coerce")
    result.attrs.update(diagnostics)
    return result
