# Shared NFL scoring follow-up

Two-point conversion history should be normalized into one `two_point_conversions` stat before site scoring.

Expected nflverse weekly columns:
- `passing_2pt_conversions`
- `rushing_2pt_conversions`
- `receiving_2pt_conversions`

For each player-game, `two_point_conversions` is the sum of every available 2PT role column. The shared `score_nfl_stat_line()` already awards 2 points per conversion for both DraftKings and FanDuel, so this normalization belongs upstream of site scoring.
