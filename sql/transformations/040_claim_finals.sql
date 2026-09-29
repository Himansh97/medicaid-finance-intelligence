-- Resolve each claim family to one active version, then decide what counts.
--
-- Order matters and is the whole point. Resolve the chain FIRST, then exclude
-- denied and voided outcomes. Filtering voids before resolution would leave the
-- paid version of a voided family standing as a live claim, which is how a
-- reversed payment survives into a spend total.
--
-- "Latest" means the highest version adjudicated on or before the run's cutoff.
-- A version adjudicated after the cutoff has not happened yet as far as this
-- release is concerned.

INSERT INTO fact_claim_header_final (
    run_id, claim_family_key, claim_version_key, member_key, market_key,
    plan_key, record_type, claim_file_type, service_month,
    header_paid_amount_cents, population_match
)
WITH through_cutoff AS (
    SELECT h.*
    FROM claim_header_version h
    JOIN pipeline_run pr ON pr.run_id = h.run_id
    WHERE h.run_id = :run_id
      AND h.adjudicated_at <= pr.as_of_cutoff
),
latest AS (
    SELECT claim_family_key, MAX(version_number) AS version_number
    FROM through_cutoff
    GROUP BY claim_family_key
),
resolved AS (
    SELECT t.*
    FROM through_cutoff t
    JOIN latest l
      ON l.claim_family_key = t.claim_family_key
     AND l.version_number = t.version_number
)
SELECT
    r.run_id,
    r.claim_family_key,
    r.claim_version_key,
    r.member_key,
    r.market_key,
    r.plan_key,
    r.record_type,
    r.claim_file_type,
    -- Service-end month. Every line inherits it; inpatient and long-term dollars
    -- are not spread across the days they span.
    substr(r.service_end_date, 1, 7) || '-01' AS service_month,
    r.header_paid_amount_cents,
    -- Whether the claim matched in-scope exposure. An unmatched claim keeps its
    -- dollars visible in the reconciliation bridge and out of KPI numerators,
    -- so the money is explained rather than silently dropped.
    CASE
        WHEN mm.member_key IS NULL THEN 'NO_EXPOSURE'
        WHEN mm.in_primary_cohort = 0 THEN 'OUT_OF_COHORT'
        WHEN mm.delivery_system <> CASE r.record_type
                                       WHEN 'FFS' THEN 'FFS'
                                       ELSE 'MANAGED_CARE' END THEN 'CONFLICTING_EXPOSURE'
        ELSE 'MATCHED'
    END
FROM resolved r
LEFT JOIN fact_member_month mm
       ON mm.run_id = r.run_id
      AND mm.member_key = r.member_key
      AND mm.month_start = substr(r.service_end_date, 1, 7) || '-01'
-- Denied and voided families are excluded only now, after the chain decided
-- which version speaks for the family.
WHERE r.status = 'ACCEPTED';

INSERT INTO fact_claim_line_final (
    run_id, claim_family_key, line_number, category_key,
    provider_key, line_paid_amount_cents
)
SELECT
    f.run_id,
    f.claim_family_key,
    l.line_number,
    l.category_key,
    l.provider_key,
    l.line_paid_amount_cents
FROM fact_claim_header_final f
JOIN claim_line_version l ON l.claim_version_key = f.claim_version_key
WHERE f.run_id = :run_id;
