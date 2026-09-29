"""Resolution and quality rules against the fixture.

Run with:  python -m pytest tests -q     or     python tests/test_pipeline.py

The fixture plants defects deliberately, so the run is expected to FAIL. These
tests assert it failed for exactly the declared reasons and not for any other.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_generation import fixture as fx
from src.data_generation.build_fixture import build, connect
from src.validation.run_pipeline import run


class PipelineTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.db = Path(cls._dir.name) / "fixture.db"
        build(cls.db)
        cls.result = run(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def setUp(self):
        self.conn = connect(self.db)

    def tearDown(self):
        self.conn.close()

    def one(self, sql, *args):
        return self.conn.execute(sql, args).fetchone()[0]

    def rows(self, sql, *args):
        return self.conn.execute(sql, args).fetchall()


class TestExposureResolution(PipelineTestCase):
    def test_the_duplicate_span_produces_one_span_not_two(self):
        self.assertEqual(
            self.one("SELECT COUNT(*) FROM eligibility_span "
                     "WHERE eligibility_span_id='SYN_ELG_001'"), 1)

    def test_and_therefore_one_member_month_not_two(self):
        # The point of deduplicating on the business key: a doubled denominator
        # halves PMPM silently, which no downstream check would notice.
        self.assertEqual(
            self.one("SELECT COUNT(*) FROM fact_member_month "
                     "WHERE member_key=1 AND month_start='2026-01-01'"), 1)

    def test_partial_coverage_is_one_member_month_with_twelve_days(self):
        weight, days = self.rows(
            "SELECT member_month_weight, eligible_days FROM fact_member_month "
            "WHERE member_key=3 AND month_start='2026-01-01'")[0]
        self.assertEqual(weight, 1, "any eligible day is a whole member month")
        self.assertEqual(days, 12, "and the days are kept for later proration")

    def test_a_member_with_no_claims_still_holds_a_denominator(self):
        self.assertEqual(
            self.one("SELECT COUNT(*) FROM fact_member_month WHERE member_key=2"), 1)
        self.assertEqual(
            self.one("SELECT COUNT(*) FROM fact_claim_header_final WHERE member_key=2"), 0)

    def test_chip_limited_benefit_is_excluded_from_the_primary_cohort(self):
        flags = {r[0] for r in self.rows(
            "SELECT in_primary_cohort FROM fact_member_month WHERE member_key=5")}
        self.assertEqual(flags, {0})

    def test_primary_cohort_member_months_by_delivery_system(self):
        ffs = self.one(
            "SELECT COALESCE(SUM(member_month_weight),0) FROM fact_member_month "
            "WHERE in_primary_cohort=1 AND delivery_system='FFS'")
        mc = self.one(
            "SELECT COALESCE(SUM(member_month_weight),0) FROM fact_member_month "
            "WHERE in_primary_cohort=1 AND delivery_system='MANAGED_CARE'")
        self.assertEqual((ffs, mc), (7, 2))


class TestClaimResolution(PipelineTestCase):
    def test_a_replacement_contributes_the_replacement_amount_once(self):
        # Acceptance example 3: $100 replaced by $120 is $120 and one claim.
        rows = self.rows(
            "SELECT header_paid_amount_cents FROM fact_claim_header_final "
            "WHERE claim_family_key='SYN_C002'")
        self.assertEqual(len(rows), 1, "one row per family, not one per version")
        self.assertEqual(rows[0][0], 12000)

    def test_a_voided_family_does_not_reach_the_finals(self):
        self.assertEqual(
            self.one("SELECT COUNT(*) FROM fact_claim_header_final "
                     "WHERE claim_family_key='SYN_C003'"), 0)

    def test_but_its_paid_version_was_kept_for_the_ledger_to_reference(self):
        # Filtering voids before resolution would drop this row, and the reversal
        # would then reference a version that does not exist.
        self.assertEqual(
            self.one("SELECT COUNT(*) FROM claim_header_version "
                     "WHERE claim_family_key='SYN_C003'"), 2)

    def test_a_denied_family_does_not_reach_the_finals(self):
        self.assertEqual(
            self.one("SELECT COUNT(*) FROM fact_claim_header_final "
                     "WHERE claim_family_key='SYN_C004'"), 0)

    def test_a_zero_dollar_encounter_is_valid_and_carries_no_spend(self):
        record_type, amount = self.rows(
            "SELECT record_type, header_paid_amount_cents "
            "FROM fact_claim_header_final WHERE claim_family_key='SYN_C005'")[0]
        self.assertEqual(record_type, "ENCOUNTER")
        self.assertIsNone(amount, "an encounter carries utilisation, not dollars")

    def test_service_month_comes_from_the_service_end_date(self):
        self.assertEqual(
            self.one("SELECT service_month FROM fact_claim_header_final "
                     "WHERE claim_family_key='SYN_C002'"), "2026-02-01")

    def test_every_final_claim_matched_its_exposure(self):
        unmatched = self.rows(
            "SELECT claim_family_key, population_match FROM fact_claim_header_final "
            "WHERE population_match <> 'MATCHED'")
        self.assertEqual(unmatched, [])

    def test_two_line_claim_lines_survive_resolution_and_sum_to_the_header(self):
        header = self.one("SELECT header_paid_amount_cents FROM fact_claim_header_final "
                          "WHERE claim_family_key='SYN_C001'")
        lines = self.one("SELECT SUM(line_paid_amount_cents) FROM fact_claim_line_final "
                         "WHERE claim_family_key='SYN_C001'")
        self.assertEqual((header, lines), (12000, 12000))


class TestFinancialReconciliation(PipelineTestCase):
    def test_every_family_ledger_equals_its_final_balance(self):
        mismatches = self.rows("""
            SELECT p.claim_family_key, SUM(p.signed_amount_cents),
                   COALESCE((SELECT f.header_paid_amount_cents
                             FROM fact_claim_header_final f
                             WHERE f.claim_family_key = p.claim_family_key), 0)
            FROM fact_payment_transaction p
            GROUP BY p.claim_family_key
            HAVING ABS(SUM(p.signed_amount_cents) -
                   COALESCE((SELECT f.header_paid_amount_cents
                             FROM fact_claim_header_final f
                             WHERE f.claim_family_key = p.claim_family_key), 0)) > 1
        """)
        self.assertEqual(mismatches, [], "cent-level agreement, not approximate")

    def test_a_voided_family_nets_to_zero_rather_than_merely_being_absent(self):
        self.assertEqual(
            self.one("SELECT SUM(signed_amount_cents) FROM fact_payment_transaction "
                     "WHERE claim_family_key='SYN_C003'"), 0)

    def test_capitation_correction_leaves_the_corrected_rate(self):
        self.assertEqual(
            self.one("SELECT SUM(signed_amount_cents) FROM fact_capitation_transaction "
                     "WHERE coverage_month='2026-01-01'"), 47500)

    def test_capitation_is_attributed_to_coverage_month_not_payment_month(self):
        # SYN_CAP_003 pays in February for January coverage. Attributing it to the
        # payment month would move $475 into the wrong month.
        coverage, payment = self.rows(
            "SELECT coverage_month, payment_date FROM fact_capitation_transaction "
            "WHERE capitation_transaction_id='SYN_CAP_003'")[0]
        self.assertEqual(coverage, "2026-01-01")
        self.assertTrue(payment.startswith("2026-02"))


class TestQualityRules(PipelineTestCase):
    def test_the_run_failed_because_blocking_rules_failed(self):
        self.assertEqual(self.result["status"], "FAILED")

    def test_each_declared_defect_was_caught_by_its_expected_rule(self):
        for defect_id, _, _, rule_id, description in fx.EXPECTED_DEFECTS:
            failed = self.one(
                "SELECT COUNT(*) FROM dq_result "
                "WHERE rule_id=? AND disposition='FAIL'", rule_id)
            self.assertGreater(
                failed, 0, f"{defect_id} went undetected by {rule_id}: {description}")

    def test_no_rule_failed_that_was_not_expected_to(self):
        expected = {d[3] for d in fx.EXPECTED_DEFECTS}
        actual = {r[0] for r in self.rows(
            "SELECT DISTINCT rule_id FROM dq_result "
            "WHERE severity='BLOCKING' AND disposition='FAIL'")}
        self.assertEqual(
            actual - expected, set(),
            "a rule failed on data the fixture believes is clean")

    def test_an_empty_arriving_feed_is_not_a_missing_feed(self):
        # The control for the missing-feed rule. Market B sent a February file
        # containing nothing, which is a complete report of a quiet month. A rule
        # that failed this would block every legitimately quiet partition.
        disposition = self.one(
            "SELECT disposition FROM dq_result "
            "WHERE rule_id='DQ_MISSING_MARKET_FEED' AND market_id='SYN_MKT_B' "
            "AND month_start='2026-02-01'")
        self.assertEqual(disposition, "PASS")
        self.assertEqual(
            self.one("SELECT row_count FROM source_file "
                     "WHERE source_file_id=?",
                     "SRC_CLAIMS_SYN_MKT_B_2026-02-01"),
            0, "and it really did arrive empty")

    def test_the_missing_feed_is_the_one_that_never_arrived(self):
        failing = self.rows(
            "SELECT market_id, month_start FROM dq_result "
            "WHERE rule_id='DQ_MISSING_MARKET_FEED' AND disposition='FAIL'")
        self.assertEqual(failing, [("SYN_MKT_C", "2026-02-01")])

    def test_the_unmapped_code_rule_reports_the_dollars_at_stake(self):
        impact = self.one(
            "SELECT financial_impact_cents FROM dq_result "
            "WHERE rule_id='DQ_LINE_UNMAPPED_SERVICE_CODE'")
        self.assertEqual(impact, 6000, "a structural failure with a dollar consequence")

    def test_rules_do_not_read_the_answer_key(self):
        # expected_defect exists for tests, not for rules. If a rule consulted it,
        # emptying it would change what the run reports.
        #
        # This builds its own database rather than mutating the shared one: a test
        # that re-runs the pipeline over populated curated tables would violate
        # their grains, and one that deletes rows would corrupt every test
        # ordered after it.
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "no_answer_key.db"
            build(db)
            conn = connect(db)
            conn.execute("DELETE FROM expected_defect")
            conn.commit()
            conn.close()

            blind = run(db)

        self.assertEqual(blind["status"], self.result["status"])
        self.assertEqual(
            sorted(f[0] for f in blind["failures"]),
            sorted(f[0] for f in self.result["failures"]),
            "rule outcomes changed when the declared defects were removed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
