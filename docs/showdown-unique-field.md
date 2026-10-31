# Showdown opponent sample correction

The October 19 WAS/SF export contained 45,376 estimated entries but only 3,175
unique rosters. The most common John Bates Captain roster appeared 2,779 times.
The old pipeline accepted duplicate proposals, biased Captain acceptance through
the $49K salary floor, then applied a second ownership-based concentration step.
Generated Field CPT ownership was also eligible as a future build input.

The replacement enumerates legal Captain/FLEX combinations, samples without
replacement, then applies existing bounded history selection without replacement.
Captain preferences normalize across each Captain's legal FLEX combinations,
preventing rejection rates from determining Captain popularity. Explicit supplied
Captain ownership can override the fallback; generated field ownership cannot.
Fallback Captain preferences use squared posted projection, an unvalidated
heuristic rather than claimed external ownership.

On the frozen positive-projection WAS/SF pool, only 7,282 legal rosters exist in
$49K–$50K. The opponent-only range is now $48K–$50K, with 15,809 legal combinations
available and a 10,000-roster sample. User lineup-building constraints are unchanged.
A smaller available set is reported explicitly rather than padded with duplicates.
An enumeration guard rejects excessively large pools instead of allowing runaway
memory use. This code applies only to DraftKings Showdown.

Expansion preserves every selected representative once, then uniformly samples
additional rows. It does not multiply ownership weights again or add hardcoded
chalk buckets. Exact duplicates remain possible. This expansion is an estimate,
not a fitted model of real contest duplicate tails. More unique rosters or a lower
maximum duplicate count does not establish better forecast/ROI accuracy.

For contest 196786696, the supplied payout schedule is scoped to that exact ID:
14,240 paid places, $5,000 total prizes. The public contest API did not return
usable JSON. Its 59.4K lobby capacity is therefore stored as a visibly approximate
59,400 fallback, with a contest-specific widget key; it is not asserted as an exact
capacity. Users can enter the exact capacity when known. Current registration
count 15,308 is not the full-capacity pregame field assumption.

Validation: `tests/test_showdown_field.py` covers unique Captain-aware identities,
exhaustion, legality, expansion support and concentration, lack of generated-CPT
feedback, and payout reconciliation. `docs/benchmarks/showdown-unique-field.json`
records the frozen-pool construction check. Full candidate/ROI calibration is not
part of that diagnostic.
