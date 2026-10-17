import numpy as np
from dk_showdown_field_calibration import projected_duplicate_counts


def test_projected_dupes_shape_and_monotonicity():
    log_weights = np.array([-8.0, -5.0, -2.0, 0.0])
    dupes = projected_duplicate_counts(log_weights, 50000)
    assert dupes.shape == log_weights.shape
    assert np.all(dupes >= 0)
    assert dupes[-1] > dupes[0]


def test_projected_dupes_uses_empirical_field_counts():
    log_weights = np.array([-2.0, -1.0, 0.0])
    empirical = np.array([1, 7, 80])
    dupes = projected_duplicate_counts(log_weights, 47562, empirical)
    assert dupes.tolist() == [1, 7, 80]
