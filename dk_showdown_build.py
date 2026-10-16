"""Production adapter for fast exhaustive DraftKings Showdown candidate builds."""

from __future__ import annotations

from typing import Mapping

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
    """Build the strongest legal candidate pool without portfolio diversification."""
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

    # The exhaustive engine already computes and returns SimMean/SimP95/SimP99,
    # Score, Salary, and diagnostics for the retained 5,000. Return that frame
    # directly instead of rebuilding lineup metrics at the Streamlit handoff.
    return fast_exhaustive_showdown_candidates(
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
        chunk_size=10000,
    )
