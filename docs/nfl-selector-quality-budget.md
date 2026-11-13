# NFL portfolio quality budget

Applies to DK Showdown/Classic and FD Single Game/Full Roster. The NBA selector
and experimental PBP situational model are not changed or imported.

Selection maximizes the sum of pregame Top1 estimates under all requested
overall, special-role and FLEX exposure limits, locks/fades, and automatic cap.
The second stage minimizes squared overall exposure while retaining at least
95% of that best feasible sum. Quality is an estimated count of top-1% entries,
not portfolio ROI. Other ranking choices sort displayed tables only.

The existing diversity slider sets the hard automatic cap to 100 minus .4 times
the slider value. Caps never relax. With a single entry, any cap below 100% is
infeasible; choose diversity 0 explicitly rather than silently rounding the cap.

Each stage has a 15-second solver limit. An uncertified quality optimum or
infeasible limits stop selection with a UI error and warning log. Saved lineups
are copied before build invalidation and are not replaced by a failed result.
A valid concentration-stage timeout is labeled in the UI/logs. If prior lineups
exist, a preview is shown and they remain assigned until the user chooses
"Use validated timeout portfolio". The prior copy remains recoverable. For a
first portfolio, a validated timeout result can be used immediately. No timeout
result is claimed to have minimum possible concentration.

Selection is cached by canonical candidate identities/Top1 values, count,
controls and cap. Changing display sorting does not reselect entries. Updated
nonselection metrics are read from the current candidate frame on cache reuse.
Recovery and caches are scoped by slate workspace, site, format and contest.

Validation before integration: nine exact/constraint/timeout tests; eight
development slates; six additional retrospective scored site/slates including
Classic and Full Roster. Five of six additional cases improved replayed net.
One FD case lost about ten cents. Two other full-roster files lacked evidence
and were excluded. These historical results do not guarantee future profit.

Integration tests cover saved-lineup recovery across all formats, both timeout
paths, explicit acceptance of a preview, cache isolation, display-order
independence and owned-entry assignment counts. No learned-model promotion or
learning-validation bypass is part of this change.
