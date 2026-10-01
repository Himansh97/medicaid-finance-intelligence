-- Population and coverage rules.

-- An expected market-month feed that never arrived. This is the rule that makes
-- "unavailable" different from "zero". Without the expectation recorded in
-- expected_partition, a market that failed to send claims is indistinguishable
-- from a market with nothing to report, and a cross-market total would quietly
-- shrink instead of refusing to publish.
--
-- Evaluated per partition, so the failure names the market and the month.
-- Arrival is evidenced by the file, never by the rows inside it.
--
-- A market with a quiet month sends a file containing nothing. A market whose
-- feed failed sends no file at all. Counting rows cannot tell those apart, and
-- treating a quiet month as a missing feed would block a release that is
-- actually complete, while treating a missing feed as a quiet month would
-- publish a total that silently shrank. One row per expected partition.
INSERT INTO dq_result
SELECT
    ep.run_id, 'DQ_MISSING_MARKET_FEED', 'v1', ep.market_id, ep.month_start,
    'BLOCKING',
    COUNT(*),
    SUM(CASE WHEN sf.source_file_id IS NULL THEN 1 ELSE 0 END),
    NULL,
    CASE WHEN SUM(CASE WHEN sf.source_file_id IS NULL THEN 1 ELSE 0 END) > 0
         THEN 'FAIL' ELSE 'PASS' END
FROM expected_partition ep
LEFT JOIN source_file sf
  ON sf.run_id = ep.run_id
 AND sf.entity = ep.entity
 AND sf.market_id = ep.market_id
 AND sf.month_start = ep.month_start
WHERE ep.run_id = :run_id
GROUP BY ep.run_id, ep.market_id, ep.month_start;

-- A member holding two different assignments in one month. The exposure fact's
-- grain refuses these, so the transformation excludes them; this rule is what
-- makes the exclusion visible rather than a silently shorter denominator.
INSERT INTO dq_result
SELECT
    :run_id, 'DQ_MM_CONFLICTING_ASSIGNMENT', 'v1', 'ALL', 'ALL', 'BLOCKING',
    (SELECT COUNT(*) FROM eligibility_span WHERE run_id = :run_id),
    COALESCE((SELECT COUNT(*) FROM (
        SELECT e.member_key, d.month_start
        FROM eligibility_span e
        JOIN dim_date d ON d.calendar_date BETWEEN e.start_date AND e.end_date
        WHERE e.run_id = :run_id
        GROUP BY e.member_key, d.month_start
        HAVING COUNT(DISTINCT e.market_key || '|' || e.plan_key || '|' || e.program || '|'
                     || e.benefit_scope || '|' || e.eligibility_group || '|'
                     || e.delivery_system) > 1
    )), 0),
    NULL,
    CASE WHEN EXISTS (
        SELECT 1
        FROM eligibility_span e
        JOIN dim_date d ON d.calendar_date BETWEEN e.start_date AND e.end_date
        WHERE e.run_id = :run_id
        GROUP BY e.member_key, d.month_start
        HAVING COUNT(DISTINCT e.market_key || '|' || e.plan_key || '|' || e.program || '|'
                     || e.benefit_scope || '|' || e.eligibility_group || '|'
                     || e.delivery_system) > 1
    ) THEN 'FAIL' ELSE 'PASS' END;

-- An accepted claim with no matching exposure in its service month, or matching
-- exposure in a different market, plan or delivery system. These keep their dollars in the
-- bridge and stay out of KPI numerators. OUT_OF_COHORT is a valid exclusion,
-- not a failing row or quality impact. This rule explains a gap between
-- raw spend and reported spend rather than hiding one.
INSERT INTO dq_result
SELECT
    :run_id, 'DQ_CLAIM_POPULATION_MATCH', 'v3', 'ALL', 'ALL', 'BLOCKING',
    (SELECT COUNT(*) FROM fact_claim_header_final WHERE run_id = :run_id),
    (SELECT COUNT(*) FROM fact_claim_header_final
      WHERE run_id = :run_id AND population_match IN ('NO_EXPOSURE', 'CONFLICTING_EXPOSURE')),
    (SELECT COALESCE(SUM(header_paid_amount_cents), 0) FROM fact_claim_header_final
      WHERE run_id = :run_id AND population_match IN ('NO_EXPOSURE', 'CONFLICTING_EXPOSURE')),
    CASE WHEN EXISTS (
        SELECT 1 FROM fact_claim_header_final
        WHERE run_id = :run_id AND population_match IN ('NO_EXPOSURE', 'CONFLICTING_EXPOSURE')
    ) THEN 'FAIL' ELSE 'PASS' END;
