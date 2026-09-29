# KPI dictionary

**Version:** 0.1 · **Status:** design contract; no measures implemented

## Common rules

PMPM means per member per month: divide eligible dollars by the matching population's member months. It answers cost per unit of covered exposure, not cost per claimant.

Primary cohort: synthetic full-benefit Medicaid members; exclude separate CHIP and limited-benefit coverage. Apply identical market, coverage, and delivery-system filters to numerators and denominators. A month with confirmed complete input and no activity is zero; a missing or failed input is unavailable.

A **member month (MM)** is 1 for any eligible day during the calendar month, including members with no claims. This is an explicit portfolio convention; it is not prorated exposure. Deduplicate overlapping eligibility spans into a union of covered days. One primary market, plan, and delivery system per member-month is required; conflicting assignments block publication. The FFS population uses a designated FFS/not-applicable plan key. Distinct monthly members equal member months at monthly total grain; across months, summed MM differs from distinct people.

Primary time basis: claim header service-end month. All lines inherit that month; do not spread inpatient/LT dollars across days. Paid amounts mean final adjudicated amounts known by the release cutoff. Paid-month reporting uses the signed transaction ledger by payment date, including adjustments. Never mix those bases in one series. Use only accepted, non-denied, non-void final claim versions for service-month measures; zero-dollar accepted claims may contribute utilization. Negative adjustments belong to the ledger, not negative terminal claim balances.

Default slicing: month, market, delivery system, plan, and eligibility group. Provider and service-category filters apply to claim measures only; they must not remove members with no claims from denominators. No provider-level PMPM is certified in this MVP. Category PMPM uses the full matched FFS MM denominator and is labeled “category contribution to FFS PMPM.”

## Definitions

| ID / measure | Formula and grain | Eligibility and interpretation |
|---|---|---|
| K01 Member months | SUM(member_month_weight); member-month fact | Weight = 1 in primary cohort; separately report FFS and managed care. Additive across months and disjoint markets. |
| K02 Monthly membership | COUNT(DISTINCT member_key) in month | Any-day enrolled membership, not end-of-month enrollment. Multi-month distinct members must be recalculated, never summed. |
| K03 Average monthly membership | Total MM / number of selected calendar months | Includes complete zero-enrollment months. Unavailable if any selected month is missing. |
| K04 FFS medical paid amount | SUM(final line Medicaid paid amount); final FFS service lines | Includes only accepted FFS claims matched to the member's FFS service month. Excludes billed/allowed amounts, encounters, capitation, supplemental payments, rebates, and administration. |
| K05 FFS medical PMPM | K04 / FFS K01 | USD/member-month. Portfolio observed-paid metric, not incurred cost or all-program Medicaid PMPM. |
| K06 FFS claim count | COUNT(DISTINCT claim_family_key); accepted final FFS headers | Header count, not line count, admissions, visits, or unique patients. Under a category filter, count claims containing that category; category counts may overlap. |
| K07 FFS claims per 1,000 MM | K06 / FFS K01 × 1,000 | Utilization proxy. For multi-month periods, ratio of sums; no extra annualization. |
| K08 Average FFS claim cost | K04 / K06 | USD/claim. Category version uses category dollars and distinct claims with that category; not an admission cost. |
| K09 FFS spend share | Category K04 / total K04 within selected non-category filters × 100 | A disjoint line category map makes shares reconcile. Undefined when total spend is zero. Market share similarly removes only the market filter. |
| K10 Managed-care encounter count/rate | Distinct accepted final encounter families; count / managed-care MM × 1,000 | Service-use proxy only. Zero or missing encounter dollars do not make a valid encounter invalid. No capitation records count as encounters. |
| K11 State-to-plan capitation / PMPM | SUM(signed capitation amount attributed to coverage month); amount / managed-care MM | Separate coverage-payment measure. Include validated adjustments through cutoff. No allocation to service categories; not provider medical spend. |
| K12 Payment-month FFS net payments | SUM(signed FFS transaction amount) by payment month | Cash-activity proxy from the synthetic ledger. No PMPM by default and no claim of reconciliation to a real GL. |
| K13 Month-over-month variance | Current − prior; percentage = (current − prior) / prior × 100 | Same KPI, cohort, basis, and definition version; consecutive calendar months. Missing prior = unavailable. Prior = 0: percentage unavailable, with “new activity” if current > 0. |
| K14 Quality failure rate | Distinct failing raw rows / total raw rows × 100 | Count each row once even if several rules fail. Show rule counts separately; never confuse these with excluded financial dollars. Empty input = unavailable. |

All zero-denominator ratios are NULL/unavailable, never infinity or zero. Display the numerator and denominator beside rates. Recompute aggregate ratios from base sums; never average market PMPMs or sum percentages. Negative capitation corrections and paid-month net payments are permitted when linked to prior payments and reconciled; negative/zero baselines have no percentage-change interpretation and display absolute variance only.

## Spend variance bridge

For comparable FFS months, let M be member months, P be PMPM, and S = M × P. With prior = 0 and current = 1 as subscripts:

- Membership effect = (M₁ − M₀) × P₀.
- PMPM effect = M₁ × (P₁ − P₀).
- Their sum equals S₁ − S₀; this ordering assigns the interaction to PMPM.

Example: prior 1,000 MM and $200,000 spend means $200 PMPM; current 1,100 MM and $231,000 means $210 PMPM. Spend rises $31,000: $20,000 membership effect plus $11,000 PMPM effect. PMPM rises 5%; spend rises 15.5%. If either denominator is zero, skip the bridge and show absolute spend change.

Market and category contributions use current minus prior spend at disjoint grains and sum to total variance. A contribution percentage is unavailable if total variance is zero and can exceed 100% when effects offset. These are arithmetic explanations, not causal findings. No budget variance exists until a separately governed budget source is designed.

## Review flags and later anomaly analysis

Proposed deterministic materiality flag: absolute FFS spend change at least $10,000 **and** absolute percentage change at least 10%, with positive prior spend. New activity from a zero baseline is flagged separately if current spend is at least $10,000. Thresholds are configurable portfolio assumptions.

A later statistical candidate rule may compare monthly PMPM against the immediately preceding 12 certified consecutive service months for the same cohort. Proposed score: 0.6745 × (current − median) / MAD, where MAD is median absolute deviation.

A candidate requires **both** conditions, not either one:

1. Absolute score > 3.5.
2. Estimated financial impact ≥ $10,000, where impact = |current PMPM − historical median PMPM| × current member months.

The second condition exists because the score measures distance in units of historical dispersion, and a quiet history makes that unit small. Where MAD is $0.05, a move of $0.26 PMPM scores above 3.5, which on a $200 PMPM is a 0.13% change and not worth a finance analyst's attention. Measuring impact against the same median the score uses keeps the two conditions on one baseline. The $10,000 figure is a proposed portfolio setting to be tested against real generated histories, not an established Medicaid standard, and it is deliberately the same figure the deterministic materiality flag uses so the two can be compared and tuned together.

Additional gates: current MM ≥ 100, and complete comparable history. Missing history, MAD = 0, or a definition change produces “not evaluated”; do not divide by zero or manufacture a baseline. No seasonal adjustment or predictive accuracy is claimed.

**Comparison-ready months only.** Statistical detection applies to months finance has marked comparison-ready. A provisional month is not eligible, because incomplete claims development produces movement that is real in the data and misleading as a finding. Passing every data-quality check does not mean claims are fully developed; the checks test whether records are internally consistent, not whether the period has finished paying.

Provisional months instead receive a separately labeled **preliminary movement advisory**, which is not an anomaly flag. It carries the as-of cutoff, the provisional status, the observed movement, and a statement that the period remains subject to claims development. It never produces a statistical score, never enters anomaly counts, and must not be presented in the same visual component as a comparison-ready flag. This keeps recent months visible to finance without lending them a confidence the underlying data does not support.

This rule is documented only, not implemented.

## Acceptance examples for later implementation

1. $10,000 FFS spend / 100 FFS MM = $100 PMPM, even if only 20 members have claims.
2. Markets with $10,000/100 MM and $90,000/300 MM combine to $250 PMPM, not $200.
3. A $100 claim replaced by a $120 claim contributes $120 and one claim; ledger entries +100, −100, +120 reconcile to $120.
4. Two lines of $70 and $50 in different categories contribute $120 total and one claim overall; category claim counts are non-additive.
5. $50,000 capitation plus $40,000 encounter amounts produces $50,000 capitation, not $90,000 spend; encounters still contribute utilization.
6. A member eligible for one day contributes 1 MM; duplicate spans do not create a second MM.
7. A failed market feed makes the selected all-market total unavailable, rather than shrinking spend silently.
8. A quiet history of twelve months alternating $199.95 and $200.05 PMPM has median $200.00 and MAD $0.05. A current month of $200.40 on 1,000 MM scores 5.4 and carries $400 of impact. No candidate: the score condition passes and the materiality condition fails, which is the case this rule exists to suppress.
9. The same quiet history with a current month of $215.00 on 1,000 MM scores 202.3 and carries $15,000 of impact. Candidate raised: both conditions pass.
10. A provisional month showing a large movement produces a preliminary movement advisory carrying its cutoff and provisional status, and produces no statistical score and no anomaly flag, even when every data-quality rule for that month passes.

These examples specify future tests. They have not been run against a database. Examples 8 and 9 exist to test the rule against a deliberately quiet history in both directions; example 10 tests an incomplete period. Test all three before any alert reaches a dashboard.
