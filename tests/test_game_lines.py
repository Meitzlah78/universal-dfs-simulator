import ast
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
from simmah_game_lines import implied_scores, field_market_factors


def test_implied_scores_and_invalid_inputs():
    assert implied_scores(48, -6) == (21, 27)
    assert implied_scores(48, 6) == (27, 21)
    assert implied_scores(48, 0) == (24, 24)
    for total, spread in [(None, 0), (48, None), (float('nan'), 0), (0, 0), (40, 40)]:
        assert implied_scores(total, spread) is None


def test_markets_are_neutral_when_missing_and_bounded():
    pool = pd.DataFrame({'Team': ['LA', 'BUF', 'MIA'], 'Position': ['WR', 'DST', 'QB']})
    np.testing.assert_array_equal(field_market_factors(pool, {}), [1, 1, 1])
    factors = field_market_factors(pool, {'LAR': (40, 10), 'BUF': (27, 17)})
    assert factors[0] == 1.15
    assert factors[1] > 1
    assert factors[2] == 1


def test_app_ownership_priority_and_fallback_integration():
    tree = ast.parse(Path('dfs_app.py').read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'opponent_field_selection_weights')
    namespace = {'np': np, 'pd': pd, 'st': SimpleNamespace(session_state={'active_game_markets': {'LAR': (30, 20)}})}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'dfs_app.py', 'exec'), namespace)
    weights = namespace[fn.name]
    pool = pd.DataFrame({'Team': ['LAR', 'BUF'], 'Position': ['WR', 'WR']})
    baseline = .1 + pd.Series([20, 20]).rank(pct=True).to_numpy() ** 2
    assert weights(pool, [20, 20])[0] > baseline[0]
    pool['Projected Ownership'] = [25., 15.]
    np.testing.assert_array_equal(weights(pool, [20, 20]), [25, 15])
    pool['Ownership Selection Weight'] = [25., 15.]
    pool['Ownership Source'] = ['Projection-rank fallback (unlisted)', 'Footballguys']
    adjusted = weights(pool, [20, 20])
    assert adjusted[0] > 25 and adjusted[1] == 15
