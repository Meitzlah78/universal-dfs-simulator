"""Count exact roster matches in the simulated opponent field."""
from collections import Counter

import pandas as pd


def showdown_opponent_copies(portfolio, field):
    """Keep Captain distinct and ignore FLEX ordering; do not count user entries."""
    slots = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
    result = pd.Series(pd.NA, index=portfolio.index, dtype="Int64")
    if not isinstance(field, pd.DataFrame) or not all(c in field for c in slots):
        return result
    if not all(c in portfolio for c in slots):
        return result

    def key(row):
        if any(pd.isna(value) or not str(value).strip() for value in row):
            return None
        players = [str(value).strip().casefold() for value in row]
        return players[0], tuple(sorted(players[1:]))

    counts = Counter(k for row in field[slots].itertuples(index=False, name=None)
                     if (k := key(row)) is not None)
    return pd.Series([counts.get(k, 0) if (k := key(row)) is not None else pd.NA
                      for row in portfolio[slots].itertuples(index=False, name=None)],
                     index=portfolio.index, dtype="Int64")
