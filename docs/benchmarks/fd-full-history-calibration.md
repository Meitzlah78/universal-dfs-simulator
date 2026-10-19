# FanDuel full-roster history calibration

The October 18, 2026 ten-game $0.25 contest supplied 215,417 complete
nine-player rosters out of 215,568 entries. All complete rosters had verified
same-slate salary, position, team and opponent metadata from the saved official
FanDuel salary template. The contest allowed 150 entries per user.

The anonymous seed profile stores aggregate ownership concentration, salary
left, QB pass-catcher stack counts, bring-back counts and RB/defense pairing.
Joint stack/bring-back counts are [32550, 11518, 64058, 57486, 26114, 23691].
Mean salary left was $166.96. Selection is restricted by platform, format,
stake, entry limit and game count using the existing history matcher.

The existing generator uses the learned six-group construction distribution.
The subsequent history selection uses compatible feature histograms. The
existing full-roster salary acceptance inputs and supported salary range remain
in place. Exact historical salary frequencies are not newly imposed by this
change. Duplicate counts are recorded but are not actively fitted.

This does not transfer individual players' settled ownership to future slates,
change player projections, or shift score/ROI outputs to fit the result. Future
ownership targets still depend on the current slate's external ownership or
estimated popularity. The seed contains no names, entry IDs or actual scores.

This contest is calibration data, not a holdout. No claim of improved future
ROI or profitability follows from matching its construction frequencies.
