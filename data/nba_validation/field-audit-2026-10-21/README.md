# October 21, 2026 NBA field-structure audit

Retrospective descriptive audit completed October 22. No live settings, projections, scoring or field-generation code changed. No predictive improvement or ROI claim.

## Sources and denominators
Source SHA-256 identities appear in source-manifest.json. Hashes establish file identity, not pre-lock timing. DK contest 196983215 has 2,972 entries, 2,970 complete rosters and two blanks excluded. Saved DK fields each represent 2,971 entries using Copies. FD has 69,542 entries, 69,510 complete rosters; saved field represents 86,227 modeled entries. Comparisons include the user's entries, not exclusively opponents. Different entry counts affect duplication comparisons.

All complete contest lineup scores reconcile to supplied player FPTS. Player identities match saved pools. Original FanDuel salary upload confirms the four checked team assignments. These checks do not certify the entire ingestion pipeline.

## Salary and ownership
DK exact-cap frequency actual/earlier/later: 47.27/72.84/13.67%. Later modeled field leaves over $2,000 unused in 16.69% of entries versus 0.13% actual. Salary quantiles use entry-weighted inverse empirical CDF, without interpolation.

DK Garland ownership actual/earlier/later: 37.95/10.97/7.07%; Young: 8.08/9.93/8.31%. The miss is player- and site-specific.

FD exact-cap actual/model: 46.23/70.20%. Uniform weighting of 7,627 retained unique rosters gives 86.48%; applying current relative-popularity strength 0.5 on retained support gives 69.89%. This reconstruction excludes unexported zero-copy support and does not prove the historical settings.

FD actual/model ownership: Zubac 40.77/7.88%; Isaiah Jackson 42.55/18.03%; Garland 35.40/15.24%; Jerome 26.28/3.19%; Lendeborg 33.39/1.68%. Eligible raw RotoWire values total 1,426.2%. Hypothetically normalizing to 900% implies $57,387 average salary versus $59,860 actual. Live fallback weights legal rosters by relative popularity; it does not simply normalize player percentages.

## Pair associations
dk-top15-pairs.csv contains all 105 pairs selected by actual DK ownership, with entry-weighted marginals, joint frequency and joint-minus-marginal-product residuals in percentage points. Earlier field underrepresents 101/105 pairs, later 105/105. Example actual/earlier/later residuals: Schroder-Davis +6.90/-0.25/+0.21; Davis-Jerome +5.30/-0.23/-0.36.

Residuals describe associations, not controls for salary, eligibility, differing marginals or finite-sample effects. This retrospective top-15 selection does not validate predictions or prove slot-order bias.

## Limits
Original build settings, seeds, source fetch times and commit provenance were not preserved in exports. The exact field used to rank final entries is unverified. Upload times are not provider fetch times. Snapshot already records Beal/Ingram OUT and Jackson expected to start; those known absences cannot simply be blamed on missing later news. Other late effects remain unverified.

Original evaluation scenarios are unavailable. FD has 5,000 saved candidates; a complete matching DK package is unavailable. Contest files lack actual minutes. Regenerated scenarios are retrospective, not replacements for original frozen outcomes. The historical January 2025 minutes pilot is not current-engine validation.

Ownership matching requires explicit, separately labeled reweighting with feasibility/residual checks. Slot permutations can differ without changing roster composition. No hindsight factors or settings are promoted.

## Reproduction and next test
Run: python reproduce.py SOURCE_UPLOAD_DIRECTORY OUTPUT_DIRECTORY
Requires the named source files; generates the pair table, quantiles and manifest. Original user contest files are not duplicated here. README FD summaries document the separately computed descriptive audit; reproduce.py regenerates the DK tables only.

Future builds should save effective settings, independent seeds, input hashes/fetch times, code commit and snapshot time. Preserve 10,000 scenarios and 5,000 candidates. Prospective comparisons must freeze before lock and keep candidate/scenario inputs identical.
