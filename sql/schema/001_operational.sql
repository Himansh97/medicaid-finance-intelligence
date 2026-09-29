-- Operational entities. Everything else references a run, so this applies first.
-- Logical design: docs/data_dictionary.md, "Operational and publication entities".

-- One execution of the pipeline. Reproducibility depends on seed, config and code
-- version being recorded here rather than inferred from when a run happened.
CREATE TABLE pipeline_run (
    run_id            TEXT PRIMARY KEY,
    scenario_id       TEXT    NOT NULL,
    seed              INTEGER NOT NULL,
    config_hash       TEXT    NOT NULL,
    code_version      TEXT    NOT NULL,
    -- Paid amounts are only "final" with respect to a cutoff. A run without one
    -- cannot state what it observed, so it is required rather than defaulted.
    as_of_cutoff      TEXT    NOT NULL,
    started_at        TEXT    NOT NULL,
    ended_at          TEXT,
    status            TEXT    NOT NULL
        CHECK (status IN ('CREATED', 'VALIDATING', 'FAILED', 'READY_FOR_REVIEW', 'CERTIFIED')),
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

-- One ingested file. Hash and counts are captured at landing so a later
-- reconciliation can show that what was loaded is what arrived.
CREATE TABLE source_file (
    source_file_id    TEXT PRIMARY KEY,
    run_id            TEXT    NOT NULL REFERENCES pipeline_run (run_id),
    source_system     TEXT    NOT NULL DEFAULT 'synthetic'
        CHECK (source_system = 'synthetic'),
    entity            TEXT    NOT NULL,
    market_id         TEXT,
    content_hash      TEXT    NOT NULL,
    row_count         INTEGER NOT NULL CHECK (row_count >= 0),
    ingested_at       TEXT    NOT NULL
);

-- The market-month feeds a release is expected to contain. Without this, a market
-- that never arrives is indistinguishable from a market with nothing to report,
-- and the difference is the whole point of BR-04.
CREATE TABLE expected_partition (
    run_id            TEXT NOT NULL REFERENCES pipeline_run (run_id),
    market_id         TEXT NOT NULL,
    month_start       TEXT NOT NULL,
    entity            TEXT NOT NULL,
    PRIMARY KEY (run_id, market_id, month_start, entity)
);

-- One raw row that failed one rule. A row failing several rules produces several
-- records here, which is why the primary key includes the rule.
CREATE TABLE quarantine_record (
    run_id            TEXT NOT NULL REFERENCES pipeline_run (run_id),
    source_file_id    TEXT NOT NULL REFERENCES source_file (source_file_id),
    source_row_id     TEXT NOT NULL,
    rule_id           TEXT NOT NULL,
    reason            TEXT NOT NULL,
    remediation_status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (remediation_status IN ('OPEN', 'CORRECTED', 'ACCEPTED_WITH_REASON')),
    PRIMARY KEY (run_id, source_file_id, source_row_id, rule_id)
);

-- One rule evaluated against one partition. financial_impact_cents is nullable
-- because a structural rule has no dollar figure, and recording zero there would
-- assert an impact of nothing rather than an impact that does not apply.
CREATE TABLE dq_result (
    run_id                TEXT    NOT NULL REFERENCES pipeline_run (run_id),
    rule_id               TEXT    NOT NULL,
    rule_version          TEXT    NOT NULL,
    market_id             TEXT,
    month_start           TEXT,
    severity              TEXT    NOT NULL CHECK (severity IN ('BLOCKING', 'WARNING')),
    evaluated_count       INTEGER NOT NULL CHECK (evaluated_count >= 0),
    failing_row_count     INTEGER NOT NULL CHECK (failing_row_count >= 0),
    financial_impact_cents INTEGER,
    disposition           TEXT    NOT NULL
        CHECK (disposition IN ('PASS', 'FAIL', 'ACCEPTED_WITH_REASON', 'NOT_EVALUATED')),
    PRIMARY KEY (run_id, rule_id, rule_version, market_id, month_start),
    CHECK (failing_row_count <= evaluated_count)
);

-- The expected-defect manifest. A fixture deliberately contains bad rows, and a
-- quality rule that "passes" because the defect was quietly removed proves
-- nothing. Declaring defects up front lets a test assert that each one was
-- actually caught, and it is never read by the pipeline itself.
CREATE TABLE expected_defect (
    scenario_id       TEXT NOT NULL,
    defect_id         TEXT NOT NULL,
    entity            TEXT NOT NULL,
    source_row_id     TEXT,
    expected_rule_id  TEXT NOT NULL,
    description       TEXT NOT NULL,
    PRIMARY KEY (scenario_id, defect_id)
);
