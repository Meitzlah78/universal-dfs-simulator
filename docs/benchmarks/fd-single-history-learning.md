# FanDuel Single Game history

Contest 135464-281110099 contributes 95,313 scored complete six-player rosters.
The CSV identifies players by football position, not MVP/FLEX labels. Every
scored roster reconciles exactly to 1.5 times its first-listed player's base
fantasy points plus the five remaining players' points. The importer now
verifies this relationship before assigning MVP/FLEX roles and includes K
position tokens. Missing or conflicting score evidence rejects this inference.
Explicit MVP exports remain supported. Full-roster imports are not reclassified
when the user explicitly selects Full Roster.

Anonymous features capture MVP popularity, overall ownership concentration and
same-file salary usage. The contest has 11,844 unique rosters among 95,313
complete entries. Duplicate counts are recorded, not an actively fitted target.
The existing field calibration uses compatible feature histograms to select
legal proposals. This does not alter player projections or learn winning player
names. FPTS is used to verify the export's slot schema, never as a selection
feature. Future field realism and ROI require independent validation.
