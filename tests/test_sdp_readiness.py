"""The reporting readiness view, and the honesty of its framing.

Most of what matters here is that the view never claims to measure state directed
payment reporting. It measures supplemental payment reporting in 2020 and offers
that as a proxy, and the tests below exist to stop that distinction eroding.

Run with:  python -m pytest tests -q   or   python tests/test_sdp_readiness.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.sdp.readiness import USABLE_ASSESSMENTS, parse_topic_file, supplemental_payment_files

PUBLISHED = ROOT / "data" / "published" / "sdp_reporting_readiness.json"


class TestTopicParsing(unittest.TestCase):
    def test_the_header_row_is_found_past_the_title_lines(self):
        # DQ Atlas files open with title, method and source lines before the
        # real header, so a naive reader takes the title as the column names.
        content = (
            '"Title: Explore by Topic, Supplemental Payments",,,\n'
            '"DQ Assessment based on: Multiple criteria",,,\n'
            '"Source: Centers for Medicare & Medicaid Services.",,,\n'
            ',,,\n'
            '"State","Data Year","DQ Assessment","# Supplemental Payment Records"\n'
            '"Alabama","2020","Low concern","1234"\n'
        )
        rows = parse_topic_file(content)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["State"], "Alabama")
        self.assertEqual(rows[0]["DQ Assessment"], "Low concern")

    def test_a_file_with_no_header_yields_nothing_rather_than_guessing(self):
        self.assertEqual(parse_topic_file('"just a title",,,\n'), [])

    def test_files_are_returned_newest_first(self):
        measures = "tafVersionId,measureId,payload\n" + "\n".join(
            f'1,{i},"{{""fileName"": ""TAF_DQ_Supplemental_Pmts_{y}_Release_1.csv"", '
            f'""fileContent"": """"}}"'
            for i, y in enumerate((2016, 2020, 2018))
        )
        found = supplemental_payment_files(measures)
        self.assertEqual([y for y, _, _ in found], [2020, 2018, 2016])

    def test_other_topics_are_ignored(self):
        measures = ('tafVersionId,measureId,payload\n'
                    '1,1,"{""fileName"": ""TAF_DQ_Enroll_CMC_Plans_2016_Release_1.csv"", '
                    '""fileContent"": """"}"')
        self.assertEqual(supplemental_payment_files(measures), [])


class TestUsableDefinition(unittest.TestCase):
    def test_unclassified_does_not_count_as_reporting(self):
        # Unclassified generally means there was not enough data to assess,
        # which for a reporting question is the answer rather than the absence
        # of one. Counting it as usable would turn silence into success.
        for assessment in ("Unclassified", "Unusable", "High concern", "Medium concern"):
            self.assertNotIn(assessment, USABLE_ASSESSMENTS)

    def test_only_low_concern_counts(self):
        self.assertEqual(USABLE_ASSESSMENTS, {"Low concern"})


class TestPublishedView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PUBLISHED.exists():
            raise unittest.SkipTest("readiness view not built; see src.sdp.readiness")
        cls.view = json.loads(PUBLISHED.read_text())

    def test_it_says_what_it_actually_measures(self):
        self.assertIn("supplemental", self.view["measured"].lower())
        self.assertIn("directed payment", self.view["proxy_for"].lower())
        self.assertNotEqual(self.view["measured"], self.view["proxy_for"],
                            "the proxy and the thing it stands for must stay distinct")

    def test_the_caveats_travel_with_the_numbers(self):
        joined = " ".join(self.view["caveats"]).lower()
        self.assertIn("proxy", joined)
        self.assertIn("fee-for-service", joined)
        self.assertIn("data use agreement", joined)
        self.assertIn(str(self.view["newest_year"]), joined,
                      "the caveats must name the year, not leave it to be looked up")

    def test_the_data_is_openly_stale(self):
        # The requirement this proxies for took effect in September 2026. If the
        # newest assessment ever reaches 2026, this test should fail and the
        # framing should be revisited rather than quietly kept.
        self.assertLess(self.view["newest_year"], 2026)

    def test_usable_count_matches_the_state_rows(self):
        counted = sum(1 for s in self.view["states"] if s["reports_usably"])
        self.assertEqual(counted, self.view["states_reporting_usably"])

    def test_most_states_were_not_reporting_usably(self):
        # The substantive finding. If this ever stops being true the headline
        # claim needs rewriting, not the test relaxing.
        total = self.view["states_assessed"]
        self.assertLess(self.view["states_reporting_usably"] / total, 0.5)

    def test_states_carry_their_sdp_dollars_where_known(self):
        joined = [s for s in self.view["states"] if s.get("sdp_amount_usd")]
        self.assertTrue(joined, "the join to the published dataset produced nothing")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestTableauExtract(unittest.TestCase):
    """The extract exists to make the wrong total hard to produce."""

    @classmethod
    def setUpClass(cls):
        import pandas as pd
        path = ROOT / "data" / "published" / "sdp_tableau_extract.csv"
        if not path.exists():
            raise unittest.SkipTest("no extract; see src.sdp.tableau_export")
        cls.df = pd.read_csv(path)

    def test_one_row_per_arrangement_per_rating_period(self):
        key = ["state_code", "payment_type", "provider_class",
               "rating_period_start", "rating_period_end"]
        self.assertFalse(self.df.duplicated(subset=key).any(),
                         "a superseded filing survived and will double count")

    def test_every_row_carries_an_amount(self):
        # A BI tool sums what it is given, so a missing amount would read as a
        # zero. Genuine zeros exist: eight states filed Question 4 as $0. Those
        # are the published values and are kept, flagged rather than dropped.
        self.assertTrue(self.df["amount_usd"].notna().all())
        self.assertTrue((self.df["amount_usd"] >= 0).all())
        zeros = self.df[self.df["amount_usd"] == 0]
        self.assertTrue(zeros["amount_is_zero"].all(),
                        "a zero amount must be flagged so it can be excluded")

    def test_the_year_is_present_for_filtering(self):
        self.assertTrue(self.df["rating_period_year"].notna().all())
        years = self.df["rating_period_year"].astype(int).astype(str)
        self.assertTrue(years.str.match(r"^\d{4}$").all())

    def test_caps_and_spend_are_separate_columns(self):
        self.assertIn("state_grandfathered_cap_usd", self.df.columns)
        self.assertIn("amount_usd", self.df.columns)
        self.assertNotEqual("state_grandfathered_cap_usd", "amount_usd")

    def test_no_denominator_field_exists_to_tempt_a_per_capita_figure(self):
        forbidden = [c for c in self.df.columns
                     if any(w in c.lower() for w in ("member", "enroll", "capita", "pmpm"))]
        self.assertEqual(forbidden, [],
                         "this dataset has no denominators; a field implying one would invite "
                         "a rate it cannot support")
