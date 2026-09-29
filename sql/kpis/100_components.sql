-- KPI components. Exposure and claims are aggregated to the reporting grain
-- SEPARATELY here, before anything joins them.
--
-- That separation is the point. Joining claim lines to member months and then
-- summing membership repeats a member once per line, which inflates a
-- denominator in a way that looks plausible and reconciles to nothing. Every
-- view below reaches its grain by itself.
--
-- Views are dropped and recreated so applying this file is idempotent.

DROP VIEW IF EXISTS v_partition_status;
DROP VIEW IF EXISTS v_primary_exposure;
DROP VIEW IF EXISTS v_exposure_month;
DROP VIEW IF EXISTS v_ffs_spend_month;
DROP VIEW IF EXISTS v_ffs_claims_month;
DROP VIEW IF EXISTS v_ffs_category_month;
DROP VIEW IF EXISTS v_encounter_month;
DROP VIEW IF EXISTS v_capitation_month;

-- Whether a market-month may be reported at all.
--
-- This exists because a KPI view on its own cannot tell the difference between a
-- market that spent nothing and a market whose feed never arrived: both produce
-- no claim rows and both compute to zero. Publishing that zero is the specific
-- failure the business requirements call out, so availability travels beside
-- every measure rather than living only in the release gate.
--
-- A blocking failure scoped to the whole run ('ALL') makes every partition
-- unavailable, because a defect nobody has localised could be anywhere.
CREATE VIEW v_partition_status AS
SELECT
    m.market_key,
    d.month_start,
    r.run_id,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM dq_result g
            WHERE g.run_id = r.run_id AND g.market_id = 'ALL'
              AND g.severity = 'BLOCKING' AND g.disposition = 'FAIL')
        THEN 'UNAVAILABLE_RUN'
        WHEN EXISTS (
            SELECT 1 FROM dq_result p
            WHERE p.run_id = r.run_id AND p.market_id = m.market_id
              AND p.month_start = d.month_start
              AND p.severity = 'BLOCKING' AND p.disposition = 'FAIL')
        THEN 'UNAVAILABLE_PARTITION'
        ELSE 'AVAILABLE'
    END AS partition_status
FROM dim_market m
CROSS JOIN (SELECT DISTINCT month_start FROM dim_date) d
CROSS JOIN (SELECT DISTINCT run_id FROM pipeline_run) r;

-- The primary cohort: full-benefit Medicaid. The flag was computed once at
-- exposure build time so a later query cannot redefine the cohort by forgetting
-- a filter.
CREATE VIEW v_primary_exposure AS
SELECT run_id, member_key, month_start, market_key, plan_key,
       delivery_system, eligibility_group, member_month_weight, eligible_days
FROM fact_member_month
WHERE in_primary_cohort = 1;

-- K01 and K02 components. Member months are additive; distinct members are not,
-- which is why both are carried rather than one derived from the other.
CREATE VIEW v_exposure_month AS
SELECT
    run_id,
    month_start,
    market_key,
    delivery_system,
    SUM(member_month_weight) AS member_months,
    COUNT(DISTINCT member_key) AS distinct_members
FROM v_primary_exposure
GROUP BY run_id, month_start, market_key, delivery_system;

-- K04 component. Dollars come from lines, per the KPI dictionary, because the
-- header total is not a summable fact once category detail is in play.
--
-- A claim whose lines did not all resolve contributes no dollars here. Its
-- header still exists and DQ_LINE_UNMAPPED_SERVICE_CODE blocks the release, so
-- the gap is reported rather than published.
CREATE VIEW v_ffs_spend_month AS
SELECT
    f.run_id,
    f.service_month AS month_start,
    f.market_key,
    SUM(l.line_paid_amount_cents) AS paid_cents
FROM fact_claim_header_final f
JOIN fact_claim_line_final l
  ON l.run_id = f.run_id
 AND l.claim_family_key = f.claim_family_key
WHERE f.record_type = 'FFS'
  AND f.population_match = 'MATCHED'
GROUP BY f.run_id, f.service_month, f.market_key;

-- K06 component. Distinct claim families, so a two-line claim is one claim.
CREATE VIEW v_ffs_claims_month AS
SELECT
    run_id,
    service_month AS month_start,
    market_key,
    COUNT(DISTINCT claim_family_key) AS claim_count
FROM fact_claim_header_final
WHERE record_type = 'FFS'
  AND population_match = 'MATCHED'
GROUP BY run_id, service_month, market_key;

-- K09 component. Claim counts here are NOT additive across categories: a claim
-- with lines in two categories is counted under both, so summing the column
-- across categories double counts it. The column is named to say so.
CREATE VIEW v_ffs_category_month AS
SELECT
    f.run_id,
    f.service_month AS month_start,
    f.market_key,
    l.category_key,
    SUM(l.line_paid_amount_cents) AS category_paid_cents,
    COUNT(DISTINCT f.claim_family_key) AS claims_containing_category
FROM fact_claim_header_final f
JOIN fact_claim_line_final l
  ON l.run_id = f.run_id
 AND l.claim_family_key = f.claim_family_key
WHERE f.record_type = 'FFS'
  AND f.population_match = 'MATCHED'
GROUP BY f.run_id, f.service_month, f.market_key, l.category_key;

-- K10 component. Encounters describe utilisation only. No dollar column exists
-- here on purpose: an encounter amount is not spend, and a view that exposed one
-- would eventually be added to capitation by someone building a total.
CREATE VIEW v_encounter_month AS
SELECT
    run_id,
    service_month AS month_start,
    market_key,
    COUNT(DISTINCT claim_family_key) AS encounter_count
FROM fact_claim_header_final
WHERE record_type = 'ENCOUNTER'
  AND population_match = 'MATCHED'
GROUP BY run_id, service_month, market_key;

-- K11 component. Attributed to coverage month, not payment month, and signed so
-- corrections net against what they correct.
CREATE VIEW v_capitation_month AS
SELECT
    run_id,
    coverage_month AS month_start,
    market_key,
    SUM(signed_amount_cents) AS capitation_cents
FROM fact_capitation_transaction
GROUP BY run_id, coverage_month, market_key;
