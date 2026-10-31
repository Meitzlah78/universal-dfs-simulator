"""User build exclusions leave full-slate simulations and opponents intact."""
import numpy as np
from simmah_nba_projections import team_key


def game_options(pool):
    pairs={tuple(sorted((team_key(r.Team),team_key(r.Opponent)))) for r in pool.itertuples()}
    return {' vs '.join(pair):pair for pair in sorted(pairs)}


def excluded_player_indices(pool,games=(),teams=()):
    options=game_options(pool);known={team_key(team) for team in pool['Team']}
    selected_teams={team_key(team) for team in teams}
    if not set(games)<=set(options) or not selected_teams<=known:
        raise ValueError('Exclusion does not match the loaded slate')
    selected_games={options[label] for label in games}
    return np.array([i for i,row in enumerate(pool.itertuples())
        if team_key(row.Team) in selected_teams or
        tuple(sorted((team_key(row.Team),team_key(row.Opponent)))) in selected_games],dtype=int)
