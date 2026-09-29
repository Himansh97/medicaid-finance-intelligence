"""The fixture contains what it claims, and the schema refuses what it forbids.

Run with:  python -m pytest tests -q     or     python tests/test_fixture_and_schema.py

A constraint nobody has tried to violate is a comment. Most of this file
deliberately writes bad rows and asserts the database rejects them.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_generation import fixture as fx
from src.data_generation.build_fixture import build, connect


class FixtureTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.db = Path(cls._dir.name) / "fixture.db"
        build(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def setUp(self):
        self.conn = connect(self.db)

    def tearDown(self):
        self.conn.close()

    def q(self, sql, *args):
        return self.conn.execute(sql, args).fetchall()

    def one(self, sql, *args):
        return self.conn.execute(sql, args).fetchone()[0]


class TestTenCases(FixtureTestCase):
    """docs/architecture.md names ten cases the first fixture must contain."""

    def test_every_named_case_is_present(self):
        missing = []
        for case, (entity, row_id) in fx.CASE_COVERAGE.items():
            if entity == "expected_partition":
                market, month, ent = row_id.split("/")
                found = self.one(
                    "SELECT COUNT(*) FROM expected_partition "
                    "WHERE market_id=? AND month_start=? AND entity=?",
                    market, month, ent)
            else:
                found = self.one(
                    f"SELECT COUNT(*) FROM {entity} WHERE source_row_id=?", row_id)
            if not found:
                missing.append(f"{case} ({entity}/{row_id})")
        self.assertEqual(missing, [], f"fixture lost cases: {missing}")

    def test_member_without_claims_has_exposure_and_no_claim(self):
        self.assertEqual(
            self.one("SELECT COUNT(*) FROM raw_eligibility_span WHERE member_id='SYN_M002'"), 1)
        self.assertEqual(
            self.one("SELECT COUNT(*) FROM raw_claim_header WHERE member_id='SYN_M002'"), 0)

    def test_partial_month_coverage_is_twelve_days_not_a_partial_member_month(self):
        start, end = self.q(
            "SELECT start_date, end_date FROM raw_eligibility_span "
            "WHERE source_row_id='ELG_003'")[0]
        self.assertEqual((start, end), ("2026-01-20", "2026-01-31"))

    def test_duplicate_shares_a_business_key_but_not_a_row_id(self):
        rows = self.q(
            "SELECT source_row_id FROM raw_eligibility_span "
            "WHERE eligibility_span_id='SYN_ELG_001' ORDER BY source_row_id")
        self.assertEqual([r[0] for r in rows], ["ELG_001", "ELG_008"])

    def test_missing_market_feed_is_expected_but_absent(self):
        expected = self.one(
            "SELECT COUNT(*) FROM expected_partition "
            "WHERE market_id='SYN_MKT_C' AND month_start='2026-02-01' AND entity='claims'")
        self.assertEqual(expected, 1, "the February market C feed must be expected")
        arrived = self.one(
            "SELECT COUNT(*) FROM raw_claim_header "
            "WHERE market_id='SYN_MKT_C' AND service_end_date >= '2026-02-01'")
        self.assertEqual(arrived, 0, "and must not have arrived, or the case is not exercised")

    def test_unmapped_service_code_is_absent_from_the_category_map(self):
        used = self.one(
            "SELECT COUNT(*) FROM raw_claim_line WHERE service_code='SVC_UNMAPPED_99'")
        mapped = self.one(
            "SELECT COUNT(*) FROM service_category_map WHERE service_code='SVC_UNMAPPED_99'")
        self.assertEqual((used, mapped), (1, 0))


class TestFixtureArithmetic(FixtureTestCase):
    """Figures the KPI acceptance examples will later be checked against."""

    def test_two_line_claim_sums_to_its_header(self):
        header = self.one(
            "SELECT header_paid_amount_cents FROM raw_claim_header "
            "WHERE claim_family_id='SYN_C001' AND version_number=1")
        lines = self.one(
            "SELECT SUM(line_paid_amount_cents) FROM raw_claim_line "
            "WHERE claim_family_id='SYN_C001' AND version_number=1")
        self.assertEqual(header, 12000)
        self.assertEqual(lines, 12000, "acceptance example 4: $70 + $50 = $120")

    def test_replacement_ledger_nets_to_the_replacement_amount(self):
        # Acceptance example 3: +100, -100, +120 reconciles to $120.
        total = self.one(
            "SELECT SUM(signed_amount_cents) FROM raw_payment_transaction "
            "WHERE claim_family_id='SYN_C002'")
        self.assertEqual(total, 12000)

    def test_voided_claim_nets_to_zero(self):
        total = self.one(
            "SELECT SUM(signed_amount_cents) FROM raw_payment_transaction "
            "WHERE claim_family_id='SYN_C003'")
        self.assertEqual(total, 0, "a void must leave no paid balance behind")

    def test_capitation_correction_nets_to_the_corrected_rate(self):
        total = self.one(
            "SELECT SUM(signed_amount_cents) FROM raw_capitation_transaction "
            "WHERE coverage_month='2026-01-01'")
        self.assertEqual(total, 47500, "$450 reversed and re-paid at $475")

    def test_denied_and_encounter_claims_produce_no_payments(self):
        for family in ("SYN_C004", "SYN_C005"):
            self.assertEqual(
                self.one("SELECT COUNT(*) FROM raw_payment_transaction "
                         "WHERE claim_family_id=?", family),
                0, f"{family} should have no payment activity")

    def test_money_is_exact(self):
        # The reason for integer cents. Summed as floats, these do not equal 120.
        cents = [r[0] for r in self.q(
            "SELECT line_paid_amount_cents FROM raw_claim_line "
            "WHERE claim_family_id='SYN_C001'")]
        self.assertEqual(sum(cents), 12000)
        self.assertIsInstance(sum(cents), int)


class TestSchemaRefusals(FixtureTestCase):
    """Each test writes a row the design forbids and expects the write to fail."""

    def assertRejected(self, sql, *args):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(sql, args)
            self.conn.commit()
        self.conn.rollback()

    def test_foreign_keys_are_actually_enforced(self):
        # If PRAGMA foreign_keys is off, every REFERENCES clause is decoration.
        self.assertEqual(self.one("PRAGMA foreign_keys"), 1)
        self.assertRejected(
            "INSERT INTO dim_plan VALUES (99, 999, 'SYN_X', 'x', 'MANAGED_CARE')")

    def test_accepted_ffs_claim_must_state_what_medicaid_paid(self):
        self.assertRejected(
            "INSERT INTO claim_header_version VALUES "
            "(900,?,'SYN_CX',1,NULL,1,1,1,'OT','FFS','ACCEPTED',"
            "'2026-01-01','2026-01-01','2026-01-01',NULL,'SRC_CLAIMS_2026Q1','X')",
            fx.RUN_ID)

    def test_a_terminal_claim_balance_cannot_be_negative(self):
        self.assertRejected(
            "INSERT INTO claim_header_version VALUES "
            "(901,?,'SYN_CY',1,NULL,1,1,1,'OT','FFS','ACCEPTED',"
            "'2026-01-01','2026-01-01','2026-01-01',-500,'SRC_CLAIMS_2026Q1','Y')",
            fx.RUN_ID)

    def test_service_dates_must_be_ordered(self):
        self.assertRejected(
            "INSERT INTO claim_header_version VALUES "
            "(902,?,'SYN_CZ',1,NULL,1,1,1,'OT','FFS','ACCEPTED',"
            "'2026-01-20','2026-01-10','2026-01-20',100,'SRC_CLAIMS_2026Q1','Z')",
            fx.RUN_ID)

    def test_a_reversal_must_reference_what_it_reverses(self):
        self.assertRejected(
            "INSERT INTO fact_payment_transaction VALUES "
            "('SYN_TXN_X',?, 'SYN_C001',1,'2026-01-10','REVERSAL',NULL,-100,"
            "'SRC_PAY_2026Q1','X')",
            fx.RUN_ID)

    def test_a_payment_must_not_reference_a_reversal_target(self):
        self.assertRejected(
            "INSERT INTO fact_payment_transaction VALUES "
            "('SYN_TXN_Y',?, 'SYN_C001',1,'2026-01-10','PAYMENT','SYN_TXN_001',100,"
            "'SRC_PAY_2026Q1','Y')",
            fx.RUN_ID)

    def test_a_reversal_cannot_be_positive(self):
        self.assertRejected(
            "INSERT INTO fact_payment_transaction VALUES "
            "('SYN_TXN_Z',?, 'SYN_C001',1,'2026-01-10','REVERSAL','SYN_TXN_001',100,"
            "'SRC_PAY_2026Q1','Z')",
            fx.RUN_ID)

    def test_negative_capitation_must_be_linked_to_what_it_corrects(self):
        self.assertRejected(
            "INSERT INTO fact_capitation_transaction VALUES "
            "('SYN_CAP_X',?,4,2,4,'2026-01-01','2026-01-05',NULL,-100,"
            "'SRC_CAP_2026Q1','X')",
            fx.RUN_ID)

    def test_a_member_month_weight_is_always_one(self):
        self.assertRejected(
            "INSERT INTO fact_member_month VALUES "
            "(?,1,'2026-01-01',1,1,'MEDICAID','FULL','ADULT','FFS',31,2,1)",
            fx.RUN_ID)

    def test_chip_or_limited_benefit_cannot_be_in_the_primary_cohort(self):
        self.assertRejected(
            "INSERT INTO fact_member_month VALUES "
            "(?,5,'2026-01-01',1,1,'CHIP','LIMITED','CHILD','FFS',31,1,1)",
            fx.RUN_ID)

    def test_a_member_cannot_hold_two_assignments_in_one_month(self):
        # The grain is the control: a conflict fails on write rather than
        # producing two member months and doubling a denominator.
        self.conn.execute(
            "INSERT INTO fact_member_month VALUES "
            "(?,1,'2026-01-01',1,1,'MEDICAID','FULL','ADULT','FFS',31,1,1)",
            (fx.RUN_ID,))
        self.assertRejected(
            "INSERT INTO fact_member_month VALUES "
            "(?,1,'2026-01-01',2,3,'MEDICAID','FULL','ADULT','FFS',31,1,1)",
            fx.RUN_ID)

    def test_eligible_days_must_fall_within_a_month(self):
        self.assertRejected(
            "INSERT INTO fact_member_month VALUES "
            "(?,2,'2026-01-01',1,1,'MEDICAID','FULL','ADULT','FFS',0,1,1)",
            fx.RUN_ID)

    def test_a_claim_family_cannot_repeat_a_version_number(self):
        # The curated table is empty until resolution runs, so the first version
        # has to be written here before a duplicate can collide with it.
        self.conn.execute(
            "INSERT INTO claim_header_version VALUES "
            "(903,?,'SYN_CDUP',1,NULL,1,1,1,'OT','FFS','ACCEPTED',"
            "'2026-01-10','2026-01-10','2026-01-10',12000,'SRC_CLAIMS_2026Q1','D1')",
            (fx.RUN_ID,))
        self.assertRejected(
            "INSERT INTO claim_header_version VALUES "
            "(904,?,'SYN_CDUP',1,NULL,1,1,1,'OT','FFS','ACCEPTED',"
            "'2026-01-10','2026-01-10','2026-01-10',12000,'SRC_CLAIMS_2026Q1','D2')",
            fx.RUN_ID)


class TestCuratedLayerIsEmpty(FixtureTestCase):
    """The build claims to load raw only. This checks that it did."""

    def test_curated_tables_are_created_but_unpopulated(self):
        for table in ("fact_member_month", "claim_header_version",
                      "claim_line_version", "fact_claim_header_final",
                      "fact_claim_line_final", "eligibility_span",
                      "fact_payment_transaction", "fact_capitation_transaction"):
            self.assertEqual(
                self.one(f"SELECT COUNT(*) FROM {table}"), 0,
                f"{table} should be empty until resolution is implemented")


if __name__ == "__main__":
    unittest.main(verbosity=2)
