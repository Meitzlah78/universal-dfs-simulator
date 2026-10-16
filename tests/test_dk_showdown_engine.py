import numpy as np
import pandas as pd

from dk_showdown_engine import (
    ShowdownRules,
    candidate_score,
    exact_duplicate_counts,
    lineup_key,
    lineup_salary,
    score_lineup_matrix,
)


def test_lineup_salary_matches_dk_showdown_math():
    salaries = np.array([10000, 9000, 8000, 7000, 6000, 5000], dtype=float)
    assert lineup_salary(0, [1, 2, 3, 4, 5], salaries) == 50000


def test_candidate_score_matches_existing_app_formula():
    player_sim = {
        "A": {"Mean": 20.0, "P95": 32.0, "P99": 40.0, "StdDev": 8.0},
        "B": {"Mean": 15.0, "P95": 25.0, "P99": 31.0, "StdDev": 6.0},
        "C": {"Mean": 12.0, "P95": 20.0, "P99": 28.0, "StdDev": 5.0},
        "D": {"Mean": 10.0, "P95": 17.0, "P99": 24.0, "StdDev": 4.0},
        "E": {"Mean": 8.0, "P95": 14.0, "P99": 19.0, "StdDev": 3.0},
        "F": {"Mean": 6.0, "P95": 11.0, "P99": 16.0, "StdDev": 2.0},
    }
    ownership = {"A": 35.0, "B": 30.0, "C": 25.0, "D": 20.0, "E": 15.0, "F": 10.0}
    captain = "A"
    flex = ("B", "C", "D", "E", "F")
    p95_weight, p99_weight, mean_weight, stddev_weight = 0.30, 0.55, 0.15, 0.10

    total_mean = player_sim[captain]["Mean"] * 1.5 + sum(player_sim[p]["Mean"] for p in flex)
    total_p95 = player_sim[captain]["P95"] * 1.5 + sum(player_sim[p]["P95"] for p in flex)
    total_p99 = player_sim[captain]["P99"] * 1.5 + sum(player_sim[p]["P99"] for p in flex)
    total_stddev = player_sim[captain]["StdDev"] * 1.5 + sum(player_sim[p]["StdDev"] for p in flex)
    raw_score = (
        total_p95 * p95_weight
        + total_p99 * p99_weight
        + total_mean * mean_weight
        + total_stddev * stddev_weight
    )
    lineup_ownership = ownership[captain] * 1.5 + sum(ownership[p] for p in flex)
    lineup_upside = max(0.0, total_p99 - total_p95)
    ownership_tax = max(0.0, lineup_ownership - 15.0 * 6.5) * 0.06
    upside_credit = min(ownership_tax, lineup_upside * 0.08)

    actual = candidate_score(
        captain, flex, player_sim, ownership,
        p95_weight, p99_weight, mean_weight, stddev_weight,
    )
    assert actual["SimMean"] == total_mean
    assert actual["SimP95"] == total_p95
    assert actual["SimP99"] == total_p99
    assert actual["Score"] == raw_score - ownership_tax + upside_credit


def test_vectorized_scores_match_legacy_loop_math():
    simulations = np.array(
        [
            [10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0],
            [20.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
        ]
    )
    captains = np.array([0, 6])
    flex = np.array([[1, 2, 3, 4, 5], [0, 1, 2, 3, 4]])

    legacy = np.empty((len(simulations), len(captains)), dtype=float)
    for scenario in range(len(simulations)):
        for lineup in range(len(captains)):
            legacy[scenario, lineup] = (
                simulations[scenario, captains[lineup]] * 1.5
                + sum(simulations[scenario, player] for player in flex[lineup])
            )

    actual = score_lineup_matrix(simulations, captains, flex)
    np.testing.assert_allclose(actual, legacy)


def test_exact_duplicates_ignore_flex_order_but_not_captain():
    lineups = pd.DataFrame(
        [
            {"Captain": "A", "Flex1": "B", "Flex2": "C", "Flex3": "D", "Flex4": "E", "Flex5": "F"},
            {"Captain": "A", "Flex1": "F", "Flex2": "E", "Flex3": "D", "Flex4": "C", "Flex5": "B"},
            {"Captain": "B", "Flex1": "A", "Flex2": "C", "Flex3": "D", "Flex4": "E", "Flex5": "F"},
        ]
    )
    assert exact_duplicate_counts(lineups).tolist() == [2, 2, 1]
    assert lineup_key("A", ["B", "C", "D", "E", "F"]) != lineup_key("B", ["A", "C", "D", "E", "F"])


def test_rejects_wrong_flex_width():
    values = np.ones((2, 6))
    try:
        score_lineup_matrix(values, np.array([0]), np.array([[1, 2, 3, 4]]), ShowdownRules())
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for a lineup without five FLEX players")
