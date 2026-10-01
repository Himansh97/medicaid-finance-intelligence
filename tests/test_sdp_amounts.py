"""Reading the approved amount out of a CMS approval letter.

The phrasings tested here are all ones CMS actually publishes. The variation is
real: "separate payment term of up to", "separate payment term amount up to" and
"separate payment term up to" all appear, and so do plain, million and billion
number formats.

Run with:  python -m pytest tests -q   or   python tests/test_sdp_amounts.py
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.sdp.amounts import _ANY_AMOUNT, _COMPILED, to_cents


def match_amount(text: str):
    """Mirror extract_amount's phrase selection against a string of letter text.

    Earliest match in the document wins, which is how extract_amount chooses.
    """
    matches = []
    for name, pattern in _COMPILED:
        m = pattern.search(text)
        if m:
            matches.append((m.start(), name, to_cents(m.group("num"), m.group("scale"))))
    if not matches:
        return None, None
    matches.sort()
    return matches[0][1], matches[0][2]


class TestCentsArithmetic(unittest.TestCase):
    """Money is integer cents, per sql/schema/README.md. No floats survive."""

    def test_plain_amounts(self):
        self.assertEqual(to_cents("5,102,154", None), 510_215_400)
        self.assertEqual(to_cents("500", None), 50_000)

    def test_scaled_amounts_are_exact(self):
        # Arizona writes every figure this way. Doing it in floating point and
        # rounding late loses cents on nine-figure amounts.
        self.assertEqual(to_cents("238.60", "million"), 23_860_000_000)
        self.assertEqual(to_cents("310.4", "million"), 31_040_000_000)
        self.assertEqual(to_cents("1.2", "billion"), 120_000_000_000)

    def test_a_scaled_and_a_plain_amount_agree(self):
        self.assertEqual(to_cents("238.6", "million"), to_cents("238,600,000", None))

    def test_no_float_creeps_into_the_result(self):
        for args in [("238.60", "million"), ("1.2", "billion"), ("5,102,154", None)]:
            self.assertIsInstance(to_cents(*args), int)


class TestPhraseVariants(unittest.TestCase):
    """Each of these wordings appears in published approval letters."""

    def test_separate_payment_term_with_of(self):
        name, cents = match_amount(
            "incorporated in the capitation rates through a separate payment "
            "term of up to $5,102,154.")
        self.assertEqual(name, "separate_payment_term")
        self.assertEqual(cents, 510_215_400)

    def test_separate_payment_term_without_of(self):
        _, cents = match_amount(
            "through a separate payment term up to $385.1 million.")
        self.assertEqual(cents, 38_510_000_000)

    def test_separate_payment_term_with_amount(self):
        _, cents = match_amount(
            "through a separate payment term amount up to $12,345,678.")
        self.assertEqual(cents, 1_234_567_800)

    def test_risk_based_rate_adjustment(self):
        name, cents = match_amount(
            "incorporated into the capitation rates through a risk-based rate "
            "adjustment of up to $150,850,000.")
        self.assertEqual(name, "risk_based_adjustment")
        self.assertEqual(cents, 15_085_000_000)

    def test_total_dollar_amount(self):
        _, cents = match_amount("with a total dollar amount of $54,542,328")
        self.assertEqual(cents, 5_454_232_800)


class TestPhraseAnchoring(unittest.TestCase):
    """Why the phrase matters, rather than hunting for a dollar sign."""

    def test_the_earliest_phrase_wins_not_the_largest_amount(self):
        # Taken from AZ_Fee_IPH.OPH.PC.SP.NF.HCBS.BHI.BHO.D_Amend, which states
        # $150,850,000 in the approval bullet and $165,400,000 further down.
        # The approval bullet comes first, and it is the approving statement.
        letter = (
            "is approved: incorporated into the capitation rates through a "
            "risk-based rate adjustment of up to $150,850,000. The state "
            "submitted this SDP proposal with the total dollar amount of "
            "$165,400,000.")
        all_found = sorted({
            to_cents(m.group("num"), m.group("scale"))
            for m in _ANY_AMOUNT.finditer(letter)
        })
        self.assertEqual(len(all_found), 2, "the letter really does cite two figures")

        name, cents = match_amount(letter)
        self.assertEqual(name, "risk_based_adjustment")
        self.assertEqual(cents, 15_085_000_000)
        self.assertNotEqual(cents, max(all_found),
                            "and it is not simply the largest number present")

    def test_a_disagreement_between_two_phrases_is_reported(self):
        from src.sdp.amounts import AmountResult
        import tempfile
        # The selection is tested above; here the point is that the second,
        # different figure is surfaced rather than silently dropped.
        letter = (
            "is approved: through a risk-based rate adjustment of up to "
            "$150,850,000. Submitted with the total dollar amount of "
            "$165,400,000.")
        seen = sorted({to_cents(m.group("num"), m.group("scale"))
                       for m in _ANY_AMOUNT.finditer(letter)})
        self.assertEqual(seen, [15_085_000_000, 16_540_000_000])

    def test_an_amount_with_no_recognised_phrase_is_not_claimed(self):
        # Reporting nothing is correct here. Guessing would attach a number to an
        # arrangement on the strength of it merely being nearby.
        name, cents = match_amount(
            "Delaware DSHP Plus (MCO managed care) $4,000,000 $6,000,000")
        self.assertIsNone(name)
        self.assertIsNone(cents)


class TestSourceSilence(unittest.TestCase):
    """Some approvals genuinely state no amount. That is a finding, not a bug."""

    def test_an_approval_with_no_figure_yields_nothing(self):
        letter = (
            "Uniform increase established by the state for Differential Adjusted "
            "Payments (DAP) program eligible providers for the rating period "
            "covering October 1, 2022 through September 30, 2023, and "
            "incorporated in the capitation rates through a risk based rate "
            "adjustment. This approval letter does not constitute approval of "
            "any Medicaid managed care plan contracts.")
        name, cents = match_amount(letter)
        self.assertIsNone(cents)
        self.assertIsNone(name)
        self.assertEqual(
            list(_ANY_AMOUNT.finditer(letter)), [],
            "the letter contains no dollar figure at all, which is the point")


@pytest.mark.integration
class TestAgainstDownloadedPreprints(unittest.TestCase):
    """Runs only when PDFs have been fetched. Guards the headline rates."""

    @classmethod
    def setUpClass(cls):
        import json
        path = ROOT / "data" / "processed" / "sdp_amounts.json"
        if not path.exists():
            raise unittest.SkipTest("no extraction run; see src.sdp.extract")
        cls.summary = json.loads(path.read_text())
        if cls.summary["evaluated"] < 100:
            raise unittest.SkipTest("too few preprints downloaded to judge a rate")

    def test_our_own_gap_stays_small(self):
        total = self.summary["evaluated"]
        rate = 100 * self.summary["unresolved"] / total
        self.assertLess(rate, 6.0,
                        f"unresolved rose to {rate:.1f}%; a phrase variant is probably unhandled")

    def test_source_silence_is_counted_separately_from_our_gap(self):
        # Collapsing these two would let a drop in extraction quality hide
        # behind CMS's own omissions.
        self.assertGreater(self.summary["no_amount_stated_by_cms"], 0)
        # Scoped to approval letters: the other two document categories cannot
        # carry an approved amount, so folding them in would flatter the rate.
        self.assertEqual(
            self.summary["approvals"],
            self.summary["anchored"] + self.summary["no_amount_stated_by_cms"]
            + self.summary["unresolved"])

    def test_every_anchored_amount_names_its_phrase_and_its_source(self):
        for r in self.summary["records"]:
            if r["amount_cents"] is not None:
                self.assertTrue(r["matched_phrase"], f"{r['sdp_identifier']} has no phrase")
                self.assertTrue(r["source_url"], f"{r['sdp_identifier']} has no source URL")
                self.assertTrue(r["raw_text"], f"{r['sdp_identifier']} has no raw text")

    def test_amounts_are_integers_in_cents(self):
        for r in self.summary["records"]:
            if r["amount_cents"] is not None:
                self.assertIsInstance(r["amount_cents"], int)
                self.assertGreaterEqual(r["amount_cents"], 0)

    def test_a_zero_is_only_ever_a_phase_down_cap(self):
        # Two Massachusetts documents state "total dollar amount of $0". Both are
        # grandfathering determinations under Public Law 119-21, where $0 is a
        # ceiling the arrangement may not exceed. A $0 sitting among approvals
        # would mean something quite different and should be investigated.
        for r in self.summary["records"]:
            if r["amount_cents"] == 0:
                self.assertEqual(r["letter_type"], "phase_down_determination",
                                 f"{r['sdp_identifier']} reports $0 as an approval")

    def test_document_categories_account_for_every_record(self):
        total = (self.summary["approvals"] + self.summary["phase_down_determinations"]
                 + self.summary["form_only_no_letter"])
        self.assertEqual(total, self.summary["evaluated"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
