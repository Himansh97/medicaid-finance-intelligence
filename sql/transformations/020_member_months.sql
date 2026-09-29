-- Spans become the member-month exposure fact.
--
-- Covered days are counted as a union across spans, not summed, so two
-- overlapping spans for the same member cannot produce more days than the month
-- holds. The weight is 1 regardless: a member eligible for one day contributes a
-- whole member month under the documented any-day convention. eligible_days is
-- kept anyway so prorated exposure can be measured later without rebuilding.
--
-- A member holding two different assignments in one month is excluded here and
-- reported by DQ_MM_CONFLICTING_ASSIGNMENT. Inserting them would violate the
-- grain and abort the run, which would be correct but unreadable; excluding and
-- reporting names the member and the month.

INSERT INTO fact_member_month (
    run_id, member_key, month_start, market_key, plan_key,
    program, benefit_scope, eligibility_group, delivery_system,
    eligible_days, member_month_weight, in_primary_cohort
)
WITH covered AS (
    SELECT
        e.run_id,
        e.member_key,
        d.month_start,
        e.market_key,
        e.plan_key,
        e.program,
        e.benefit_scope,
        e.eligibility_group,
        e.delivery_system,
        d.calendar_date
    FROM eligibility_span e
    JOIN dim_date d
      ON d.calendar_date BETWEEN e.start_date AND e.end_date
    WHERE e.run_id = :run_id
),
conflicted AS (
    -- More than one assignment for one member in one month. Counted over the
    -- whole attribute set, because a market change and a benefit-scope change
    -- are the same class of problem.
    SELECT run_id, member_key, month_start
    FROM covered
    GROUP BY run_id, member_key, month_start
    HAVING COUNT(DISTINCT market_key || '|' || plan_key || '|' || program || '|'
                 || benefit_scope || '|' || eligibility_group || '|' || delivery_system) > 1
)
SELECT
    c.run_id,
    c.member_key,
    c.month_start,
    c.market_key,
    c.plan_key,
    c.program,
    c.benefit_scope,
    c.eligibility_group,
    c.delivery_system,
    COUNT(DISTINCT c.calendar_date),
    1,
    CASE WHEN c.program = 'MEDICAID' AND c.benefit_scope = 'FULL' THEN 1 ELSE 0 END
FROM covered c
WHERE NOT EXISTS (
    SELECT 1 FROM conflicted x
    WHERE x.run_id = c.run_id
      AND x.member_key = c.member_key
      AND x.month_start = c.month_start
)
GROUP BY c.run_id, c.member_key, c.month_start, c.market_key, c.plan_key,
         c.program, c.benefit_scope, c.eligibility_group, c.delivery_system;
