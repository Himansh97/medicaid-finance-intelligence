# Data dictionary

**Version:** 0.1 · **Status:** logical design; names are project aliases, not official CMS field names

## CMS grounding and deliberate adaptations

T-MSIS is a state reporting system; TAF is its research-oriented transformation. The proposed portfolio model borrows subject areas and distinctions, not file layouts, official code sets, or certification requirements.

| CMS concept | Portfolio representation | Adaptation |
|---|---|---|
| TAF Demographic and Eligibility (DE) | Synthetic member, eligibility spans, member-month exposure | Monthly analytical fact derived from synthetic spans; no annual DE replica or real beneficiary identifiers |
| IP / LT / OT / RX claims | `claim_file_type` on header and related lines | Inpatient, long-term care, other services, pharmacy; file family is distinct from payment/record type |
| Claim headers and lines | Separate versioned headers and lines | Header identifies a claim family; lines support category dollars without duplicating header totals |
| Annual Provider (APR) and Annual Managed Care Plan (APL) | Fictional provider and plan dimensions | Simplified descriptive records rather than annual CMS extracts |
| FFS, encounters, capitation | Explicit `record_type` and separate capitation fact | Avoid treating all records as paid medical claims |
| Data-quality assessment | Versioned local rule results and release gates | Inspired by CMS's quality emphasis; local thresholds are not DQ Atlas scores |

CMS sources, consulted 2026-09-29:

- [TAF overview and technical guidance](https://www.medicaid.gov/medicaid/data-systems/macbis/medicaid-chip-research-files/transformed-medicaid-statistical-information-system-t-msis-analytic-files-taf): subject areas and links to official file documentation.
- [TAF data dictionaries and file families](https://www.medicaid.gov/medicaid/data-systems/medicaid-and-chip-business-information-solution/transformed-medicaid-statistical-information-system-t-msis/t-msis-analytic-files): official reference entry point. A future real-source adapter must pin the applicable release and exact element mappings.
- [CMS expenditure methodology brief 6081](https://www.medicaid.gov/dq-atlas/downloads/supplemental/6081-Measuring-TAF-Expenditures.pdf): state payments and provider-payment perspectives differ; encounter amounts require care. This project therefore separates financial bases and excludes encounter dollars from spend.
- [CMS encounter-data guidance](https://www.medicaid.gov/medicaid/managed-care/guidance/encounter-data): validation and completeness are essential to encounter usability.

The definitions below are original portfolio design choices. They must not be represented as CMS-prescribed KPIs.

## Conventions and shared fields

PK = unique primary key; FK = reference to another table. IDs are strings prefixed `SYN_`; warehouse surrogate keys may be integers. Dates use ISO YYYY-MM-DD; months are first-of-month dates; timestamps are UTC. USD amounts use DECIMAL(18,2), rates/ratios retain at least six decimal places. Raw fields can be missing to demonstrate failures; curated required fields cannot.

Every raw row carries `source_row_id` (PK within file), `source_file_id`, `source_system='synthetic'`, `ingested_at`, `scenario_id`, and `run_id`. Every curated fact retains source lineage plus `run_id` and `mapping_version`. All published rows carry `release_id`, `definition_version`, `as_of_timestamp`, and `quality_status`. A lineage bridge preserves multiple raw-row references when aggregation prevents direct row-level linkage.

Natural identifiers are scoped by `source_system` and `market_id`; never assume source member, provider, or claim IDs are globally unique. For this synthetic dataset, `member_key` represents one fictional person across months and markets; no cross-state identity inference is attempted.

## Dimensions

| Table / grain / PK | Required attributes | Rules |
|---|---|---|
| `dim_member`: one fictional person / `member_key` | `synthetic_member_id`, broad `age_band` | No direct identifiers, birth dates, or addresses; eligibility attributes live in exposure fact. |
| `dim_market`: one reporting region / `market_key` | `market_id`, `market_name`, `state_code` | Fictional labels; state code is descriptive, not evidence of real state data. |
| `dim_plan`: one fictional plan / `plan_key` | `market_key`, `plan_id`, `plan_name`, `plan_type` | Special FFS/not-applicable row; managed-care facts require an actual fictional plan. |
| `dim_provider`: one fictional provider / `provider_key` | `provider_id`, `provider_type` | No real NPI. Unknown permitted with warning when linkage is nonessential; no provider KPI certification. |
| `dim_service_category`: one category / `category_key` | `category_code`, `category_name` | Initial mutually exclusive categories: inpatient, institutional LT, outpatient, professional, pharmacy, other. OT is not synonymous with outpatient. |
| `dim_date`: one calendar day / `date_key` | `calendar_date`, `month_start`, `year`, `month_number`, `days_in_month` | Reused in service-end, payment, and coverage date roles. Calendar months; fiscal calendars deferred. |

A versioned category mapping uses `claim_file_type`, synthetic `service_code`, and effective dates. Each line maps to exactly one category. Unmapped lines block release; explicitly mapped “other” is valid and monitored. Descriptive dimensions are fixed for the initial scenario; any correction increments the mapping version and causes a new release. Full slowly changing dimensions are deferred.

## Eligibility and exposure

`eligibility_span` is one synthetic coverage interval per `eligibility_span_id` (PK): `member_key`, `market_key`, `plan_key`, `program` (MEDICAID or CHIP), `benefit_scope` (FULL or LIMITED), `eligibility_group` (CHILD, ADULT, AGED, DISABILITY), `delivery_system` (FFS or MANAGED_CARE), `start_date`, and `end_date`, all required. Endpoints are inclusive. Dates must be ordered. All codes are project enums, not CMS codes.

`fact_member_month` has PK (`member_key`, `month_start`) within a run. Required fields: market/plan keys, program, benefit scope, eligibility group, delivery system, `eligible_days` (integer 1 through calendar days), `member_month_weight` (1), and `in_primary_cohort` (boolean). Derive eligible days from interval unions. Same-assignment overlapping spans merge; conflicting assignments within a month block publication. No claim is required to create exposure.

## Claims and financial activity

| Entity / grain / PK | Fields and nullability | Meaning and constraints |
|---|---|---|
| `claim_header_version`: one submitted claim-family version / `claim_version_key` | Required `claim_family_key`, `version_number`, `member_key`, `market_key`, `plan_key`, `claim_file_type` (IP/LT/OT/RX), `record_type` (FFS/ENCOUNTER), `status` (ACCEPTED/DENIED/VOID), service start/end, `adjudicated_at`; optional `replaces_version_key` | Unique family/version; prior version must exist when replacement is asserted. Revision chains cannot branch or cycle. |
| Header financial fields | `header_medicaid_paid_amount` required for accepted FFS; nullable for encounters | Amount paid by Medicaid for covered FFS services, not billed or allowed charge. Nonnegative terminal amount; encounters may be NULL or zero without failing financial controls. |
| `claim_line_version`: one line of a header version / (`claim_version_key`, `line_number`) | Required `category_key`, synthetic `service_code`; optional `provider_key`, `units`; FFS requires `line_medicaid_paid_amount` | FFS lines sum to header dollars within $0.01. Units vary by service and are not summed into a universal utilization measure. |
| `fact_claim_header_final`: one resolved active claim family per run / `claim_family_key` | Selected `claim_version_key`, header fields, service month, population-match status | Select latest adjudicated version through cutoff, then exclude final denied/void families. Never filter voids before resolving the chain. |
| `fact_claim_line_final`: one line of selected final version / (`claim_family_key`, `line_number`) | Selected header FK, category/provider keys, paid amount | All lines inherit header service-end month and cohort assignment. Header totals are not repeated as summable line fields. |
| `fact_payment_transaction`: one FFS financial event / `payment_transaction_id` | Required family/version keys, `payment_date`, `signed_amount`, `event_type` (PAYMENT/REVERSAL); reversal references original transaction | Separate signed ledger for payment-month reporting. Replacement reverses previous balance and books replacement; void reverses previous payment. Not an official TAF transaction replica. |
| `fact_capitation_transaction`: one state-to-plan payment or correction / `capitation_transaction_id` | Required member/market/plan keys, `coverage_month`, `payment_date`, `signed_amount`; optional `reverses_transaction_id` | Managed-care coverage payments only. Corrections require linkage and reconciliation; duplicate payment IDs invalid. No service category or provider FK. |

Synthetic adjudication and payment events occur on the same date, so through-cutoff ledger balances reconcile to final FFS balances. Different dates and payable balances would require an explicit accounts-payable extension. A reversal must fully offset its referenced event; partial changes use full reversal plus replacement. Every accepted final claim must match in-scope exposure in its service-end month and delivery system for certified reporting. Out-of-cohort records remain in the reconciliation bridge but not in KPI numerators. In-cohort missing or conflicting exposure blocks release.

Example: family SYN_C1 version 1 pays $100; version 2 replaces it with $120. The ledger contains +$100, −$100, +$120. The final header is version 2 with one or more lines totaling $120. Its service-month spend is $120, its overall claim count is one, and payment-month activity follows each event's date.

## Operational and publication entities

| Entity / grain | Minimum fields |
|---|---|
| `pipeline_run`: one execution | run ID, seed/config hash, code version, source hashes, cutoff, start/end times, status |
| `dq_result`: one rule per partition/run | rule ID/version, severity, evaluated count, failing distinct-row count, financial impact, disposition |
| `quarantine_record`: one raw row and rule failure | source row/file IDs, rule ID, reason, run ID, remediation status; multiple failures allowed |
| `reconciliation_result`: one market/run/basis bridge | raw signed total, duplicates removed, corrections, exclusions by reason, unresolved amount, curated total, difference |
| `release_manifest`: one immutable release | run ID, definition/mapping/rule versions, expected and passed partitions, as-of cutoff, provisional months, approver, approval timestamp, status |
| `mart_finance_month`: month × market × plan × delivery system × eligibility group | FFS spend, FFS claim count, MM, encounter count, capitation amount; raw components retained |
| `mart_category_month`: same dimensions plus category | FFS category spend and distinct category claim count; denominator obtained separately from exposure mart |
| `variance_result` / `anomaly_result`: one KPI/cohort/month/release | current/prior or baseline, effects/score, threshold version, evaluated status, reason, review disposition |

Mart rows retain program/benefit scope or explicitly enforce the primary-cohort filter; neither scope may silently change between releases. Category claim counts are non-additive. Ratios are computed from components, not stored as additive facts. Exposure and claims must be aggregated separately before joins to prevent repeated membership per claim line.
