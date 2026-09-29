-- Claim versions and the resolved finals.
--
-- Every submitted version is kept. Resolution selects one active version per
-- family and records the choice; it never deletes a superseded row, because the
-- payment ledger references versions that are no longer current.

CREATE TABLE claim_header_version (
    claim_version_key   INTEGER PRIMARY KEY,
    run_id              TEXT    NOT NULL REFERENCES pipeline_run (run_id),
    claim_family_key    TEXT    NOT NULL,
    version_number      INTEGER NOT NULL CHECK (version_number >= 1),
    -- Self-reference, so a replacement chain cannot point at a version that was
    -- never submitted. Cycles and branches are not expressible as a constraint
    -- and are checked by a rule at resolution time.
    replaces_version_key INTEGER REFERENCES claim_header_version (claim_version_key),
    member_key          INTEGER NOT NULL REFERENCES dim_member (member_key),
    market_key          INTEGER NOT NULL REFERENCES dim_market (market_key),
    plan_key            INTEGER NOT NULL REFERENCES dim_plan (plan_key),
    claim_file_type     TEXT    NOT NULL CHECK (claim_file_type IN ('IP', 'LT', 'OT', 'RX')),
    record_type         TEXT    NOT NULL CHECK (record_type IN ('FFS', 'ENCOUNTER')),
    status              TEXT    NOT NULL CHECK (status IN ('ACCEPTED', 'DENIED', 'VOID')),
    service_start_date  TEXT    NOT NULL,
    service_end_date    TEXT    NOT NULL,
    adjudicated_at      TEXT    NOT NULL,
    header_paid_amount_cents INTEGER,
    source_file_id      TEXT    NOT NULL REFERENCES source_file (source_file_id),
    source_row_id       TEXT    NOT NULL,
    UNIQUE (claim_family_key, version_number),
    CHECK (service_end_date >= service_start_date),
    -- An accepted FFS claim must state what Medicaid paid. An encounter may not,
    -- and a zero-dollar encounter is valid rather than a defect.
    CHECK (NOT (record_type = 'FFS' AND status = 'ACCEPTED')
           OR header_paid_amount_cents IS NOT NULL),
    -- A terminal accepted amount is never negative; reductions are expressed in
    -- the signed ledger, not as a negative claim balance.
    CHECK (header_paid_amount_cents IS NULL OR header_paid_amount_cents >= 0),
    CHECK (version_number > 1 OR replaces_version_key IS NULL)
);

CREATE INDEX idx_hdr_family ON claim_header_version (claim_family_key, version_number);
CREATE INDEX idx_hdr_service_end ON claim_header_version (service_end_date);

CREATE TABLE claim_line_version (
    claim_version_key   INTEGER NOT NULL REFERENCES claim_header_version (claim_version_key),
    line_number         INTEGER NOT NULL CHECK (line_number >= 1),
    category_key        INTEGER NOT NULL REFERENCES dim_service_category (category_key),
    service_code        TEXT    NOT NULL,
    provider_key        INTEGER REFERENCES dim_provider (provider_key),
    -- Units are service-specific. They are deliberately not summed into any
    -- cross-category utilisation measure.
    units               INTEGER,
    line_paid_amount_cents INTEGER,
    PRIMARY KEY (claim_version_key, line_number),
    CHECK (line_paid_amount_cents IS NULL OR line_paid_amount_cents >= 0)
);

-- One resolved active family per run. The selected version is recorded rather
-- than recomputed, so a later reader sees which version produced the number.
CREATE TABLE fact_claim_header_final (
    run_id              TEXT    NOT NULL REFERENCES pipeline_run (run_id),
    claim_family_key    TEXT    NOT NULL,
    claim_version_key   INTEGER NOT NULL REFERENCES claim_header_version (claim_version_key),
    member_key          INTEGER NOT NULL REFERENCES dim_member (member_key),
    market_key          INTEGER NOT NULL REFERENCES dim_market (market_key),
    plan_key            INTEGER NOT NULL REFERENCES dim_plan (plan_key),
    record_type         TEXT    NOT NULL CHECK (record_type IN ('FFS', 'ENCOUNTER')),
    claim_file_type     TEXT    NOT NULL CHECK (claim_file_type IN ('IP', 'LT', 'OT', 'RX')),
    -- The default analytical time basis. Every line inherits it; inpatient and
    -- long-term dollars are not spread across days.
    service_month       TEXT    NOT NULL,
    header_paid_amount_cents INTEGER,
    -- Whether the claim matched in-scope exposure in its service month. An
    -- unmatched claim stays in the reconciliation bridge and out of KPI
    -- numerators, so the dollars are explained rather than dropped.
    population_match    TEXT    NOT NULL
        CHECK (population_match IN ('MATCHED', 'OUT_OF_COHORT', 'NO_EXPOSURE', 'CONFLICTING_EXPOSURE')),
    PRIMARY KEY (run_id, claim_family_key)
);

CREATE INDEX idx_final_month ON fact_claim_header_final (service_month, market_key, record_type);

CREATE TABLE fact_claim_line_final (
    run_id              TEXT    NOT NULL,
    claim_family_key    TEXT    NOT NULL,
    line_number         INTEGER NOT NULL,
    category_key        INTEGER NOT NULL REFERENCES dim_service_category (category_key),
    provider_key        INTEGER REFERENCES dim_provider (provider_key),
    line_paid_amount_cents INTEGER,
    PRIMARY KEY (run_id, claim_family_key, line_number),
    FOREIGN KEY (run_id, claim_family_key)
        REFERENCES fact_claim_header_final (run_id, claim_family_key)
);
