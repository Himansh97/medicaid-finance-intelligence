"""The small fixture named in docs/architecture.md, "Future verification and
learning sequence".

Every record here is fictional and written by hand. There is no sampling and no
randomness: the fixture is small enough to reason about completely, and a test
that fails should point at a row a person can read rather than at a seed.

The ten cases the architecture asks for are declared in EXPECTED_DEFECTS and in
CASE_COVERAGE below, so a test can assert the fixture still contains them rather
than trusting this docstring.

Money is in integer cents throughout. See sql/schema/README.md.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

SCENARIO_ID = "FIXTURE_V1"
RUN_ID = "RUN_FIXTURE_0001"
SEED = 20260929
MAPPING_VERSION = "MAP_V1"
CODE_VERSION = "fixture-only"

# Paid amounts are only final with respect to a cutoff. Every payment in this
# fixture falls well before it, so nothing is provisional for the wrong reason.
AS_OF_CUTOFF = "2026-03-31"
INGESTED_AT = "2026-03-31T00:00:00Z"

MONTHS = ["2026-01-01", "2026-02-01"]

# --------------------------------------------------------------------------
# Dimensions
# --------------------------------------------------------------------------

MARKETS = [
    # (market_key, market_id, market_name, state_code)
    (1, "SYN_MKT_A", "Northgate", "TX"),
    (2, "SYN_MKT_B", "Larkfield", "OH"),
    (3, "SYN_MKT_C", "Westbrook", "AZ"),
]

PLANS = [
    # (plan_key, market_key, plan_id, plan_name, plan_type)
    (1, 1, "SYN_PLAN_A_FFS", "Northgate fee-for-service", "FFS_NOT_APPLICABLE"),
    (2, 1, "SYN_PLAN_A1", "Northgate Care Plan", "MANAGED_CARE"),
    (3, 2, "SYN_PLAN_B_FFS", "Larkfield fee-for-service", "FFS_NOT_APPLICABLE"),
    (4, 2, "SYN_PLAN_B1", "Larkfield Health Choice", "MANAGED_CARE"),
    (5, 3, "SYN_PLAN_C_FFS", "Westbrook fee-for-service", "FFS_NOT_APPLICABLE"),
    (6, 3, "SYN_PLAN_C1", "Westbrook Community Plan", "MANAGED_CARE"),
]

MEMBERS = [
    # (member_key, synthetic_member_id, age_band)
    (1, "SYN_M001", "35-49"),
    (2, "SYN_M002", "18-34"),
    (3, "SYN_M003", "0-17"),
    (4, "SYN_M004", "50-64"),
    (5, "SYN_M005", "0-17"),
    (6, "SYN_M006", "65+"),
    (7, "SYN_M007", "18-34"),
]

CATEGORIES = [
    (1, "INPATIENT", "Inpatient"),
    (2, "INSTITUTIONAL_LT", "Institutional long-term care"),
    (3, "OUTPATIENT", "Outpatient"),
    (4, "PROFESSIONAL", "Professional"),
    (5, "PHARMACY", "Pharmacy"),
    (6, "OTHER", "Other"),
]

PROVIDERS = [
    (1, "SYN_PRV_001", "HOSPITAL"),
    (2, "SYN_PRV_002", "PHYSICIAN"),
    (3, "SYN_PRV_003", "PHARMACY"),
]

# SVC_UNMAPPED_99 is deliberately absent. An unmapped line must block a release,
# and a map with no gap cannot demonstrate that.
CATEGORY_MAP = [
    # (mapping_version, claim_file_type, service_code, category_key, effective_start, effective_end)
    (MAPPING_VERSION, "OT", "SVC_OUTPT_01", 3, "2026-01-01", None),
    (MAPPING_VERSION, "OT", "SVC_PROF_01", 4, "2026-01-01", None),
    (MAPPING_VERSION, "IP", "SVC_IP_01", 1, "2026-01-01", None),
    (MAPPING_VERSION, "RX", "SVC_RX_01", 5, "2026-01-01", None),
    (MAPPING_VERSION, "LT", "SVC_LT_01", 2, "2026-01-01", None),
]


def dim_date_rows():
    """Every day of the fixture's service months."""
    rows = []
    key = 0
    for month in MONTHS:
        y, m, _ = (int(p) for p in month.split("-"))
        days = monthrange(y, m)[1]
        for d in range(1, days + 1):
            key += 1
            rows.append((key, date(y, m, d).isoformat(), month, y, m, days))
    return rows


# --------------------------------------------------------------------------
# Raw eligibility
# --------------------------------------------------------------------------

# (row_id, span_id, member, market, plan, program, scope, group, delivery, start, end)
_SPANS = [
    ("ELG_001", "SYN_ELG_001", "SYN_M001", "SYN_MKT_A", "SYN_PLAN_A_FFS",
     "MEDICAID", "FULL", "ADULT", "FFS", "2026-01-01", "2026-02-28"),
    # Case 1: enrolled, never claims. Must still hold a PMPM denominator.
    ("ELG_002", "SYN_ELG_002", "SYN_M002", "SYN_MKT_A", "SYN_PLAN_A_FFS",
     "MEDICAID", "FULL", "ADULT", "FFS", "2026-01-01", "2026-01-31"),
    # Case 2: twelve covered days. One member month under the any-day convention.
    ("ELG_003", "SYN_ELG_003", "SYN_M003", "SYN_MKT_B", "SYN_PLAN_B_FFS",
     "MEDICAID", "FULL", "CHILD", "FFS", "2026-01-20", "2026-01-31"),
    ("ELG_004", "SYN_ELG_004", "SYN_M004", "SYN_MKT_B", "SYN_PLAN_B1",
     "MEDICAID", "FULL", "ADULT", "MANAGED_CARE", "2026-01-01", "2026-02-28"),
    # Out of the primary cohort: separate CHIP, limited benefit.
    ("ELG_005", "SYN_ELG_005", "SYN_M005", "SYN_MKT_A", "SYN_PLAN_A_FFS",
     "CHIP", "LIMITED", "CHILD", "FFS", "2026-01-01", "2026-02-28"),
    ("ELG_006", "SYN_ELG_006", "SYN_M006", "SYN_MKT_C", "SYN_PLAN_C_FFS",
     "MEDICAID", "FULL", "AGED", "FFS", "2026-01-01", "2026-02-28"),
    ("ELG_007", "SYN_ELG_007", "SYN_M007", "SYN_MKT_A", "SYN_PLAN_A_FFS",
     "MEDICAID", "FULL", "ADULT", "FFS", "2026-01-01", "2026-01-31"),
    # Case 9: the same span landed twice. Same business key, different row id, so
    # only a rule on the business key catches it. Deduplicating must not create a
    # second member month.
    ("ELG_008", "SYN_ELG_001", "SYN_M001", "SYN_MKT_A", "SYN_PLAN_A_FFS",
     "MEDICAID", "FULL", "ADULT", "FFS", "2026-01-01", "2026-02-28"),
]


def raw_eligibility_rows(file_id):
    return [
        (file_id, r[0], RUN_ID, INGESTED_AT, r[1], r[2], r[3], r[4],
         r[5], r[6], r[7], r[8], r[9], r[10])
        for r in _SPANS
    ]


# --------------------------------------------------------------------------
# Raw claims
# --------------------------------------------------------------------------

# (row_id, family, version, replaces, member, market, plan, file_type,
#  record_type, status, svc_start, svc_end, adjudicated, header_cents)
_HEADERS = [
    # Case 3: one claim, two lines, two categories. One claim overall; category
    # claim counts are not additive.
    ("HDR_001", "SYN_C001", 1, None, "SYN_M001", "SYN_MKT_A", "SYN_PLAN_A_FFS",
     "OT", "FFS", "ACCEPTED", "2026-01-10", "2026-01-10", "2026-01-10", 12000),
    # Case 4: replacement. $100 superseded by $120; the family contributes $120
    # and one claim, not $220 and two.
    ("HDR_002", "SYN_C002", 1, None, "SYN_M001", "SYN_MKT_A", "SYN_PLAN_A_FFS",
     "OT", "FFS", "ACCEPTED", "2026-02-05", "2026-02-05", "2026-02-05", 10000),
    ("HDR_003", "SYN_C002", 2, "SYN_C002:1", "SYN_M001", "SYN_MKT_A", "SYN_PLAN_A_FFS",
     "OT", "FFS", "ACCEPTED", "2026-02-05", "2026-02-05", "2026-02-20", 12000),
    # Case 5: void. Voids must be resolved through the chain, never filtered out
    # before resolution, or the paid v1 would survive as a live claim.
    ("HDR_004", "SYN_C003", 1, None, "SYN_M007", "SYN_MKT_A", "SYN_PLAN_A_FFS",
     "IP", "FFS", "ACCEPTED", "2026-01-15", "2026-01-16", "2026-01-15", 8000),
    ("HDR_005", "SYN_C003", 2, "SYN_C003:1", "SYN_M007", "SYN_MKT_A", "SYN_PLAN_A_FFS",
     "IP", "FFS", "VOID", "2026-01-15", "2026-01-16", "2026-01-28", 0),
    # Case 6: denied. Contributes no spend and no utilisation.
    ("HDR_006", "SYN_C004", 1, None, "SYN_M003", "SYN_MKT_B", "SYN_PLAN_B_FFS",
     "OT", "FFS", "DENIED", "2026-01-22", "2026-01-22", "2026-01-25", 0),
    # Case 7: zero-dollar encounter. Valid; contributes utilisation and no spend.
    ("HDR_007", "SYN_C005", 1, None, "SYN_M004", "SYN_MKT_B", "SYN_PLAN_B1",
     "OT", "ENCOUNTER", "ACCEPTED", "2026-01-12", "2026-01-12", "2026-01-12", None),
    # Case 10 depends on this one existing in January and nothing arriving for
    # market C in February.
    ("HDR_008", "SYN_C006", 1, None, "SYN_M006", "SYN_MKT_C", "SYN_PLAN_C_FFS",
     "RX", "FFS", "ACCEPTED", "2026-01-08", "2026-01-08", "2026-01-08", 4500),
    # Carries a service code the category map does not contain.
    ("HDR_009", "SYN_C007", 1, None, "SYN_M001", "SYN_MKT_A", "SYN_PLAN_A_FFS",
     "OT", "FFS", "ACCEPTED", "2026-02-14", "2026-02-14", "2026-02-14", 6000),
]

# (row_id, family, version, line_no, service_code, provider, units, cents)
_LINES = [
    ("LIN_001", "SYN_C001", 1, 1, "SVC_OUTPT_01", "SYN_PRV_001", 1, 7000),
    ("LIN_002", "SYN_C001", 1, 2, "SVC_PROF_01", "SYN_PRV_002", 1, 5000),
    ("LIN_003", "SYN_C002", 1, 1, "SVC_OUTPT_01", "SYN_PRV_001", 1, 10000),
    ("LIN_004", "SYN_C002", 2, 1, "SVC_OUTPT_01", "SYN_PRV_001", 1, 12000),
    ("LIN_005", "SYN_C003", 1, 1, "SVC_IP_01", "SYN_PRV_001", 2, 8000),
    ("LIN_006", "SYN_C003", 2, 1, "SVC_IP_01", "SYN_PRV_001", 2, 0),
    ("LIN_007", "SYN_C004", 1, 1, "SVC_OUTPT_01", "SYN_PRV_002", 1, 0),
    ("LIN_008", "SYN_C005", 1, 1, "SVC_OUTPT_01", "SYN_PRV_002", 1, None),
    ("LIN_009", "SYN_C006", 1, 1, "SVC_RX_01", "SYN_PRV_003", 30, 4500),
    ("LIN_010", "SYN_C007", 1, 1, "SVC_UNMAPPED_99", "SYN_PRV_002", 1, 6000),
]


def raw_claim_header_rows(file_id):
    return [(file_id, r[0], RUN_ID, INGESTED_AT, *r[1:]) for r in _HEADERS]


def raw_claim_line_rows(file_id):
    return [(file_id, r[0], RUN_ID, INGESTED_AT, *r[1:]) for r in _LINES]


# --------------------------------------------------------------------------
# Raw financial activity
# --------------------------------------------------------------------------

# Adjudication and payment coincide in this fixture, so a ledger balance through
# the cutoff reconciles to the final claim balance without an accounts-payable
# model. Acceptance example 3's +100, -100, +120 appears here literally.
_PAYMENTS = [
    # (row_id, txn_id, family, version, payment_date, event_type, reverses, cents)
    ("PAY_001", "SYN_TXN_001", "SYN_C001", 1, "2026-01-10", "PAYMENT", None, 12000),
    ("PAY_002", "SYN_TXN_002", "SYN_C002", 1, "2026-02-05", "PAYMENT", None, 10000),
    ("PAY_003", "SYN_TXN_003", "SYN_C002", 1, "2026-02-20", "REVERSAL", "SYN_TXN_002", -10000),
    ("PAY_004", "SYN_TXN_004", "SYN_C002", 2, "2026-02-20", "PAYMENT", None, 12000),
    ("PAY_005", "SYN_TXN_005", "SYN_C003", 1, "2026-01-15", "PAYMENT", None, 8000),
    ("PAY_006", "SYN_TXN_006", "SYN_C003", 2, "2026-01-28", "REVERSAL", "SYN_TXN_005", -8000),
    ("PAY_007", "SYN_TXN_007", "SYN_C006", 1, "2026-01-08", "PAYMENT", None, 4500),
    ("PAY_008", "SYN_TXN_008", "SYN_C007", 1, "2026-02-14", "PAYMENT", None, 6000),
]

# Case 8: a capitation correction. The January payment is reversed in February
# and re-paid at a different rate, so coverage month and payment month diverge.
_CAPITATION = [
    # (row_id, txn_id, member, market, plan, coverage_month, payment_date, reverses, cents)
    ("CAP_001", "SYN_CAP_001", "SYN_M004", "SYN_MKT_B", "SYN_PLAN_B1",
     "2026-01-01", "2026-01-05", None, 45000),
    ("CAP_002", "SYN_CAP_002", "SYN_M004", "SYN_MKT_B", "SYN_PLAN_B1",
     "2026-01-01", "2026-02-10", "SYN_CAP_001", -45000),
    ("CAP_003", "SYN_CAP_003", "SYN_M004", "SYN_MKT_B", "SYN_PLAN_B1",
     "2026-01-01", "2026-02-10", None, 47500),
    ("CAP_004", "SYN_CAP_004", "SYN_M004", "SYN_MKT_B", "SYN_PLAN_B1",
     "2026-02-01", "2026-02-05", None, 47500),
]


def raw_payment_rows(file_id):
    return [(file_id, r[0], RUN_ID, INGESTED_AT, *r[1:]) for r in _PAYMENTS]


def raw_capitation_rows(file_id):
    return [(file_id, r[0], RUN_ID, INGESTED_AT, *r[1:]) for r in _CAPITATION]


# --------------------------------------------------------------------------
# Expected coverage and declared defects
# --------------------------------------------------------------------------

def expected_partitions():
    """Every market-month feed a complete release would contain.

    Market C has no claims file for February. Because the expectation is recorded
    here, that absence is a blocking failure rather than a month that looks quiet.
    """
    rows = []
    for _, market_id, _, _ in MARKETS:
        for month in MONTHS:
            for entity in ("eligibility", "claims"):
                rows.append((RUN_ID, market_id, month, entity))
    return rows


# Declared so a test can assert each defect was actually caught. Never read by
# the pipeline: a rule that consults the answer key proves nothing.
EXPECTED_DEFECTS = [
    # (defect_id, entity, source_row_id, expected_rule_id, description)
    ("D01", "raw_eligibility_span", "ELG_008", "DQ_ELIG_DUPLICATE_KEY",
     "SYN_ELG_001 landed twice under different source rows; dedupe must not create a second member month"),
    ("D02", "raw_claim_line", "LIN_010", "DQ_LINE_UNMAPPED_SERVICE_CODE",
     "SVC_UNMAPPED_99 is absent from the category map; unmapped lines block the release"),
    ("D03", "expected_partition", None, "DQ_MISSING_MARKET_FEED",
     "Market SYN_MKT_C has no claims feed for 2026-02; the all-market total is unavailable, not smaller"),
]

# What each of the architecture's ten cases is represented by, so a test can
# assert the fixture has not quietly lost one.
CASE_COVERAGE = {
    "member without claims": ("raw_eligibility_span", "ELG_002"),
    "partial-month coverage": ("raw_eligibility_span", "ELG_003"),
    "two-line claim": ("raw_claim_header", "HDR_001"),
    "replacement": ("raw_claim_header", "HDR_003"),
    "void": ("raw_claim_header", "HDR_005"),
    "denied claim": ("raw_claim_header", "HDR_006"),
    "zero-dollar encounter": ("raw_claim_header", "HDR_007"),
    "capitation correction": ("raw_capitation_transaction", "CAP_002"),
    "duplicate input": ("raw_eligibility_span", "ELG_008"),
    "missing market feed": ("expected_partition", "SYN_MKT_C/2026-02-01/claims"),
}
