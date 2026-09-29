-- Conformed dimensions. One row describes one thing; no dimension carries a
-- measure. Grains follow docs/data_dictionary.md, "Dimensions".

CREATE TABLE dim_market (
    market_key    INTEGER PRIMARY KEY,
    market_id     TEXT NOT NULL UNIQUE,
    market_name   TEXT NOT NULL,
    -- Descriptive only. A fictional market carrying a real state code is not
    -- evidence about that state and must never be reported as such.
    state_code    TEXT NOT NULL
);

CREATE TABLE dim_member (
    member_key          INTEGER PRIMARY KEY,
    synthetic_member_id TEXT NOT NULL UNIQUE,
    -- Broad bands only. No birth date, name, address or any direct identifier
    -- appears anywhere in this schema.
    age_band            TEXT NOT NULL
        CHECK (age_band IN ('0-17', '18-34', '35-49', '50-64', '65+')),
    CHECK (synthetic_member_id LIKE 'SYN\_%' ESCAPE '\')
);

CREATE TABLE dim_plan (
    plan_key   INTEGER PRIMARY KEY,
    market_key INTEGER NOT NULL REFERENCES dim_market (market_key),
    plan_id    TEXT NOT NULL,
    plan_name  TEXT NOT NULL,
    -- The FFS row exists so an FFS member-month can carry a real plan key rather
    -- than a null that every later join has to special-case.
    plan_type  TEXT NOT NULL CHECK (plan_type IN ('MANAGED_CARE', 'FFS_NOT_APPLICABLE')),
    UNIQUE (market_key, plan_id)
);

CREATE TABLE dim_provider (
    provider_key  INTEGER PRIMARY KEY,
    provider_id   TEXT NOT NULL UNIQUE,
    provider_type TEXT NOT NULL,
    -- No real NPI. An unknown provider is permitted because provider linkage is
    -- not essential to any certified KPI in this MVP.
    CHECK (provider_id LIKE 'SYN\_%' ESCAPE '\')
);

CREATE TABLE dim_service_category (
    category_key  INTEGER PRIMARY KEY,
    category_code TEXT NOT NULL UNIQUE,
    category_name TEXT NOT NULL,
    -- Mutually exclusive by construction: every line maps to exactly one, which
    -- is what makes K09 spend shares reconcile to 100%.
    CHECK (category_code IN ('INPATIENT', 'INSTITUTIONAL_LT', 'OUTPATIENT',
                             'PROFESSIONAL', 'PHARMACY', 'OTHER'))
);

-- Versioned map from claim file type and service code to a category. Effective
-- dating plus a version means a correction produces a new release rather than
-- silently restating a published one.
CREATE TABLE service_category_map (
    mapping_version   TEXT    NOT NULL,
    claim_file_type   TEXT    NOT NULL CHECK (claim_file_type IN ('IP', 'LT', 'OT', 'RX')),
    service_code      TEXT    NOT NULL,
    category_key      INTEGER NOT NULL REFERENCES dim_service_category (category_key),
    effective_start   TEXT    NOT NULL,
    effective_end     TEXT,
    PRIMARY KEY (mapping_version, claim_file_type, service_code, effective_start),
    CHECK (effective_end IS NULL OR effective_end >= effective_start)
);

CREATE TABLE dim_date (
    date_key      INTEGER PRIMARY KEY,
    calendar_date TEXT    NOT NULL UNIQUE,
    month_start   TEXT    NOT NULL,
    year          INTEGER NOT NULL,
    month_number  INTEGER NOT NULL CHECK (month_number BETWEEN 1 AND 12),
    days_in_month INTEGER NOT NULL CHECK (days_in_month BETWEEN 28 AND 31)
);

CREATE INDEX idx_dim_date_month ON dim_date (month_start);
