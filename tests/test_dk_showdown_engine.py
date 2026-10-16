import numpy as np
import pandas as pd

from dk_showdown_engine import (
    ShowdownRules,
    candidate_score,
    duplicate_expansion_counts,
    duplicate_expansion_weights,
    exact_duplicate_counts,
    lineup_key,
    lineup_salary,
    sample_opponent_batch,
    score_lineup_matrix,
    score_showdown_chunks,
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
    captain = "A"; flex = ("B", "C", "D", "E", "F")
    p95_weight, p99_weight, mean_weight, stddev_weight = 0.30, 0.55, 0.15, 0.10
    total_mean = player_sim[captain]["Mean"] * 1.5 + sum(player_sim[p]["Mean"] for p in flex)
    total_p95 = player_sim[captain]["P95"] * 1.5 + sum(player_sim[p]["P95"] for p in flex)
    total_p99 = player_sim[captain]["P99"] * 1.5 + sum(player_sim[p]["P99"] for p in flex)
    total_stddev = player_sim[captain]["StdDev"] * 1.5 + sum(player_sim[p]["StdDev"] for p in flex)
    raw_score = total_p95*p95_weight + total_p99*p99_weight + total_mean*mean_weight + total_stddev*stddev_weight
    lineup_ownership = ownership[captain]*1.5 + sum(ownership[p] for p in flex)
    tax = max(0.0, lineup_ownership - 15.0*6.5)*0.06
    credit = min(tax, max(0.0, total_p99-total_p95)*0.08)
    actual = candidate_score(captain, flex, player_sim, ownership, p95_weight, p99_weight, mean_weight, stddev_weight)
    assert actual == {"SimMean": total_mean, "SimP95": total_p95, "SimP99": total_p99, "Score": raw_score-tax+credit}


def test_duplicate_expansion_weights_match_current_calibration():
    log_weights = np.linspace(-8.0, 0.0, 500, dtype=np.float64)
    centered = log_weights - np.max(log_weights)
    base = np.exp(centered*0.38); base /= base.sum(); total = len(log_weights)
    broad_count = min(max(250, min(1800, max(250, total//5))), total)
    broad_indices = np.argpartition(log_weights, -broad_count)[-broad_count:]
    broad = np.zeros(total); broad_strength = np.exp(centered[broad_indices]*0.80)
    broad[broad_indices] = broad_strength/broad_strength.sum()
    top_count = max(10, min(40, total)); top_indices = np.argpartition(log_weights, -top_count)[-top_count:]
    top = np.zeros(total); top_strength = np.exp(centered[top_indices]*1.20); top[top_indices] = top_strength/top_strength.sum()
    expected = 0.57*base + 0.25*broad + 0.18*top; expected /= expected.sum()
    np.testing.assert_allclose(duplicate_expansion_weights(log_weights), expected, rtol=0.0, atol=1e-15)


def test_duplicate_expansion_counts_are_exact_and_deterministic():
    values = np.random.default_rng(20261016).normal(-14.0, 2.0, size=10_000)
    a = duplicate_expansion_counts(values, 47_271, seed=7)
    b = duplicate_expansion_counts(values, 47_271, seed=7)
    np.testing.assert_array_equal(a, b)
    assert a.dtype == np.int64
    assert np.all(a >= 0)
    assert int(a.sum()) == 47_271


def test_duplicate_expansion_weights_handle_small_and_empty_fields():
    assert duplicate_expansion_weights([]).size == 0
    weights = duplicate_expansion_weights([0.0, -1.0, -2.0])
    assert weights.shape == (3,) and np.all(weights > 0) and np.isclose(weights.sum(), 1.0)


def test_opponent_batch_sampler_has_valid_unique_flex_and_no_captain_overlap():
    rng = np.random.default_rng(123)
    captain_weights = np.array([10, 8, 6, 4, 3, 2, 1], dtype=float)
    flex_weights = np.array([9, 8, 7, 6, 5, 4, 3], dtype=float)
    captains, flex = sample_opponent_batch(rng, captain_weights, flex_weights, 2000)
    assert captains.shape == (2000,)
    assert flex.shape == (2000, 5)
    assert np.all(np.sum(flex == captains[:, None], axis=1) == 0)
    assert np.all(np.array([len(set(row)) for row in flex]) == 5)
    assert np.all((captains >= 0) & (captains < 7))
    assert np.all((flex >= 0) & (flex < 7))


def test_opponent_batch_sampler_is_seed_deterministic():
    cpt = np.array([4, 3, 2, 1, 1, 1], dtype=float)
    flex_w = np.array([1, 2, 3, 4, 5, 6], dtype=float)
    a = sample_opponent_batch(np.random.default_rng(99), cpt, flex_w, 100)
    b = sample_opponent_batch(np.random.default_rng(99), cpt, flex_w, 100)
    np.testing.assert_array_equal(a[0], b[0]); np.testing.assert_array_equal(a[1], b[1])


def test_vectorized_scores_match_legacy_loop_math():
    simulations = np.array([[10.,9.,8.,7.,6.,5.,4.],[20.,3.,4.,5.,6.,7.,8.],[1.,2.,3.,4.,5.,6.,7.]])
    captains = np.array([0,6]); flex = np.array([[1,2,3,4,5],[0,1,2,3,4]])
    legacy = np.empty((len(simulations), len(captains)))
    for s in range(len(simulations)):
        for l in range(len(captains)):
            legacy[s,l] = simulations[s,captains[l]]*1.5 + sum(simulations[s,p] for p in flex[l])
    np.testing.assert_allclose(score_lineup_matrix(simulations, captains, flex), legacy)


def test_score_lineup_matrix_preserves_float32_for_hot_path():
    simulations = np.arange(42, dtype=np.float32).reshape(6, 7)
    captains = np.array([0, 6], dtype=np.int16)
    flex = np.array([[1,2,3,4,5],[0,1,2,3,4]], dtype=np.int16)
    scores = score_lineup_matrix(simulations, captains, flex)
    assert scores.dtype == np.float32


def test_chunked_showdown_scores_equal_one_shot_matrix():
    rng = np.random.default_rng(2026)
    simulations = rng.normal(size=(19, 8)).astype(np.float32)
    lineups = np.array([
        [0,1,2,3,4,5],
        [6,0,1,2,3,4],
        [7,1,2,3,4,5],
    ], dtype=np.int16)
    expected = score_lineup_matrix(simulations, lineups[:, 0], lineups[:, 1:])
    chunks = list(score_showdown_chunks(simulations, lineups, chunk_size=4))
    actual = np.concatenate([scores for _, _, scores in chunks], axis=0)
    assert [(start, end) for start, end, _ in chunks] == [(0,4),(4,8),(8,12),(12,16),(16,19)]
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=0.0)


def test_chunked_showdown_scoring_rejects_bad_inputs():
    values = np.ones((3, 7), dtype=np.float32)
    try:
        list(score_showdown_chunks(values, np.ones((2, 5), dtype=np.int16)))
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for a lineup matrix without six columns")
    try:
        list(score_showdown_chunks(values, np.ones((2, 6), dtype=np.int16), chunk_size=0))
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for zero chunk size")


def test_exact_duplicates_ignore_flex_order_but_not_captain():
    lineups = pd.DataFrame([
        {"Captain":"A","Flex1":"B","Flex2":"C","Flex3":"D","Flex4":"E","Flex5":"F"},
        {"Captain":"A","Flex1":"F","Flex2":"E","Flex3":"D","Flex4":"C","Flex5":"B"},
        {"Captain":"B","Flex1":"A","Flex2":"C","Flex3":"D","Flex4":"E","Flex5":"F"},
    ])
    assert exact_duplicate_counts(lineups).tolist() == [2,2,1]
    assert lineup_key("A", ["B","C","D","E","F"]) != lineup_key("B", ["A","C","D","E","F"])


def test_rejects_wrong_flex_width():
    try:
        score_lineup_matrix(np.ones((2,6)), np.array([0]), np.array([[1,2,3,4]]), ShowdownRules())
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for a lineup without five FLEX players")
