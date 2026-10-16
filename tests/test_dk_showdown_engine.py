import numpy as np
import pandas as pd

from dk_showdown_engine import (
    ShowdownRules,
    exact_duplicate_counts,
    lineup_key,
    lineup_salary,
    score_lineup_matrix,
)


def test_lineup_salary_matches_dk_showdown_math():
    salaries = np.array([10000, 9000, 8000, 7000, 6000, 5000], dtype=float)
    assert lineup_salary(0, [1, 2, 3, 4, 5], salaries) == 50000


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
