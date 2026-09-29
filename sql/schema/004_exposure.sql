-- Eligibility and exposure. Membership is independent of claims: a member with
-- no claim still has exposure, which is what keeps them in a PMPM denominator.

CREATE TABLE eligibility_span (
    eligibility_span_id TEXT    PRIMARY KEY,
    run_id              TEXT    NOT NULL REFERENCES pipeline_run (run_id),
    member_key          INTEGER NOT NULL REFERENCES dim_member (member_key),
    market_key          INTEGER NOT NULL REFERENCES dim_market (market_key),
    plan_key            INTEGER NOT NULL REFERENCES dim_plan (plan_key),
    program             TEXT    NOT NULL CHECK (program IN ('MEDICAID', 'CHIP')),
    benefit_scope       TEXT    NOT NULL CHECK (benefit_scope IN ('FULL', 'LIMITED')),
    eligibility_group   TEXT    NOT NULL
        CHECK (eligibility_group IN ('CHILD', 'ADULT', 'AGED', 'DISABILITY')),
    delivery_system     TEXT    NOT NULL CHECK (delivery_system IN ('FFS', 'MANAGED_CARE')),
    -- Endpoints are inclusive. A one-day span has start_date = end_date and
    -- contributes a whole member month under the any-day convention.
    start_date          TEXT    NOT NULL,
    end_date            TEXT    NOT NULL,
    source_file_id      TEXT    NOT NULL REFERENCES source_file (source_file_id),
    source_row_id       TEXT    NOT NULL,
    CHECK (end_date >= start_date)
);

CREATE INDEX idx_elig_member ON eligibility_span (member_key, start_date);

-- The member-month fact. Grain is one member per calendar month per run, which
-- the primary key enforces: a member cannot hold two conflicting assignments in
-- one month, so such a conflict fails on insert rather than quietly producing
-- two member months and doubling a denominator.
CREATE TABLE fact_member_month (
    run_id              TEXT    NOT NULL REFERENCES pipeline_run (run_id),
    member_key          INTEGER NOT NULL REFERENCES dim_member (member_key),
    month_start         TEXT    NOT NULL,
    market_key          INTEGER NOT NULL REFERENCES dim_market (market_key),
    plan_key            INTEGER NOT NULL REFERENCES dim_plan (plan_key),
    program             TEXT    NOT NULL CHECK (program IN ('MEDICAID', 'CHIP')),
    benefit_scope       TEXT    NOT NULL CHECK (benefit_scope IN ('FULL', 'LIMITED')),
    eligibility_group   TEXT    NOT NULL
        CHECK (eligibility_group IN ('CHILD', 'ADULT', 'AGED', 'DISABILITY')),
    delivery_system     TEXT    NOT NULL CHECK (delivery_system IN ('FFS', 'MANAGED_CARE')),
    -- Retained even though the weight is 1, so prorated exposure can be measured
    -- later without regenerating the fact. Derived from a union of covered days,
    -- so overlapping duplicate spans cannot inflate it.
    eligible_days       INTEGER NOT NULL CHECK (eligible_days BETWEEN 1 AND 31),
    -- The any-day convention, stated as a constraint rather than a comment.
    member_month_weight INTEGER NOT NULL DEFAULT 1 CHECK (member_month_weight = 1),
    in_primary_cohort   INTEGER NOT NULL CHECK (in_primary_cohort IN (0, 1)),
    PRIMARY KEY (run_id, member_key, month_start),
    -- Primary cohort is full-benefit Medicaid. Encoding it here stops a later
    -- query from redefining the cohort by omitting a filter.
    CHECK (in_primary_cohort = 0
           OR (program = 'MEDICAID' AND benefit_scope = 'FULL'))
);

CREATE INDEX idx_mm_month_market ON fact_member_month (month_start, market_key, delivery_system);
