# DAL–GB Showdown opponent learning

Completed contest 196786594 adds 35,434 valid six-player lineups to the anonymous
DK Showdown history, scoped to one game, low stakes and a 20-entry limit.
Incomplete or repeated-player rosters are excluded by the existing parser.

The stored features include total ownership concentration, log ownership product
and captain popularity. Captain popularity is the captain's share of captain
selections across the complete supplied field. The profile stores histograms,
not player identities, actual points or finishing ranks. Verified historical
salary/team metadata was unavailable for this import, so no salary or team
features are invented.

Generated slot labels are now normalized before historical calibration, so
Captain and CPT both activate the captain feature. Matching historical
histograms reweight an oversized legal opponent proposal pool with bounded
weights. Unsupported shapes cannot be created by reweighting.

This affects user builds through opponent-based evaluation and ranking. It is
not a new supervised lineup winner model. The app does not imitate the winning
players from one game or optimize on this contest's actual points. Duplicate
counts remain recorded diagnostics, not an actively fitted duplicate model.

Future slates must test whether these patterns improve field realism and
selection. This contest is training data and cannot also establish holdout ROI.
