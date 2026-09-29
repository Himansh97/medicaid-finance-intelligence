-- Immutable landing tables.
--
-- These deliberately do NOT enforce the grains in docs/data_dictionary.md. Raw
-- rows may be duplicated, may reference members that do not exist, may carry
-- invalid dates and may be missing required fields, because the fixture has to be
-- able to express those defects for a quality rule to catch them. Constraints
-- here cover only what is true of any landed row: it belongs to a file, and it
-- has an identifier within that file.
--
-- Nothing in this layer is ever updated. Corrections arrive as a new run.

CREATE TABLE raw_eligibility_span (
    source_file_id      TEXT NOT NULL REFERENCES source_file (source_file_id),
    source_row_id       TEXT NOT NULL,
    run_id              TEXT NOT NULL REFERENCES pipeline_run (run_id),
    ingested_at         TEXT NOT NULL,
    eligibility_span_id TEXT,
    member_id           TEXT,
    market_id           TEXT,
    plan_id             TEXT,
    program             TEXT,
    benefit_scope       TEXT,
    eligibility_group   TEXT,
    delivery_system     TEXT,
    start_date          TEXT,
    end_date            TEXT,
    PRIMARY KEY (source_file_id, source_row_id)
);

CREATE TABLE raw_claim_header (
    source_file_id      TEXT NOT NULL REFERENCES source_file (source_file_id),
    source_row_id       TEXT NOT NULL,
    run_id              TEXT NOT NULL REFERENCES pipeline_run (run_id),
    ingested_at         TEXT NOT NULL,
    claim_family_id     TEXT,
    version_number      INTEGER,
    replaces_version_id TEXT,
    member_id           TEXT,
    market_id           TEXT,
    plan_id             TEXT,
    claim_file_type     TEXT,
    record_type         TEXT,
    status              TEXT,
    service_start_date  TEXT,
    service_end_date    TEXT,
    adjudicated_at      TEXT,
    -- Nullable at this layer: an encounter legitimately has no Medicaid paid
    -- amount, and a malformed FFS row that is missing one must be able to land
    -- so the rule that requires it has something to fail against.
    header_paid_amount_cents INTEGER,
    PRIMARY KEY (source_file_id, source_row_id)
);

CREATE TABLE raw_claim_line (
    source_file_id      TEXT NOT NULL REFERENCES source_file (source_file_id),
    source_row_id       TEXT NOT NULL,
    run_id              TEXT NOT NULL REFERENCES pipeline_run (run_id),
    ingested_at         TEXT NOT NULL,
    claim_family_id     TEXT,
    version_number      INTEGER,
    line_number         INTEGER,
    service_code        TEXT,
    provider_id         TEXT,
    units               INTEGER,
    line_paid_amount_cents INTEGER,
    PRIMARY KEY (source_file_id, source_row_id)
);

CREATE TABLE raw_payment_transaction (
    source_file_id      TEXT NOT NULL REFERENCES source_file (source_file_id),
    source_row_id       TEXT NOT NULL,
    run_id              TEXT NOT NULL REFERENCES pipeline_run (run_id),
    ingested_at         TEXT NOT NULL,
    payment_transaction_id TEXT,
    claim_family_id     TEXT,
    version_number      INTEGER,
    payment_date        TEXT,
    event_type          TEXT,
    reverses_transaction_id TEXT,
    signed_amount_cents INTEGER,
    PRIMARY KEY (source_file_id, source_row_id)
);

CREATE TABLE raw_capitation_transaction (
    source_file_id      TEXT NOT NULL REFERENCES source_file (source_file_id),
    source_row_id       TEXT NOT NULL,
    run_id              TEXT NOT NULL REFERENCES pipeline_run (run_id),
    ingested_at         TEXT NOT NULL,
    capitation_transaction_id TEXT,
    member_id           TEXT,
    market_id           TEXT,
    plan_id             TEXT,
    coverage_month      TEXT,
    payment_date        TEXT,
    reverses_transaction_id TEXT,
    signed_amount_cents INTEGER,
    PRIMARY KEY (source_file_id, source_row_id)
);
