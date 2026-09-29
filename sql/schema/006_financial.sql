-- Signed financial ledgers. These are separate from claim balances on purpose:
-- service-month spend and payment-month activity are different questions and
-- must never be mixed in one series.

-- One FFS financial event. A replacement books a reversal of the previous
-- balance and a payment for the new one, so the ledger explains how a balance
-- changed rather than only what it ended at.
CREATE TABLE fact_payment_transaction (
    payment_transaction_id TEXT    PRIMARY KEY,
    run_id                 TEXT    NOT NULL REFERENCES pipeline_run (run_id),
    claim_family_key       TEXT    NOT NULL,
    claim_version_key      INTEGER NOT NULL REFERENCES claim_header_version (claim_version_key),
    payment_date           TEXT    NOT NULL,
    event_type             TEXT    NOT NULL CHECK (event_type IN ('PAYMENT', 'REVERSAL')),
    reverses_transaction_id TEXT   REFERENCES fact_payment_transaction (payment_transaction_id),
    -- Signed: payments positive, reversals negative. Summing the column over a
    -- family through a cutoff gives that family's balance at the cutoff.
    signed_amount_cents    INTEGER NOT NULL,
    source_file_id         TEXT    NOT NULL REFERENCES source_file (source_file_id),
    source_row_id          TEXT    NOT NULL,
    -- A reversal must reference what it reverses, and a payment must not. Partial
    -- changes are expressed as a full reversal plus a replacement payment, never
    -- as a partial adjustment.
    CHECK ((event_type = 'REVERSAL') = (reverses_transaction_id IS NOT NULL)),
    CHECK ((event_type = 'PAYMENT'  AND signed_amount_cents >= 0)
        OR (event_type = 'REVERSAL' AND signed_amount_cents <= 0))
);

CREATE INDEX idx_pay_family ON fact_payment_transaction (claim_family_key, payment_date);
CREATE INDEX idx_pay_date ON fact_payment_transaction (payment_date);

-- State-to-plan capitation. Attributed to a coverage month, which is not the
-- same as the month it was paid in. No service category and no provider: a
-- capitation payment buys coverage, not a service, and allocating it to
-- categories would invent detail that does not exist.
CREATE TABLE fact_capitation_transaction (
    capitation_transaction_id TEXT    PRIMARY KEY,
    run_id                    TEXT    NOT NULL REFERENCES pipeline_run (run_id),
    member_key                INTEGER NOT NULL REFERENCES dim_member (member_key),
    market_key                INTEGER NOT NULL REFERENCES dim_market (market_key),
    plan_key                  INTEGER NOT NULL REFERENCES dim_plan (plan_key),
    coverage_month            TEXT    NOT NULL,
    payment_date              TEXT    NOT NULL,
    reverses_transaction_id   TEXT    REFERENCES fact_capitation_transaction (capitation_transaction_id),
    -- Corrections are permitted and must reference the payment they correct.
    -- An unlinked negative capitation row is a defect, not a correction.
    signed_amount_cents       INTEGER NOT NULL,
    source_file_id            TEXT    NOT NULL REFERENCES source_file (source_file_id),
    source_row_id             TEXT    NOT NULL,
    CHECK (signed_amount_cents >= 0 OR reverses_transaction_id IS NOT NULL)
);

CREATE INDEX idx_cap_coverage ON fact_capitation_transaction (coverage_month, market_key, plan_key);
