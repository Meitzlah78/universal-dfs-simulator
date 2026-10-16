"""Shared normalization helpers for NFL stat feeds."""

TWO_POINT_CONVERSION_COLUMNS = (
    'passing_2pt_conversions',
    'rushing_2pt_conversions',
    'receiving_2pt_conversions',
)


def historical_two_point_conversions(row):
    """Return successful offensive 2PT conversions credited to one player row."""
    total = 0.0
    for column in TWO_POINT_CONVERSION_COLUMNS:
        try:
            value = row.get(column, 0)
            if value is None:
                continue
            numeric = float(value)
            if numeric == numeric:  # ignore NaN without requiring pandas/numpy here
                total += numeric
        except (TypeError, ValueError):
            continue
    return total
