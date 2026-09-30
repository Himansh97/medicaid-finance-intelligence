"""Reading state answers out of the preprint's fillable form fields.

Every string tested here was typed into a real published preprint by whoever
filled it in. The variety is not hypothetical.

Run with:  python -m pytest tests -q   or   python tests/test_sdp_formfields.py
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

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
        self.assertIn("AZ_Fee_AMC.PC.SP_Renewal", issue)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
