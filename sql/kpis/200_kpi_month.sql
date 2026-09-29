-- K01 to K08 at month by market, for the FFS primary cohort.
--
-- Every ratio is computed from summed components in this view. None is stored,
-- and none is an average of other ratios: averaging market PMPMs gives $200
-- where the correct answer is $250, which is acceptance example 2.
--
-- Every ratio returns NULL when its denominator is zero. Not zero, not infinity.
-- A PMPM of zero asserts that care was free; NULL says the question has no
-- answer, which is the truth when nobody was covered.
--
-- Numerator and denominator are exposed beside every rate so a reader can
-- reproduce the arithmetic without re-querying, and so a dashboard cannot show a
-- rate whose components it never received.

DROP VIEW IF EXISTS v_kpi_ffs_month;
DROP VIEW IF EXISTS v_kpi_managed_care_month;
DROP VIEW IF EXISTS v_kpi_period_membership;

CREATE VIEW v_kpi_ffs_month AS
SELECT
    e.run_id,
    e.month_start,
    e.market_key,

    -- Carried beside every measure, not left to the release gate. A consumer
    -- that reads a value without reading this will publish a zero for a market
    -- whose feed never arrived.
    ps.partition_status,

    -- K01, K02
    e.member_months,
    e.distinct_members,

    -- K04
    COALESCE(s.paid_cents, 0) AS ffs_paid_cents,

    -- K05 = K04 / K01
    CASE WHEN e.member_months > 0
         THEN COALESCE(s.paid_cents, 0) * 1.0 / e.member_months
    END AS ffs_pmpm_cents,

    -- K06
    COALESCE(c.claim_count, 0) AS ffs_claim_count,

    -- K07 = K06 / K01 * 1000
    CASE WHEN e.member_months > 0
         THEN COALESCE(c.claim_count, 0) * 1000.0 / e.member_months
    END AS ffs_claims_per_1000_mm,

    -- K08 = K04 / K06. Undefined with no claims, which is different from a
    -- claim that cost nothing.
    CASE WHEN COALESCE(c.claim_count, 0) > 0
         THEN COALESCE(s.paid_cents, 0) * 1.0 / c.claim_count
    END AS ffs_avg_claim_cost_cents

-- Driven from exposure. A market-month with covered members and no claims is a
-- real zero and must appear; a claim with no exposure is excluded upstream by
-- population_match and reported by DQ_CLAIM_POPULATION_MATCH rather than
-- silently widening a numerator.
FROM v_exposure_month e
LEFT JOIN v_ffs_spend_month s
       ON s.run_id = e.run_id
      AND s.month_start = e.month_start
      AND s.market_key = e.market_key
LEFT JOIN v_ffs_claims_month c
       ON c.run_id = e.run_id
      AND c.month_start = e.month_start
      AND c.market_key = e.market_key
JOIN v_partition_status ps
       ON ps.run_id = e.run_id
      AND ps.month_start = e.month_start
      AND ps.market_key = e.market_key
WHERE e.delivery_system = 'FFS';

-- K10 and K11. Kept in a separate view from FFS spend so that no query can
-- select both dollar columns and add them: capitation buys coverage, encounter
-- counts describe use, and neither is fee-for-service medical spend.
CREATE VIEW v_kpi_managed_care_month AS
SELECT
    e.run_id,
    e.month_start,
    e.market_key,
    ps.partition_status,
    e.member_months,
    e.distinct_members,

    -- K10
    COALESCE(n.encounter_count, 0) AS encounter_count,
    CASE WHEN e.member_months > 0
         THEN COALESCE(n.encounter_count, 0) * 1000.0 / e.member_months
    END AS encounters_per_1000_mm,

    -- K11
    COALESCE(p.capitation_cents, 0) AS capitation_cents,
    CASE WHEN e.member_months > 0
         THEN COALESCE(p.capitation_cents, 0) * 1.0 / e.member_months
    END AS capitation_pmpm_cents

FROM v_exposure_month e
LEFT JOIN v_encounter_month n
       ON n.run_id = e.run_id
      AND n.month_start = e.month_start
      AND n.market_key = e.market_key
LEFT JOIN v_capitation_month p
       ON p.run_id = e.run_id
      AND p.month_start = e.month_start
      AND p.market_key = e.market_key
JOIN v_partition_status ps
       ON ps.run_id = e.run_id
      AND ps.month_start = e.month_start
      AND ps.market_key = e.market_key
WHERE e.delivery_system = 'MANAGED_CARE';

-- K03, average monthly membership over a period.
--
-- The period here is every month the run holds. "Selected months" is a consumer
-- choice, so a narrower selection recomputes this rather than averaging the
-- column. months_expected comes from the calendar, not from the data: if a month
-- produced no exposure at all, dividing by the months that happened to appear
-- would quietly raise the average.
CREATE VIEW v_kpi_period_membership AS
SELECT
    e.run_id,
    e.market_key,
    e.delivery_system,
    SUM(e.member_months) AS total_member_months,
    COUNT(DISTINCT e.month_start) AS months_present,
    (SELECT COUNT(DISTINCT month_start) FROM dim_date) AS months_expected,
    CASE
        WHEN COUNT(DISTINCT e.month_start)
             < (SELECT COUNT(DISTINCT month_start) FROM dim_date)
        THEN NULL
        ELSE SUM(e.member_months) * 1.0 / COUNT(DISTINCT e.month_start)
    END AS average_monthly_membership
FROM v_exposure_month e
GROUP BY e.run_id, e.market_key, e.delivery_system;
