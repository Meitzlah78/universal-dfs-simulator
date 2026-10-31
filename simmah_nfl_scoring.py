"""Pure NFL scoring shared by offline preparation and the Streamlit app."""
import numpy as np

DFS_SCORING_RULES = {'DraftKings': {'pass_yard': 0.04, 'pass_td': 4, 'interception': -1, 'rush_yard': 0.1, 'rush_td': 6, 'receiving_yard': 0.1, 'receiving_td': 6, 'reception': 1, 'fumble_lost': -1, 'two_point_conversion': 2, 'pass_300_bonus': 3, 'rush_100_bonus': 3, 'receiving_100_bonus': 3, 'single_game_multiplier': 1.5, 'sack': 1, 'def_interception': 2, 'fumble_recovery': 2, 'defensive_td': 6, 'safety': 2, 'blocked_kick': 2}, 'FanDuel': {'pass_yard': 0.04, 'pass_td': 4, 'interception': -1, 'rush_yard': 0.1, 'rush_td': 6, 'receiving_yard': 0.1, 'receiving_td': 6, 'reception': 0.5, 'fumble_lost': -2, 'two_point_conversion': 2, 'pass_300_bonus': 0, 'rush_100_bonus': 0, 'receiving_100_bonus': 0, 'single_game_multiplier': 1.5, 'sack': 1, 'def_interception': 2, 'fumble_recovery': 2, 'defensive_td': 6, 'safety': 2, 'blocked_kick': 2}}

def score_nfl_stat_line(stats, platform):
    """Apply DraftKings or FanDuel NFL scoring to simulated player stat lines."""
    rules = DFS_SCORING_RULES['FanDuel' if str(platform).lower().startswith('fanduel') else 'DraftKings']
    arr = lambda key: np.asarray(stats.get(key, 0), dtype=float)
    passing_yards, rushing_yards, receiving_yards = (arr('passing_yards'), arr('rushing_yards'), arr('receiving_yards'))
    score = passing_yards * rules['pass_yard'] + arr('passing_tds') * rules['pass_td'] + arr('interceptions') * rules['interception'] + rushing_yards * rules['rush_yard'] + arr('rushing_tds') * rules['rush_td'] + receiving_yards * rules['receiving_yard'] + arr('receiving_tds') * rules['receiving_td'] + arr('receptions') * rules['reception'] + arr('fumbles_lost') * rules['fumble_lost'] + arr('two_point_conversions') * rules['two_point_conversion'] + arr('sacks') * rules['sack'] + arr('def_interceptions') * rules['def_interception'] + arr('fumble_recoveries') * rules['fumble_recovery'] + arr('defensive_tds') * rules['defensive_td'] + arr('safeties') * rules['safety'] + arr('blocked_kicks') * rules['blocked_kick']
    score = score + (passing_yards >= 300) * rules['pass_300_bonus']
    score = score + (rushing_yards >= 100) * rules['rush_100_bonus']
    score = score + (receiving_yards >= 100) * rules['receiving_100_bonus']
    score = score + arr('fg_under_40') * 3 + arr('fg_40_49') * 4 + arr('fg_50_plus') * 5
    score = score + arr('extra_points_made')
    points_allowed = arr('points_allowed')
    score = score + np.select([points_allowed == 0, points_allowed <= 6, points_allowed <= 13, points_allowed <= 20, points_allowed <= 27, points_allowed <= 34], [10, 7, 4, 1, 0, -1], default=-4) * np.asarray(stats.get('is_defense', 0), dtype=float)
    return score
