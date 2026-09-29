-- Signed ledgers. These stay separate from claim balances because service-month
-- spend and payment-month activity answer different questions.
--
-- A payment references the claim version it paid, including versions later
-- reversed. Joining to the final claim instead would hide the history that makes
-- a reversal explicable.

INSERT INTO fact_payment_transaction (
    payment_transaction_id, run_id, claim_family_key, claim_version_key,
    payment_date, event_type, reverses_transaction_id, signed_amount_cents,
    source_file_id, source_row_id
)
SELECT
    r.payment_transaction_id,
    r.run_id,
    r.claim_family_id,
    h.claim_version_key,
    r.payment_date,
    r.event_type,
    r.reverses_transaction_id,
    r.signed_amount_cents,
    r.source_file_id,
    r.source_row_id
FROM raw_payment_transaction r
JOIN claim_header_version h
  ON h.claim_family_key = r.claim_family_id
 AND h.version_number = r.version_number
 AND h.run_id = r.run_id
WHERE r.run_id = :run_id
-- Reversals must load after the payments they reference, or the self-reference
-- fails. Ordering by event type puts PAYMENT before REVERSAL alphabetically.
ORDER BY r.payment_date, r.event_type, r.payment_transaction_id;

INSERT INTO fact_capitation_transaction (
    capitation_transaction_id, run_id, member_key, market_key, plan_key,
    coverage_month, payment_date, reverses_transaction_id,
    signed_amount_cents, source_file_id, source_row_id
)
SELECT
    r.capitation_transaction_id,
    r.run_id,
    m.member_key,
    mk.market_key,
    p.plan_key,
    r.coverage_month,
    r.payment_date,
    r.reverses_transaction_id,
    r.signed_amount_cents,
    r.source_file_id,
    r.source_row_id
FROM raw_capitation_transaction r
JOIN dim_member m  ON m.synthetic_member_id = r.member_id
JOIN dim_market mk ON mk.market_id = r.market_id
JOIN dim_plan p    ON p.plan_id = r.plan_id AND p.market_key = mk.market_key
WHERE r.run_id = :run_id
ORDER BY r.payment_date,
         CASE WHEN r.reverses_transaction_id IS NULL THEN 0 ELSE 1 END,
         r.capitation_transaction_id;
