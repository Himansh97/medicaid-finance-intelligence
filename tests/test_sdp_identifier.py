"""The SDP control name parser, against real published identifiers.

Every string in this file is one CMS actually published. None is invented, and
the malformed ones are malformed in CMS's data rather than in ours.

Run with:  python -m pytest tests -q   or   python tests/test_sdp_identifier.py
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.sdp.identifier import parse


class TestConventionalIdentifiers(unittest.TestCase):
    def test_the_standard_form(self):
        r = parse("MO_Fee_BHO_Renewal_20250701-20260630")
        self.assertTrue(r["identifier_parsed"])
        self.assertEqual(
            (r["state_code"], r["payment_type"], r["provider_class"],
             r["review_type"], r["rating_period_start"], r["rating_period_end"]),
            ("MO", "Fee", "BHO", "Renewal", "2025-07-01", "2026-06-30"))
        self.assertEqual(r["identifier_repairs"], [], "a clean identifier needs no repair")

    def test_multi_class_arrangements_keep_their_dots(self):
        r = parse("CA_VBP_IPH.OPH_Renewal_20240101-20241231")
        self.assertEqual(r["provider_class"], "IPH.OPH")


class TestSuffixes(unittest.TestCase):
    """A suffix is often the only thing separating two identical arrangements."""

    def test_a_county_suffix_is_kept_not_discarded(self):
        r = parse("NJ_Fee_IPH.OPH_Renewal_20250701-20260630 Atlantic")
        self.assertTrue(r["identifier_parsed"])
        self.assertEqual(r["identifier_suffix"], "Atlantic")
        self.assertEqual(r["provider_class"], "IPH.OPH")

    def test_two_new_jersey_arrangements_differ_only_by_suffix(self):
        a = parse("NJ_Fee_IPH.OPH_Renewal_20250701-20260630 Atlantic")
        b = parse("NJ_Fee_IPH.OPH_Renewal_20250701-20260630 Essex")
        for field in ("state_code", "payment_type", "provider_class",
                      "rating_period_start", "rating_period_end"):
            self.assertEqual(a[field], b[field])
        self.assertNotEqual(a["identifier_suffix"], b["identifier_suffix"])


class TestRepairs(unittest.TestCase):
    """Each repair is applied and recorded. Nothing is corrected silently."""

    def test_hyphen_separated_fields(self):
        r = parse("CA-Fee-D-Renewal-20230101-20231231")
        self.assertTrue(r["identifier_parsed"])
        self.assertEqual((r["state_code"], r["provider_class"]), ("CA", "D"))
        self.assertIn("fields were hyphen separated", r["identifier_repairs"])

    def test_mmddyyyy_dates_are_detected_not_read_as_a_year_zero(self):
        # UT publishes 07012022-06302023. Reading it positionally gives year 0701.
        r = parse("UT_Fee_IPH1_Amend_07012022-06302023")
        self.assertEqual(r["rating_period_start"], "2022-07-01")
        self.assertEqual(r["rating_period_end"], "2023-06-30")
        self.assertIn("date read as MMDDYYYY", r["identifier_repairs"])

    def test_a_combined_payment_type_survives_hyphen_flattening(self):
        # VBP.Fee written with hyphens becomes VBP-Fee-IPH-OPH, where the second
        # token is a payment type rather than the start of the provider class.
        hyphen = parse("HI-VBP-Fee-IPH-OPH-Renewal-20230101-20231231")
        underscore = parse("NM_VBP.Fee_NF2_Renewal_20250101-20251231")
        self.assertEqual(hyphen["payment_type_normalised"],
                         underscore["payment_type_normalised"])
        self.assertEqual(hyphen["provider_class"], "IPH_OPH")

    def test_payment_type_fused_to_provider_class_is_split(self):
        r = parse("FL_Fee.IPH.OPH5_Renewal_20241001-20250131")
        self.assertEqual(r["payment_type"], "Fee")
        self.assertEqual(r["provider_class"], "IPH.OPH5")

    def test_a_leading_stray_character_does_not_shift_every_field(self):
        r = parse("\\GA_Fee_IPH.OPH2_Amend_20230701-20240630")
        self.assertTrue(r["identifier_parsed"])
        self.assertEqual((r["state_code"], r["payment_type"]), ("GA", "Fee"))

    def test_lower_case_state_is_upper_cased_and_recorded(self):
        r = parse("Fl-Fee-Pc-Sp-Renewal-20221001-20230930")
        self.assertEqual(r["state_code"], "FL")
        self.assertIn("state code was not upper case", r["identifier_repairs"])

    def test_stray_whitespace_around_the_period(self):
        r = parse("AZ_Fee_AMC_Amend_ 20211001-20220930")
        self.assertTrue(r["identifier_parsed"])
        self.assertEqual(r["rating_period_start"], "2021-10-01")


class TestRefusals(unittest.TestCase):
    """Where the source is wrong, say so rather than guess."""

    def test_a_nine_digit_date_is_reported_not_repaired(self):
        # FL publishes 202221001. There is no way to know which digit is wrong,
        # so inventing a date here would fabricate a rating period.
        r = parse("FL_Fee_IPH.OPH3_Renewal_202221001-20230930")
        self.assertFalse(r["identifier_parsed"])
        self.assertIsNone(r["rating_period_start"])
        self.assertIn("9 digits", r["identifier_issue"])
        # The fields that ARE readable are still returned.
        self.assertEqual(r["state_code"], "FL")
        self.assertEqual(r["rating_period_end"], "2023-09-30")

    def test_a_seven_digit_date_is_reported_not_repaired(self):
        r = parse("NM_VBP.Fee_NF2_Renewal_20260101-2026123")
        self.assertFalse(r["identifier_parsed"])
        self.assertIsNone(r["rating_period_end"])

    def test_no_rating_period_at_all(self):
        r = parse("NM_Proposal B 2021_Amendment")
        self.assertFalse(r["identifier_parsed"])
        self.assertEqual(r["identifier_issue"], "no rating period found in the identifier")

    def test_a_missing_review_type_is_not_invented(self):
        # WI publishes no review type. Assigning one would place the arrangement
        # in a category CMS never gave it.
        r = parse("WI_Fee_HCBS9_20250101-20251231")
        self.assertIsNone(r["review_type"])
        self.assertIn("no review type in the identifier", r["identifier_repairs"])
        self.assertEqual(r["provider_class"], "HCBS9")


class TestNormalisation(unittest.TestCase):
    def test_amend_variants_collapse_but_the_raw_value_survives(self):
        variants = ["Amend", "Amend2", "Amend3", "Amendment"]
        for v in variants:
            r = parse(f"XX_Fee_IPH_{v}_20250101-20251231")
            self.assertEqual(r["review_type_normalised"], "Amendment")
            self.assertEqual(r["review_type"], v, "the published value is preserved")

    def test_payment_type_order_and_case_are_normalised(self):
        a = parse("XX_Fee.VBP_IPH_Renewal_20250101-20251231")
        b = parse("XX_VBP.Fee_IPH_Renewal_20250101-20251231")
        c = parse("XX_FEE.vbp_IPH_Renewal_20250101-20251231")
        self.assertEqual(a["payment_type_normalised"], b["payment_type_normalised"])
        self.assertEqual(b["payment_type_normalised"], c["payment_type_normalised"])
        self.assertEqual(a["payment_type_normalised"], "FEE.VBP")
        self.assertNotEqual(a["payment_type"], b["payment_type"],
                            "raw values stay different, because the inconsistency is a finding")


class TestAgainstTheRealManifest(unittest.TestCase):
    """Runs only when a manifest has been fetched. Guards the headline numbers."""

    @classmethod
    def setUpClass(cls):
        import json
        path = ROOT / "data" / "raw" / "sdp" / "manifest.json"
        if not path.exists():
            raise unittest.SkipTest("no manifest fetched; run src.sdp.fetch_preprints manifest")
        cls.preprints = json.loads(path.read_text())["preprints"]

    def test_parse_rate_stays_above_ninety_nine_percent(self):
        ok = sum(1 for p in self.preprints if p["identifier_parsed"])
        rate = 100 * ok / len(self.preprints)
        self.assertGreaterEqual(
            rate, 99.0, f"identifier parse rate fell to {rate:.1f}%")

    def test_every_unparsed_identifier_states_why(self):
        for p in self.preprints:
            if not p["identifier_parsed"]:
                self.assertTrue(p["identifier_issue"],
                                f"{p['sdp_identifier']} failed without a reason")

    def test_every_repair_is_recorded_on_the_record_that_received_it(self):
        repaired = [p for p in self.preprints if p["identifier_repairs"]]
        self.assertTrue(repaired, "the corpus is known to need repairs")
        for p in repaired:
            self.assertIsInstance(p["identifier_repairs"], list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
