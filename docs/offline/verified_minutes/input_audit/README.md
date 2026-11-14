# Eligibility and short-handed audit — development evidence only

## Findings

The six saved dates / 12 builds contain 2,134 available player snapshots. Official dated NBA lineup feeds matched 2,118 names/team pairs: 1,875 Active, 243 Inactive, and 16 without a matching row. These are recovered source labels, not certified eligibility at the original capture. Official row timestamps lack an offset, and historical publication validity / rosterStatus semantics have not been established. The full quantitative independent role prior is also not present. No combined accuracy backtest can yet satisfy the verified-input contract.

259 snapshots lack explicit actual minutes; none were zero-filled. Original archived flags recovered 5,392 positive played history records, 1,108 explicit DNPs and 11 zero-minute rows without confirmed DNP. Those 11 require unknown classification. No raw rows were missing from the audit.

Cormac Ryan and Kam Jones have four preseason history observations each and no verified regular-season history in this archive. Their recovered official dated rows say Inactive on each of the four saved dates where MIL appears; timezone / capture-time verification remains outstanding. Missing actuals alone do not justify those labels or removing them retrospectively. Source URL, retrieval timestamp and source row timestamp are preserved in stale_player_cases.csv.

With zero regular-season observations, age-shrinkage returns exactly its supplied current role prior. Sensitivity inputs 4/12/24/32 produce exactly those respective raw estimates, at capture and after 14/28/56 further days without evidence. This is a mathematical diagnostic, not fitted forecasts. Shrinkage cannot rescue an inflated or unsupported prior. It does not assign zero just because logs are missing.

The 144 team snapshots contain only two 2+ historical-core-OUT snapshots: DK and FD versions of the same Nov 6 CHA game. Moussa Diabate and Dennis Schroder were the saved historical-core-OUT names. This is one team-game, not two independent injury-heavy validation cases; historical-core classification is not verified starting-five status.

## Conflict policy implemented in prototype

* Normal and injury-promoted roles use separate earlier role-labelled training subsets. Training labels require a source and timezone-aware publication time before the corresponding game; a verification boolean alone is rejected. Promotion context requires sourced, dated role evidence, not an actual-minute jump or hindsight.
* A promoted role with insufficient matching earlier samples reports insufficient support; normal-rotation bounds are not substituted. Minimum 20 records remains an experimental fixed support requirement.
* Allocation conflicts expose lower-sum excess / upper-sum shortfall against 240. No learned bounds are silently widened, no 38-minute cap is introduced, and unknown players are not silently excluded.
* A deterministic six-player promoted-rotation test demonstrates legitimate 40-minute allocations can fill 240 even when normal bounds cannot. This is a mechanics test, not evidence that the learned production parameters are accurate.

93 targeted tests pass, including historical isolation, shrinkage, unknown participation, promotion-context separation, quantified infeasibility and 240-minute conservation. Live Simmah and PR #77 are unchanged.

## Still required

Verify historical source-time / status semantics; recover or generate independent point-in-time current-role priors; expand verified injury-promotion training beyond one team-game; then run fixed chronological ablations and retain unsupported snapshots in coverage reporting. Do not use retrospective Inactive labels as pregame evidence or evaluate only the surviving easy cases. No promotion claim.
