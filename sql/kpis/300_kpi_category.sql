-- K09, category spend share, and the category contribution to PMPM.
--
-- Shares reconcile to 100% only because the category map is disjoint: every line
-- maps to exactly one category, and an unmapped line blocks the release rather
-- than quietly leaving a share that sums to 97%.
--
-- The denominator removes only the category filter. Removing anything else would
-- compare a category in one market against a total across all of them.

DROP VIEW IF EXISTS v_kpi_ffs_category_month;

CREATE VIEW v_kpi_ffs_category_month AS
SELECT
    c.run_id,
    c.month_start,
    c.market_key,
    c.category_key,
    sc.category_code,
    t.partition_status,

    c.category_paid_cents,
    -- The denominator, carried so the share can be checked without re-querying.
    t.ffs_paid_cents AS market_month_paid_cents,

    -- K09. Undefined when total spend is zero: a share of nothing is not zero
    -- percent, it is a question with no answer.
    CASE WHEN t.ffs_paid_cents > 0
         THEN c.category_paid_cents * 100.0 / t.ffs_paid_cents
    END AS ffs_spend_share_pct,

    -- Category contribution to FFS PMPM. The denominator is the FULL matched FFS
    -- member months, not the members who used this category, which is why the
    -- KPI dictionary insists on that name: it is a contribution to the overall
    -- PMPM, not the PMPM of the people who received that service.
    t.member_months,
    CASE WHEN t.member_months > 0
         THEN c.category_paid_cents * 1.0 / t.member_months
    END AS category_contribution_to_pmpm_cents,

    -- Non-additive across categories: a claim with lines in two categories is
    -- counted under both. Summing this column double counts.
    c.claims_containing_category

FROM v_ffs_category_month c
JOIN dim_service_category sc ON sc.category_key = c.category_key
JOIN v_kpi_ffs_month t
  ON t.run_id = c.run_id
 AND t.month_start = c.month_start
 AND t.market_key = c.market_key;
