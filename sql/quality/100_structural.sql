-- Structural rules. Each writes one dq_result row per evaluated partition.
--
-- Rules never read expected_defect. A rule that consults the answer key proves
-- only that the key was readable. Tests compare the two afterwards.
--
-- market_id and month_start carry 'ALL' rather than NULL for rules evaluated
-- across the whole run, because SQLite does not treat NULLs as equal in a
-- primary key and two such rows would not conflict.

-- Duplicate eligibility business keys. Keyed on the business key, not the source
-- row: the fixture lands the same span twice under two row ids, which a
-- row-level rule cannot see.
INSERT INTO dq_result
SELECT
    :run_id, 'DQ_ELIG_DUPLICATE_KEY', 'v1', 'ALL', 'ALL', 'BLOCKING',
    (SELECT COUNT(*) FROM raw_eligibility_span WHERE run_id = :run_id),
    COALESCE((
        SELECT SUM(extra) FROM (
            SELECT COUNT(*) - 1 AS extra
            FROM raw_eligibility_span
            WHERE run_id = :run_id
            GROUP BY eligibility_span_id
            HAVING COUNT(*) > 1
        )
    ), 0),
    NULL,
    CASE WHEN EXISTS (
        SELECT 1 FROM raw_eligibility_span WHERE run_id = :run_id
        GROUP BY eligibility_span_id HAVING COUNT(*) > 1
    ) THEN 'FAIL' ELSE 'PASS' END;

-- A raw eligibility row whose member, market or plan does not resolve. These are
-- dropped by the transformation joins, so without this rule they would vanish.
INSERT INTO dq_result
SELECT
    :run_id, 'DQ_ELIG_UNRESOLVED_REFERENCE', 'v1', 'ALL', 'ALL', 'BLOCKING',
    (SELECT COUNT(*) FROM raw_eligibility_span WHERE run_id = :run_id),
    (SELECT COUNT(*) FROM raw_eligibility_span r
      WHERE r.run_id = :run_id
        AND (NOT EXISTS (SELECT 1 FROM dim_member m WHERE m.synthetic_member_id = r.member_id)
          OR NOT EXISTS (SELECT 1 FROM dim_market k WHERE k.market_id = r.market_id)
          OR NOT EXISTS (SELECT 1 FROM dim_plan p JOIN dim_market k2 ON k2.market_key = p.market_key
                          WHERE p.plan_id = r.plan_id AND k2.market_id = r.market_id))),
    NULL,
    CASE WHEN EXISTS (
        SELECT 1 FROM raw_eligibility_span r
        WHERE r.run_id = :run_id
          AND (NOT EXISTS (SELECT 1 FROM dim_member m WHERE m.synthetic_member_id = r.member_id)
            OR NOT EXISTS (SELECT 1 FROM dim_market k WHERE k.market_id = r.market_id))
    ) THEN 'FAIL' ELSE 'PASS' END;

-- A claim line whose service code is absent from the category map. Unmapped
-- lines block the release: an explicitly mapped 'OTHER' is a decision, while an
-- unmapped code is a gap, and a spend share that silently omits a line does not
-- reconcile to 100%.
INSERT INTO dq_result
SELECT
    :run_id, 'DQ_LINE_UNMAPPED_SERVICE_CODE', 'v1', 'ALL', 'ALL', 'BLOCKING',
    (SELECT COUNT(*) FROM raw_claim_line WHERE run_id = :run_id),
    (SELECT COUNT(*) FROM raw_claim_line r
       JOIN raw_claim_header h
         ON h.claim_family_id = r.claim_family_id
        AND h.version_number = r.version_number
        AND h.run_id = r.run_id
      WHERE r.run_id = :run_id
        AND NOT EXISTS (
            SELECT 1 FROM service_category_map m
            WHERE m.mapping_version = :mapping_version
              AND m.claim_file_type = h.claim_file_type
              AND m.service_code = r.service_code)),
    -- The dollars that would go uncategorised. Reported because a structural
    -- failure with a financial consequence should state the consequence.
    (SELECT COALESCE(SUM(r.line_paid_amount_cents), 0) FROM raw_claim_line r
       JOIN raw_claim_header h
         ON h.claim_family_id = r.claim_family_id
        AND h.version_number = r.version_number
        AND h.run_id = r.run_id
      WHERE r.run_id = :run_id
        AND NOT EXISTS (
            SELECT 1 FROM service_category_map m
            WHERE m.mapping_version = :mapping_version
              AND m.claim_file_type = h.claim_file_type
              AND m.service_code = r.service_code)),
    CASE WHEN EXISTS (
        SELECT 1 FROM raw_claim_line r
          JOIN raw_claim_header h
            ON h.claim_family_id = r.claim_family_id
           AND h.version_number = r.version_number
           AND h.run_id = r.run_id
         WHERE r.run_id = :run_id
           AND NOT EXISTS (
               SELECT 1 FROM service_category_map m
               WHERE m.mapping_version = :mapping_version
                 AND m.claim_file_type = h.claim_file_type
                 AND m.service_code = r.service_code)
    ) THEN 'FAIL' ELSE 'PASS' END;
