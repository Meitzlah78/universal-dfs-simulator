# RotoWire automatic projections

The shared projection loader now averages positive finite DFF, DraftEdge and public RotoWire optimizer projections. RotoWire is skipped whenever a projection CSV is supplied, preserving the existing uploaded-input behavior. Existing injury filtering and no-internal-estimates rules remain in place.

The adapter uses the optimizer's public JSON requests (`slate-list.php`, `players.php`, `projections.php`) without credentials. It requires `access: true` and source `RotoWire`; it does not request premium data or use the unrelated authenticated API client package.

Site IDs and contest types distinguish DraftKings Classic / Showdown and FanDuel Full Roster / SingleGame. Exactly one listed slate must have the exact salary-pool team set and game-date set. Ambiguity, old dates, wrong teams, wrong format, access errors, missing IDs and invalid points cannot silently select a default slate. Salary game/date fields are retained for matching. If the salary file has no game date, only today's games in America/New_York are eligible and this limitation is displayed. Undated future slates require another source or an uploaded projection file.

Values join players by the provider's slate-player IDs before name normalization. Defense full names, nicknames and team abbreviations are supported. Points are base player points; Captain/MVP multipliers remain in the existing scoring engine. Zero, missing and nonfinite values do not enter the average.

Successful downloads cache for 15 minutes, keyed by platform, teams and dates. The existing manual projection refresh clears this cache. Failures raise and are not cached. RotoWire is not yet part of the separate background change-notification poll, and this is not a persistent last-good snapshot fallback.

Validation: six unit tests cover all four format selectors, mismatched teams/date/format, ambiguous slates, defense aliases, positive-only scoring, upload precedence and three-source averaging. Saved live October 19 responses verify WAS/SF DK Showdown and FD Single Game, including both kickers and defenses. Actual public accessibility does not establish uptime or projection accuracy. Current HTML/API schemas can change.
