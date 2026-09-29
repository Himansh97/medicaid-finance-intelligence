-- Financial rules. Tolerance is one cent, matching the documented $0.01.
--
-- Amounts are integer cents, so "within a cent" is an exact integer comparison
-- rather than a float epsilon. That is the reason for the storage choice.

-- FFS header dollars must equal the sum of their lines.
--
-- Headers carrying an unmapped line are excluded, because their lines did not
-- all resolve and the imbalance would be a consequence of
-- DQ_LINE_UNMAPPED_SERVICE_CODE rather than an independent finding. One root
-- cause should raise one rule.
INSERT INTO dq_result
SELECT
    :run_id, 'DQ_HEADER_LINE_BALANCE', 'v1', 'ALL', 'ALL', 'BLOCKING',
    (SELECT COUNT(*) FROM claim_header_version
      WHERE run_id = :run_id AND record_type = 'FFS' AND status = 'ACCEPTED'),
    COALESCE((SELECT COUNT(*) FROM (
        SELECT h.claim_version_key
        FROM claim_header_version h
        WHERE h.run_id = :run_id AND h.record_type = 'FFS' AND h.status = 'ACCEPTED'
          AND NOT EXISTS (
              SELECT 1 FROM raw_claim_line rl
               WHERE rl.claim_family_id = h.claim_family_key
                 AND rl.version_number = h.version_number
                 AND rl.run_id = h.run_id
                 AND NOT EXISTS (
                     SELECT 1 FROM service_category_map m
                      WHERE m.mapping_version = :mapping_version
                        AND m.claim_file_type = h.claim_file_type
                        AND m.service_code = rl.service_code))
          AND ABS(h.header_paid_amount_cents - COALESCE((
                SELECT SUM(l.line_paid_amount_cents) FROM claim_line_version l
                 WHERE l.claim_version_key = h.claim_version_key), 0)) > 1
    )), 0),
    NULL,
    CASE WHEN EXISTS (
        SELECT 1 FROM claim_header_version h
        WHERE h.run_id = :run_id AND h.record_type = 'FFS' AND h.status = 'ACCEPTED'
          AND NOT EXISTS (
              SELECT 1 FROM raw_claim_line rl
               WHERE rl.claim_family_id = h.claim_family_key
                 AND rl.version_number = h.version_number
                 AND rl.run_id = h.run_id
                 AND NOT EXISTS (
                     SELECT 1 FROM service_category_map m
                      WHERE m.mapping_version = :mapping_version
                        AND m.claim_file_type = h.claim_file_type
                        AND m.service_code = rl.service_code))
          AND ABS(h.header_paid_amount_cents - COALESCE((
                SELECT SUM(l.line_paid_amount_cents) FROM claim_line_version l
                 WHERE l.claim_version_key = h.claim_version_key), 0)) > 1
    ) THEN 'FAIL' ELSE 'PASS' END;

-- The signed ledger, summed per family through the cutoff, must equal that
-- family's final claim balance. A resolved-away family (denied, voided) has no
-- final row and must net to zero: the reversal has to be there, not merely the
-- absence of a claim.
--
-- Adjudication and payment coincide in this fixture, so this reconciles without
-- an accounts-payable model. Different dates would require one.
INSERT INTO dq_result
SELECT
    :run_id, 'DQ_LEDGER_RECONCILES_TO_CLAIMS', 'v1', 'ALL', 'ALL', 'BLOCKING',
    (SELECT COUNT(DISTINCT claim_family_key) FROM fact_payment_transaction
      WHERE run_id = :run_id),
    COALESCE((SELECT COUNT(*) FROM (
        SELECT p.claim_family_key,
               SUM(p.signed_amount_cents) AS ledger,
               COALESCE((SELECT f.header_paid_amount_cents
                           FROM fact_claim_header_final f
                          WHERE f.run_id = p.run_id
                            AND f.claim_family_key = p.claim_family_key), 0) AS final_balance
        FROM fact_payment_transaction p
        JOIN pipeline_run pr ON pr.run_id = p.run_id
        WHERE p.run_id = :run_id AND p.payment_date <= pr.as_of_cutoff
        GROUP BY p.claim_family_key
        HAVING ABS(ledger - final_balance) > 1
    )), 0),
    NULL,
    CASE WHEN EXISTS (
        SELECT 1 FROM (
            SELECT p.claim_family_key,
                   SUM(p.signed_amount_cents) AS ledger,
                   COALESCE((SELECT f.header_paid_amount_cents
                               FROM fact_claim_header_final f
                              WHERE f.run_id = p.run_id
                                AND f.claim_family_key = p.claim_family_key), 0) AS final_balance
            FROM fact_payment_transaction p
            JOIN pipeline_run pr ON pr.run_id = p.run_id
            WHERE p.run_id = :run_id AND p.payment_date <= pr.as_of_cutoff
            GROUP BY p.claim_family_key
            HAVING ABS(ledger - final_balance) > 1
        )
    ) THEN 'FAIL' ELSE 'PASS' END;

-- A negative capitation row that references nothing. A correction is linked to
-- what it corrects; an unlinked negative is a defect, and the schema already
-- refuses it, so a failure here means something bypassed the curated insert.
INSERT INTO dq_result
SELECT
    :run_id, 'DQ_CAPITATION_CORRECTION_LINKED', 'v1', 'ALL', 'ALL', 'BLOCKING',
    (SELECT COUNT(*) FROM raw_capitation_transaction WHERE run_id = :run_id),
    (SELECT COUNT(*) FROM raw_capitation_transaction
      WHERE run_id = :run_id
        AND signed_amount_cents < 0
        AND reverses_transaction_id IS NULL),
    NULL,
    CASE WHEN EXISTS (
        SELECT 1 FROM raw_capitation_transaction
        WHERE run_id = :run_id AND signed_amount_cents < 0
          AND reverses_transaction_id IS NULL
    ) THEN 'FAIL' ELSE 'PASS' END;
