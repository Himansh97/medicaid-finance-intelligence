"""Reading state answers out of the preprint's fillable form fields.

Every string tested here was typed into a real published preprint by whoever
filled it in. The variety is not hypothetical.

Run with:  python -m pytest tests -q   or   python tests/test_sdp_formfields.py
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.sdp.formfields import (
    IMPLAUSIBLE_ABOVE_CENTS, TEMPLATE_MINIMAL, TEMPLATE_NUMBERED, TEMPLATE_PROSE,
    cross_check_identifier, detect_template, parse_form_amount,
)


class TestAmountFormats(unittest.TestCase):
    """States write the same quantity a dozen different ways."""

    def test_scale_words_and_suffixes_agree(self):
        for text in ("$310.4 million", "$310.4 Million", "$310.4M", "$310.4 M"):
            self.assertEqual(parse_form_amount(text).cents, 31_040_000_000,
                             f"{text!r} should be $310,400,000")

    def test_plain_dollars(self):
        self.assertEqual(parse_form_amount("$388,500,819").cents, 38_850_081_900)

    def test_prose_around_the_number_is_ignored(self):
        for text in ("$95,851,058 (including the impact of the increase)",
                     "Approximately $3,093.1 million",
                     "$59.12M including the impact of prior year"):
            self.assertIsNotNone(parse_form_amount(text).cents, f"{text!r} failed")

    def test_approximately_does_not_change_the_number(self):
        self.assertEqual(parse_form_amount("Approximately $3,093.1 million").cents,
                         parse_form_amount("$3,093.1 million").cents)

    def test_cents_are_exact_integers(self):
        for text in ("$310.4 million", "$1.2 billion", "$388,500,819"):
            cents = parse_form_amount(text).cents
            self.assertIsInstance(cents, int)

    def test_an_empty_field_is_not_a_zero(self):
        # A blank answer and an answer of zero mean entirely different things.
        for text in ("", "   ", None):
            r = parse_form_amount(text)
            self.assertIsNone(r.cents)
            self.assertEqual(r.issue, "field is empty")


class TestAmbiguity(unittest.TestCase):
    def test_a_bare_number_is_flagged_rather_than_assumed(self):
        # One federal share reads "396.97" beside a total of "$510.73 Million".
        # It almost certainly means millions. Almost certainly is not good enough
        # to publish, so the unit is recorded as assumed.
        r = parse_form_amount("396.97")
        self.assertTrue(r.ambiguous_unit)
        self.assertIsNotNone(r.issue)

    def test_a_currency_symbol_removes_the_ambiguity(self):
        self.assertFalse(parse_form_amount("$396.97").ambiguous_unit)

    def test_a_scale_word_removes_the_ambiguity(self):
        self.assertFalse(parse_form_amount("396.97 million").ambiguous_unit)


class TestPlausibility(unittest.TestCase):
    def test_a_full_figure_with_a_scale_word_is_flagged(self):
        # Pennsylvania filed "$9,085,139 million". Read literally that is $9
        # trillion, roughly ten times total annual US Medicaid spending.
        r = parse_form_amount("$9,085,139 million")
        self.assertTrue(r.implausible)
        self.assertIsNotNone(r.cents, "the parsed value is still returned to be seen")
        self.assertIn("scale word", r.issue)

    def test_the_largest_credible_arrangement_is_not_flagged(self):
        # Texas at about $9.1 billion is the largest genuine arrangement here.
        r = parse_form_amount("$9,148,763,142")
        self.assertFalse(r.implausible)
        self.assertLess(r.cents, IMPLAUSIBLE_ABOVE_CENTS)

    def test_the_ceiling_sits_above_real_data_and_below_the_error(self):
        self.assertLess(9_148_763_142 * 100, IMPLAUSIBLE_ABOVE_CENTS)
        self.assertGreater(9_085_139_000_000 * 100, IMPLAUSIBLE_ABOVE_CENTS)


class TestTemplateDetection(unittest.TestCase):
    def test_the_numbered_template(self):
        self.assertEqual(detect_template({"4-Text": {}, "0.2-CMS ID": {}}),
                         TEMPLATE_NUMBERED)

    def test_the_minimal_template(self):
        self.assertEqual(detect_template({f"f{i}": {} for i in range(6)}),
                         TEMPLATE_MINIMAL)

    def test_the_prose_template(self):
        fields = {f"f{i}": {} for i in range(40)}
        fields["Total Amounts Transferred by This Entity i and the date of transfer"] = {}
        self.assertEqual(detect_template(fields), TEMPLATE_PROSE)


class TestIdentifierCrossCheck(unittest.TestCase):
    """The filename and the document disagree more often than one would hope."""

    def test_punctuation_and_casing_are_not_disagreements(self):
        # The first version of this check compared raw strings and counted these
        # as conflicts. They are the same arrangement written differently, and
        # reporting them inflated the headline by roughly half.
        for filename, document in [
            ("Nv-Fee-Amc-Renewal-20230101-20231231",
             "NV_Fee_AMC_Renewal_20230101-20231231"),
            ("FL_Fee_IPH.OPH3_Renewal_20221001-20230930",
             "FL_Fee_IPH.OPH3_ Renewal_20221001-20230930"),
        ]:
            self.assertIsNone(cross_check_identifier(filename, document),
                              f"{filename} vs {document} is not a real disagreement")

    def test_iph_and_ip_name_the_same_provider_class(self):
        # CMS writes inpatient hospital both ways. Treating them as different
        # arrangements manufactured a dozen conflicts that were only spelling.
        self.assertIsNone(cross_check_identifier(
            "AZ_Fee_IPH.OPH1_Renewal_20231001-20240930",
            "AZ_Fee_IP.OP1_Renewal_20231001-20240930"))

    def test_but_the_class_number_still_matters(self):
        # OPH1 and OPH2 are genuinely different classes, so canonicalising the
        # prefix must not swallow the digit.
        self.assertIsNotNone(cross_check_identifier(
            "AZ_Fee_IPH.OPH1_Renewal_20231001-20240930",
            "AZ_Fee_IP.OP2_Renewal_20231001-20240930"))

    def test_a_field_with_no_identifier_is_not_a_conflict(self):
        # Hawaii's CMS ID field reads "A", "B" or "C".
        issue = cross_check_identifier("HI_VBP.Fee_NF_Renewal_20240101-20241231", "C")
        self.assertIsNotNone(issue)
        self.assertIn("holds no identifier", issue)
        self.assertNotIn("disagrees", issue)

    def test_an_identifier_buried_in_prose_is_found(self):
        self.assertIsNone(cross_check_identifier(
            "NM_VBP_NF2_Renewal_20230101-20231231",
            "Healthcare Quality Surcharge (NM_VBP_NF2_Renewal_20230101-20231231)"))

    def test_a_real_disagreement_names_the_component(self):
        issue = cross_check_identifier(
            "VA_Fee_Oth_Renewal_20240701-20250630",
            "VA_Fee_Oth_Renewal_20220701-20230630")
        self.assertIn("rating_period_start", issue)
        self.assertIn("rating_period_end", issue)

    def test_agreement_is_silent(self):
        self.assertIsNone(cross_check_identifier(
            "MO_Fee_BHO_Renewal_20250701-20260630",
            "MO_Fee_BHO_Renewal_20250701-20260630"))

    def test_a_different_provider_class_is_reported(self):
        # Filed as AMC.PC.SP, describes itself as AMC.
        issue = cross_check_identifier(
            "AZ_Fee_AMC.PC.SP_Renewal_20241001-20250930",
            "AZ_Fee_AMC_Renewal_20241001-20250930")
        self.assertIsNotNone(issue)
        self.assertIn("provider_class", issue)

    def test_a_different_rating_period_is_reported(self):
        # Filed for 2022-2023, describes itself as 2021-2022. One is wrong, and
        # which one is not something this code can decide.
        self.assertIsNotNone(cross_check_identifier(
            "AZ_Fee_HCBS.BHO1_Renewal_20221001-20230930",
            "AZ_Fee_HCBS.BHO1_Renewal_20211001-20220930"))

    def test_a_field_listing_several_ids_matches_any_of_them(self):
        # One submission superseding another lists both, separated by a slash.
        self.assertIsNone(cross_check_identifier(
            "AZ_Fee_AMC_Renewal_20221001-20230930",
            "AZ_Fee_AMC_Amend_20221001-20230930 /AZ_Fee_AMC_Renewal_20221001-20230930"))

    def test_a_missing_cms_id_is_not_a_disagreement(self):
        self.assertIsNone(cross_check_identifier("MO_Fee_BHO_Renewal_20250701-20260630", None))
        self.assertIsNone(cross_check_identifier("MO_Fee_BHO_Renewal_20250701-20260630", ""))


class TestPublishedDataset(unittest.TestCase):
    """Runs only when the dataset has been published. Guards its shape."""

    @classmethod
    def setUpClass(cls):
        import pandas as pd
        path = ROOT / "data" / "published" / "sdp_arrangements.csv"
        if not path.exists():
            raise unittest.SkipTest("nothing published; see src.sdp.publish")
        cls.df = pd.read_csv(path)

    @pytest.mark.integration
    def test_every_listed_preprint_gets_a_row(self):
        # Including the ones with no amount. A file containing only successful
        # extractions would misstate its own coverage.
        import json
        path = ROOT / "data" / "raw" / "sdp" / "manifest.json"
        if not path.exists():
            self.skipTest("optional integration check requires the downloaded CMS manifest")
        manifest = json.loads(path.read_text())
        self.assertEqual(len(self.df), manifest["count"])

    def test_the_identifier_is_unique(self):
        self.assertEqual(self.df["sdp_identifier"].nunique(), len(self.df))

    def test_every_publishable_amount_carries_its_provenance(self):
        rows = self.df[self.df["amount_is_publishable"]]
        self.assertTrue(rows["source_url"].notna().all())
        self.assertTrue(rows["source_sha256"].notna().all())
        self.assertTrue(rows["extraction_version"].notna().all())

    def test_publishable_excludes_assumed_units_and_implausible_figures(self):
        rows = self.df[self.df["amount_is_publishable"]]
        self.assertFalse(rows["amount_unit_assumed"].any())
        self.assertFalse(rows["amount_implausible"].any())

    def test_unusable_id_fields_are_counted_apart_from_conflicts(self):
        conflicts = self.df["identifier_mismatch"].notna()
        unusable = self.df["cms_id_unusable"].notna()
        self.assertFalse((conflicts & unusable).any(),
                         "a row cannot be both a conflict and an unusable field")
        self.assertGreater(unusable.sum(), 0)

    def test_the_two_independent_readings_mostly_agree(self):
        both = self.df[self.df["total_amount_cents"].notna()
                       & self.df["letter_amount_cents"].notna()
                       & ~self.df["amount_implausible"]
                       & ~self.df["amount_unit_assumed"]]
        agree = (both["total_amount_cents"] == both["letter_amount_cents"]).mean()
        self.assertGreater(
            agree, 0.85,
            f"form and letter agreement fell to {100 * agree:.1f}%; one reading has drifted")

    def test_a_cap_is_only_ever_recorded_on_a_phase_down_document(self):
        capped = self.df[self.df["grandfathered_cap_cents"].notna()]
        self.assertGreater(len(capped), 0)
        self.assertTrue((capped["document_type"] == "phase_down_determination").all())

    def test_a_cap_never_becomes_the_published_amount(self):
        # A phase-down document may still carry a legitimate Q4 total in its
        # form, and that is a real projection. What must never happen is the
        # letter's ceiling being read as an approved amount.
        phase_down = self.df[self.df["document_type"] == "phase_down_determination"]
        self.assertFalse((phase_down["amount_source"] == "approval_letter").any())

    def test_every_publishable_row_names_its_source(self):
        rows = self.df[self.df["amount_is_publishable"]]
        self.assertTrue(rows["amount_source"].notna().all())
        self.assertTrue(set(rows["amount_source"]) <= {"form_field", "approval_letter"})

    def test_the_letter_fallback_only_fires_where_the_form_gave_nothing(self):
        fallback = self.df[self.df["amount_source"] == "approval_letter"]
        self.assertTrue(fallback["total_amount_cents"].isna().all()
                        | ~fallback["amount_is_publishable"].isna().all())

    def test_usd_is_consistent_with_cents(self):
        rows = self.df[self.df["total_amount_cents"].notna()]
        self.assertTrue(((rows["total_amount_cents"] / 100
                          - rows["total_amount_usd"]).abs() < 0.005).all())


if __name__ == "__main__":
    unittest.main(verbosity=2)
