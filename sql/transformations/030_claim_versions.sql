-- Raw claim rows become versioned headers and lines.
--
-- Every submitted version is kept, including ones later superseded or voided.
-- The payment ledger references versions that are no longer current, and a
-- reconciliation that cannot see a reversed version cannot explain the reversal.
--
-- Surrogate keys are assigned by ordering on (family, version) so the same input
-- produces the same keys on every run. replaces_version_key is resolved in a
-- second pass, because it points at a key this statement is still assigning.

INSERT INTO claim_header_version (
    claim_version_key, run_id, claim_family_key, version_number,
    replaces_version_key, member_key, market_key, plan_key,
    claim_file_type, record_type, status,
    service_start_date, service_end_date, adjudicated_at,
    header_paid_amount_cents, source_file_id, source_row_id
)
SELECT
    ROW_NUMBER() OVER (ORDER BY r.claim_family_id, r.version_number),
    r.run_id,
    r.claim_family_id,
    r.version_number,
    NULL,
    m.member_key,
    mk.market_key,
    p.plan_key,
    r.claim_file_type,
    r.record_type,
    r.status,
    r.service_start_date,
    r.service_end_date,
    r.adjudicated_at,
    r.header_paid_amount_cents,
    r.source_file_id,
    r.source_row_id
FROM raw_claim_header r
JOIN dim_member m  ON m.synthetic_member_id = r.member_id
JOIN dim_market mk ON mk.market_id = r.market_id
JOIN dim_plan p    ON p.plan_id = r.plan_id AND p.market_key = mk.market_key
WHERE r.run_id = :run_id;

-- Second pass. The raw field carries 'FAMILY:VERSION'; the curated column
-- carries the surrogate key of that version, so a chain cannot point at a
-- version that was never submitted.
UPDATE claim_header_version AS h
SET replaces_version_key = prior.claim_version_key
FROM raw_claim_header r
JOIN claim_header_version prior
  ON prior.claim_family_key =
       substr(r.replaces_version_id, 1, instr(r.replaces_version_id, ':') - 1)
 AND prior.version_number =
       CAST(substr(r.replaces_version_id, instr(r.replaces_version_id, ':') + 1) AS INTEGER)
WHERE r.source_row_id = h.source_row_id
  AND r.source_file_id = h.source_file_id
  AND r.replaces_version_id IS NOT NULL
  AND h.run_id = :run_id;

-- Lines. A line whose service code is absent from the category map does not
-- resolve a category and is dropped here; DQ_LINE_UNMAPPED_SERVICE_CODE reports
-- it and blocks the release, so the dollars are explained rather than lost.
INSERT INTO claim_line_version (
    claim_version_key, line_number, category_key, service_code,
    provider_key, units, line_paid_amount_cents
)
SELECT
    h.claim_version_key,
    r.line_number,
    map.category_key,
    r.service_code,
    prov.provider_key,
    r.units,
    r.line_paid_amount_cents
FROM raw_claim_line r
JOIN claim_header_version h
  ON h.claim_family_key = r.claim_family_id
 AND h.version_number = r.version_number
 AND h.run_id = r.run_id
JOIN service_category_map map
  ON map.claim_file_type = h.claim_file_type
 AND map.service_code = r.service_code
 AND map.mapping_version = :mapping_version
 AND map.effective_start <= h.service_end_date
 AND (map.effective_end IS NULL OR map.effective_end >= h.service_end_date)
LEFT JOIN dim_provider prov ON prov.provider_id = r.provider_id
WHERE r.run_id = :run_id;
