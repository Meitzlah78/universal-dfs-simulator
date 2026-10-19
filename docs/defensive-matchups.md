Defensive matchup context
=========================

All four formats use the shared NFL engine. Before SIM, nflverse weekly player
statistics are joined to the nflverse schedule by game_id. The player's verified
Weather Kickoff is the cutoff. Same-day games, undated games, future games and
history older than 400 days are excluded. Missing kickoff, missing source columns
or fewer than four defensive games leaves the matchup neutral.

RB/WR/TE/QB receiving yards per reception and rushing yards per carry allowed by
that opponent and position are compared with the league's same-position rates.
At least 20 relevant opportunities are required. Ratios shrink toward neutral
with eight games of prior weight and are capped at 0.90–1.10. QB sack risk uses
sacks suffered / (attempts + sacks), requires 100 dropbacks, adds a 200-dropback
prior at 6.5%, and is capped at 4–9%.

These descriptive rates are not adjusted for opponent quality, roster turnover
or individual coverage assignments. They affect generated plays before projection
fitting, never add fantasy points afterward, and do not replace external point
projections. Projection fitting may offset much of a mean efficiency change;
there is no claim of improved predictive accuracy without holdout validation.

The SIM panel shows each player's opponent, usable sample, latest included game
date, factors and neutral status. The full input snapshot participates in the
existing role/cache fingerprint. Schedule requests are cached daily and bounded
by connection/read timeouts. BUILD performs no additional matchup downloads.

Sources:
https://nflreadr.nflverse.com/reference/load_player_stats.html
https://github.com/nflverse/nfldata/blob/master/data/games.csv
