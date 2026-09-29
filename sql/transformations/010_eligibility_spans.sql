-- Raw eligibility spans become curated spans.
--
-- Deduplication is by business key, not by row. The fixture lands SYN_ELG_001
-- twice under two different source_row_ids, so a rule keyed on the row would see
-- two legitimate rows and a member would gain a second span. Keeping the lowest
-- source_row_id makes the choice deterministic rather than whichever the engine
-- happened to read first.
--
-- A raw row whose member, market or plan does not resolve is dropped by these
-- joins rather than failing the load. That is deliberate: the orphan is caught
-- and reported by DQ_ELIG_UNRESOLVED_REFERENCE, which can name it, where a
-- foreign-key violation here would only abort the run.

INSERT INTO eligibility_span (
    eligibility_span_id, run_id, member_key, market_key, plan_key,
    program, benefit_scope, eligibility_group, delivery_system,
    start_date, end_date, source_file_id, source_row_id
)
SELECT
    r.eligibility_span_id,
    r.run_id,
    m.member_key,
    mk.market_key,
    p.plan_key,
    r.program,
    r.benefit_scope,
    r.eligibility_group,
    r.delivery_system,
    r.start_date,
    r.end_date,
    r.source_file_id,
    r.source_row_id
FROM raw_eligibility_span r
JOIN dim_member m  ON m.synthetic_member_id = r.member_id
JOIN dim_market mk ON mk.market_id = r.market_id
JOIN dim_plan p    ON p.plan_id = r.plan_id AND p.market_key = mk.market_key
WHERE r.run_id = :run_id
  AND r.source_row_id = (
        SELECT MIN(d.source_row_id)
        FROM raw_eligibility_span d
        WHERE d.eligibility_span_id = r.eligibility_span_id
          AND d.run_id = r.run_id
  );
