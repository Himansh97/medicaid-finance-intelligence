"""Read the approved dollar amount out of a preprint PDF.

The amount is in CMS's approval letter, which is the first two or three pages,
not in the state-completed form that follows it. Question 4 of the form asks for
the total dollar amount and appears in every document, but the states' answers do
not survive into the text layer. The letter is the better source anyway: CMS
writes it, so the wording is consistent in a way state-typed entries are not.

Anchoring on the phrase matters more than finding a dollar sign. An amendment
letter cites both the previously approved figure and the new one, so a rule that
takes the first, the last or the largest number on the page will silently return
the wrong one. Each pattern below captures the amount CMS is approving, and an
amount found with no recognised phrase around it is reported as unanchored rather
than used.

Amounts appear as plain digits ($5,102,154), and scaled ($238.60 million,
$1.2 billion). Arizona writes every figure the scaled way, so a digits-only
pattern loses that state entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import re

from pypdf import PdfReader

# The approval letter. Three pages is generous: the letter is usually two, and
# reading one page too many is safer than truncating a letter that runs long.
LETTER_PAGES = 3

_SCALE = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}

_NUMBER = r"\$\s?(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<scale>thousand|million|billion)?"

# Ordered by how directly each states the approved amount. The first to match
# wins, so a letter that both approves an amount and mentions a prior one
# resolves to the approval.
PHRASES: list[tuple[str, str]] = [
    # The connective words vary letter to letter with no apparent pattern:
    # "of", "amount", "up to" each appear and disappear. All the variants mean
    # the same thing, so one tolerant pattern beats five brittle ones.
    ("separate_payment_term",
     r"separate payment term (?:amount )?(?:of )?(?:up to )?" + _NUMBER),
    ("payment_term_is",
     r"payment term for this state directed payment is (?:up to )?" + _NUMBER),
    # "risk based", "risk-based" and "risk-based rate" all occur.
    ("risk_based_adjustment",
     r"risk[- ]based (?:rate )?adjustment (?:of )?(?:up to )?" + _NUMBER),
    ("total_dollar_amount",
     r"total (?:dollar )?amount of (?:up to )?" + _NUMBER),
    ("amount_of_up_to",
     r"(?:in an? )?amount of up to " + _NUMBER),
    ("not_to_exceed",
     r"not to exceed " + _NUMBER),
]

_COMPILED = [(name, re.compile(p, re.I)) for name, p in PHRASES]
_ANY_AMOUNT = re.compile(_NUMBER, re.I)
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class AmountResult:
    """What one PDF yielded, and how confident that is."""

    amount_cents: int | None
    raw_text: str | None
    # Which phrase matched, so a reader can judge the claim rather than trust it.
    matched_phrase: str | None
    # Every distinct amount in the letter. More than one is normal for an
    # amendment and is the reason phrase anchoring exists.
    all_amounts_cents: tuple[int, ...]
    letter_pages_read: int
    issue: str | None

    def as_dict(self) -> dict:
        d = asdict(self)
        d["all_amounts_cents"] = list(d["all_amounts_cents"])
        return d


def to_cents(number: str, scale: str | None) -> int:
    """Money as integer cents, consistent with sql/schema/README.md.

    $238.60 million is 23_860_000_000 cents. Doing this in floats and rounding
    late loses the last cents on nine-figure amounts.
    """
    value = number.replace(",", "")
    if scale:
        # Scaled figures are written to one or two decimal places, so shifting
        # the decimal by the scale keeps the arithmetic exact.
        whole, _, frac = value.partition(".")
        digits = whole + frac
        shift = _SCALE[scale.lower()]
        exponent = len(str(shift)) - 1 - len(frac)
        return int(digits) * (10 ** exponent) * 100
    whole, _, frac = value.partition(".")
    return int(whole) * 100 + int((frac + "00")[:2] or 0)


def letter_text(pdf_path: Path, pages: int = LETTER_PAGES) -> tuple[str, int]:
    """The approval letter as one line of normalised whitespace.

    Line breaks fall mid-sentence in the extracted text, so a phrase like
    "separate payment term of up to" is routinely split across two lines and no
    pattern would match it otherwise.
    """
    reader = PdfReader(pdf_path)
    read = min(pages, len(reader.pages))
    text = " ".join((reader.pages[i].extract_text() or "") for i in range(read))
    return _WHITESPACE.sub(" ", text), read


def extract_amount(pdf_path: Path) -> AmountResult:
    """Find the approved amount, or say why it could not be found."""
    try:
        text, pages_read = letter_text(Path(pdf_path))
    except Exception as exc:  # a corrupt or unreadable download
        return AmountResult(None, None, None, (), 0, f"unreadable PDF: {exc}"[:160])

    all_amounts = tuple(sorted({
        to_cents(m.group("num"), m.group("scale")) for m in _ANY_AMOUNT.finditer(text)
    }))

    # Every phrase that matches, with where it matched.
    #
    # Selection is by position, not by the order the patterns are declared in.
    # About a quarter of letters match more than one phrase, because CMS states
    # the amount in the approval bullet and then restates it further down. The
    # approval bullet comes first, so the earliest match is the approving one.
    # Declaration order would pick whichever pattern happens to sit higher in
    # this file, which is an accident of authorship rather than a fact about the
    # document.
    matches = []
    for name, pattern in _COMPILED:
        m = pattern.search(text)
        if m:
            matches.append((m.start(), name, to_cents(m.group("num"), m.group("scale")),
                            m.group(0).strip()))

    if matches:
        matches.sort()
        _, name, cents, raw = matches[0]

        # Usually the restatement agrees. Where it does not, say so rather than
        # quietly preferring one: a letter that names two different totals is
        # something a person should look at.
        disagreeing = sorted({c for _, _, c, _ in matches} - {cents})
        issue = None
        if disagreeing:
            other = ", ".join(f"${c / 100:,.0f}" for c in disagreeing)
            issue = f"letter states a different amount elsewhere ({other})"

        return AmountResult(
            amount_cents=cents,
            raw_text=raw,
            matched_phrase=name,
            all_amounts_cents=all_amounts,
            letter_pages_read=pages_read,
            issue=issue,
        )

    # Amounts present but none of them attributable. Reporting the candidates
    # without choosing one keeps the decision with a person.
    if all_amounts:
        return AmountResult(
            None, None, None, all_amounts, pages_read,
            f"{len(all_amounts)} amount(s) in the letter, none under a recognised phrase",
        )

    return AmountResult(None, None, None, (), pages_read,
                        "no dollar amount in the approval letter")
