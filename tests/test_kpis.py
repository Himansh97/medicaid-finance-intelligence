"""KPI views against the fixture, and the acceptance examples made executable.

Run with:  python -m pytest tests -q     or     python tests/test_kpis.py

Numbered examples refer to "Acceptance examples for later implementation" in
docs/kpi_dictionary.md. They are no longer for later.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_generation.build_fixture import build, connect
from src.validation.run_pipeline import run


class KpiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.db = Path(cls._dir.name) / "fixture.db"
        build(cls.db)
        run(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def setUp(self):
        self.conn = connect(self.db)

    def tearDown(self):
        self.conn.close()

    def one(self, sql, *args):
        row = self.conn.execute(sql, args).fetchone()
        return None if row is None else row[0]

    def rows(self, sql, *args):
        return self.conn.execute(sql, args).fetchall()


class TestRatioAggregation(KpiTestCase):
    """The rules that stop a ratio being computed the easy, wrong way."""

    def test_pmpm_divides_by_covered_exposure_not_by_claimants(self):
        # Acceptance example 1. January market A: three covered members, one of
        # whom had a claim. PMPM is spend over all three, not over the one.
        mm, spend, pmpm, members = self.rows(
            "SELECT member_months, ffs_paid_cents, ffs_pmpm_cents, distinct_members "
            "FROM v_kpi_ffs_month WHERE month_start='2026-01-01' AND market_key=1")[0]
        self.assertEqual((mm, spend, members), (3, 12000, 3))
        self.assertAlmostEqual(pmpm, 12000 / 3)
        claimants = self.one(
            "SELECT COUNT(DISTINCT member_key) FROM fact_claim_header_final "
            "WHERE record_type='FFS' AND service_month='2026-01-01' AND market_key=1")
        self.assertEqual(claimants, 1, "one claimant, three members in the denominator")

    def test_combining_markets_sums_components_and_never_averages_rates(self):
        # Acceptance example 2. Averaging market PMPMs gives a different and wrong
        # answer; the correct total divides summed spend by summed member months.
        spend, mm = self.rows(
            "SELECT SUM(ffs_paid_cents), SUM(member_months) FROM v_kpi_ffs_month "
            "WHERE month_start='2026-01-01'")[0]
        correct = spend / mm
        rates = [r[0] for r in self.rows(
            "SELECT ffs_pmpm_cents FROM v_kpi_ffs_month WHERE month_start='2026-01-01'")]
        naive = sum(rates) / len(rates)
        self.assertAlmostEqual(correct, 16500 / 5)
        self.assertNotAlmostEqual(
            correct, naive,
            msg="averaging market PMPMs must not coincidentally equal the right answer")

    def test_a_zero_denominator_is_unavailable_not_zero_and_not_infinite(self):
        # January market B: one covered member, no claims. Spend is a real zero;
        # average claim cost has no denominator and must be NULL.
        spend, claims, avg = self.rows(
            "SELECT ffs_paid_cents, ffs_claim_count, ffs_avg_claim_cost_cents "
            "FROM v_kpi_ffs_month WHERE month_start='2026-01-01' AND market_key=2")[0]
        self.assertEqual((spend, claims), (0, 0))
        self.assertIsNone(avg, "cost per claim with no claims is unanswerable")

    def test_every_rate_carries_its_numerator_and_denominator(self):
        columns = {r[1] for r in self.rows("PRAGMA table_info(v_kpi_ffs_month)")}
        for component in ("member_months", "ffs_paid_cents", "ffs_claim_count"):
            self.assertIn(component, columns,
                          "a rate without its components cannot be reproduced")


class TestClaimAndCategoryCounting(KpiTestCase):
    def test_a_two_line_claim_is_one_claim_and_the_sum_of_its_lines(self):
        # Acceptance example 4.
        spend, claims = self.rows(
            "SELECT ffs_paid_cents, ffs_claim_count FROM v_kpi_ffs_month "
            "WHERE month_start='2026-01-01' AND market_key=1")[0]
        self.assertEqual((spend, claims), (12000, 1))

    def test_but_it_appears_under_both_its_categories(self):
        categories = self.rows(
            "SELECT category_code, category_paid_cents, claims_containing_category "
            "FROM v_kpi_ffs_category_month "
            "WHERE month_start='2026-01-01' AND market_key=1 ORDER BY category_code")
        self.assertEqual(
            [(c[0], c[1]) for c in categories],
            [("OUTPATIENT", 7000), ("PROFESSIONAL", 5000)])
        self.assertEqual(
            sum(c[2] for c in categories), 2,
            "summing category claim counts double counts, which is why they are "
            "labelled non-additive")

    def test_category_shares_reconcile_to_one_hundred_percent(self):
        for month, market, total in self.rows(
            "SELECT month_start, market_key, ROUND(SUM(ffs_spend_share_pct), 6) "
            "FROM v_kpi_ffs_category_month GROUP BY month_start, market_key"):
            self.assertAlmostEqual(
                total, 100.0, places=6,
                msg=f"shares for {month} market {market} do not reconcile")

    def test_category_contributions_sum_to_the_overall_pmpm(self):
        for month, market in [("2026-01-01", 1), ("2026-01-01", 3), ("2026-02-01", 1)]:
            contributions = self.one(
                "SELECT SUM(category_contribution_to_pmpm_cents) "
                "FROM v_kpi_ffs_category_month "
                "WHERE month_start=? AND market_key=?", month, market)
            pmpm = self.one(
                "SELECT ffs_pmpm_cents FROM v_kpi_ffs_month "
                "WHERE month_start=? AND market_key=?", month, market)
            self.assertAlmostEqual(
                contributions, pmpm, places=6,
                msg=f"{month} market {market}: contributions must reconcile to PMPM")


class TestSeparationOfFinancialBases(KpiTestCase):
    def test_capitation_and_encounters_are_not_in_ffs_spend(self):
        # Acceptance example 5. Market B January holds a $475 capitation payment
        # and a zero-dollar encounter. Neither may appear as FFS medical spend.
        ffs = self.one(
            "SELECT ffs_paid_cents FROM v_kpi_ffs_month "
            "WHERE month_start='2026-01-01' AND market_key=2")
        cap, enc = self.rows(
            "SELECT capitation_cents, encounter_count FROM v_kpi_managed_care_month "
            "WHERE month_start='2026-01-01' AND market_key=2")[0]
        self.assertEqual(ffs, 0)
        self.assertEqual((cap, enc), (47500, 1))

    def test_no_view_exposes_an_encounter_dollar_column(self):
        # The structural guard behind example 5: a column that does not exist
        # cannot be added to capitation by someone building a total cost card.
        for view in ("v_encounter_month", "v_kpi_managed_care_month"):
            columns = {r[1] for r in self.rows(f"PRAGMA table_info({view})")}
            self.assertFalse(
                [c for c in columns if "encounter" in c and "cents" in c],
                f"{view} must not carry encounter dollars")

    def test_ffs_and_managed_care_exposure_are_reported_separately(self):
        ffs = self.one("SELECT COALESCE(SUM(member_months),0) FROM v_kpi_ffs_month")
        mc = self.one("SELECT COALESCE(SUM(member_months),0) FROM v_kpi_managed_care_month")
        self.assertEqual((ffs, mc), (7, 2))


class TestAvailability(KpiTestCase):
    """Acceptance example 7: a failed feed is unavailable, never zero."""

    def test_every_measure_carries_a_partition_status(self):
        for view in ("v_kpi_ffs_month", "v_kpi_managed_care_month",
                     "v_kpi_ffs_category_month"):
            columns = {r[1] for r in self.rows(f"PRAGMA table_info({view})")}
            self.assertIn("partition_status", columns,
                          f"{view} can be read without knowing if it is publishable")

    def test_a_run_level_failure_makes_every_partition_unavailable(self):
        statuses = {r[0] for r in self.rows(
            "SELECT DISTINCT partition_status FROM v_kpi_ffs_month")}
        self.assertEqual(statuses, {"UNAVAILABLE_RUN"},
                         "an unlocalised blocking defect could be anywhere")

    def test_the_missing_feed_alone_is_unavailable_once_run_level_rules_pass(self):
        # The fixture's run-level defects mask the partition-level one, so this
        # isolates it: with only the missing feed failing, market C February must
        # be the single unavailable partition and the rest must publish.
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "isolated.db"
            build(db)
            run(db)
            conn = connect(db)
            conn.execute(
                "UPDATE dq_result SET disposition='PASS' "
                "WHERE market_id='ALL' AND disposition='FAIL'")
            conn.commit()
            statuses = dict(conn.execute(
                "SELECT market_key || '/' || month_start, partition_status "
                "FROM v_kpi_ffs_month").fetchall())
            conn.close()

        self.assertEqual(statuses.get("3/2026-02-01"), "UNAVAILABLE_PARTITION")
        self.assertEqual(
            {k: v for k, v in statuses.items() if k != "3/2026-02-01"},
            {k: "AVAILABLE" for k in statuses if k != "3/2026-02-01"})

    def test_average_monthly_membership_is_unavailable_when_a_month_is_missing(self):
        # Market B has FFS exposure in January only. Dividing by the one month
        # that appeared would report an average the period does not support.
        avg = self.one(
            "SELECT average_monthly_membership FROM v_kpi_period_membership "
            "WHERE market_key=2 AND delivery_system='FFS'")
        self.assertIsNone(avg)
        present, expected = self.rows(
            "SELECT months_present, months_expected FROM v_kpi_period_membership "
            "WHERE market_key=2 AND delivery_system='FFS'")[0]
        self.assertEqual((present, expected), (1, 2))

    def test_and_is_available_when_every_month_is_present(self):
        avg = self.one(
            "SELECT average_monthly_membership FROM v_kpi_period_membership "
            "WHERE market_key=1 AND delivery_system='FFS'")
        self.assertAlmostEqual(avg, 2.0, msg="4 member months across 2 months")


if __name__ == "__main__":
    unittest.main(verbosity=2)
