"""Read the state's answers out of the preprint's fillable form fields.

Every published preprint is an AcroForm PDF, and the states' answers live in its
named fields. They do not appear in the extracted text layer at all, which is why
reading the page as text finds Question 4's label and never its answer.

This is the better source than the approval letter for two reasons. It covers the
615 documents published with no letter attached, and it carries the federal and
non-federal split that the letter never states.

Three form templates are in circulation and a document may use any of them:

    numbered   4-Text, 4.a-Text, 0.2-CMS ID          the current template
    prose      field names are the question text     older, verbose
    minimal    around six fields, nothing useful     effectively empty

A template this module does not recognise is reported as unknown rather than
treated as an empty answer, because the two mean different things: one is a gap
in this code, the other is a gap in the source.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import re

from pypdf import PdfReader

TEMPLATE_NUMBERED = "numbered"
TEMPLATE_PROSE = "prose"
TEMPLATE_MINIMAL = "minimal"
TEMPLATE_UNKNOWN = "unknown"

# Logical field to the names each template gives it, tried in order.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "state": ("0.1-State",),
    "cms_id": ("0.2-CMS ID",),
    "rating_period_start": ("1-DateStart_af_date",),
    "rating_period_end": ("1-DateEnd_af_date",),
    "requested_start": ("2-DateStart_af_date",),
    "managed_care_programs": ("3-Text",),
    "total_amount": ("4-Text",),
    "federal_share": ("4.a-Text",),
    "nonfederal_share": ("4.b-Text",),
}

# Amounts are free text written by whoever filled the form, so the variety is
# wide: "$310.4 million including the impact of...", "$59.12M", "$510.73 Million",
# "Approximately $3,093.1 million", "$388,500,819  including the im...".
_SCALE_WORD = r"(?P<scale>million|billion|thousand|M\b|B\b|K\b)"
_AMOUNT = re.compile(
    r"\$?\s?(?P<num>\d[\d,]*(?:\.\d+)?)\s*" + _SCALE_WORD + r"?",
    re.I,
)
_SCALE = {"million": 1_000_000, "m": 1_000_000,
          "billion": 1_000_000_000, "b": 1_000_000_000,
          "thousand": 1_000, "k": 1_000}

# No single directed payment arrangement is worth a hundred billion dollars.
# Total annual Medicaid spending across every state is under a trillion, and the
# largest credible arrangement in this corpus is Texas at about $9.1 billion.
#
# The ceiling exists because a state can write a full-precision figure and a
# scale word together, which contradict each other. Pennsylvania filed
# "$9,085,139 million", which read literally is $9 trillion. Whether they meant
# $9,085,139 or $9.085 billion is not knowable from the field, so the value is
# reported as implausible and left unresolved rather than silently divided by a
# thousand to make it look sensible.
IMPLAUSIBLE_ABOVE_CENTS = 100_000_000_000 * 100


@dataclass(frozen=True)
class FormAmount:
    """One money answer, with what it was read from and how sure that is."""

    cents: int | None
    raw: str | None
    # True when the text carried no currency symbol and no scale word, so the
    # unit is a guess. One federal share reads simply "396.97" beside a total of
    # "$510.73 Million", which almost certainly means millions and is not
    # something this module will assert.
    ambiguous_unit: bool
    # True when the figure exceeds any credible size for one arrangement, which
    # in practice means the field combined a full-precision number with a scale
    # word. The parsed value is returned so a person can see what was written.
    implausible: bool
    issue: str | None

    def as_dict(self) -> dict:
        return asdict(self)


def parse_form_amount(text: str | None) -> FormAmount:
    """Read a dollar figure out of free-form text a person typed."""
    if text is None or not str(text).strip():
        return FormAmount(None, None, False, False, "field is empty")

    raw = str(text).strip()
    m = _AMOUNT.search(raw)
    if not m:
        return FormAmount(None, raw, False, False, "no number in the field")

    has_currency = "$" in raw[: m.end()]
    scale_word = (m.group("scale") or "").lower().rstrip(".")
    number = m.group("num").replace(",", "")

    if scale_word:
        whole, _, frac = number.partition(".")
        multiplier = _SCALE[scale_word]
        exponent = len(str(multiplier)) - 1 - len(frac)
        if exponent < 0:
            return FormAmount(None, raw, False, False,
                              "more decimal places than the scale allows")
        cents = int(whole + frac) * (10 ** exponent) * 100
    else:
        whole, _, frac = number.partition(".")
        cents = int(whole) * 100 + int((frac + "00")[:2] or 0)

    # No dollar sign and no scale word: the number is bare and its unit is
    # whatever the reader assumes. Recorded, not resolved.
    ambiguous = not has_currency and not scale_word
    implausible = cents > IMPLAUSIBLE_ABOVE_CENTS

    issue = None
    if implausible:
        issue = (f"${cents / 100:,.0f} exceeds any credible arrangement size; the "
                 "field appears to combine a full figure with a scale word")
    elif ambiguous:
        issue = "no currency symbol or scale word; unit assumed"

    return FormAmount(cents, raw, ambiguous, implausible, issue)


@dataclass(frozen=True)
class FormRecord:
    template: str
    field_count: int
    state: str | None
    cms_id: str | None
    rating_period_start: str | None
    rating_period_end: str | None
    managed_care_programs: str | None
    total: FormAmount
    federal_share: FormAmount
    nonfederal_share: FormAmount
    issue: str | None

    def as_dict(self) -> dict:
        d = asdict(self)
        for key in ("total", "federal_share", "nonfederal_share"):
            d[key] = self.__getattribute__(key).as_dict()
        return d


def _value(fields: dict, logical: str) -> str | None:
    for name in FIELD_ALIASES.get(logical, ()):
        entry = fields.get(name)
        if entry is None:
            continue
        value = entry.get("/V")
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def detect_template(fields: dict) -> str:
    if "4-Text" in fields or "0.2-CMS ID" in fields:
        return TEMPLATE_NUMBERED
    if len(fields) <= 12:
        return TEMPLATE_MINIMAL
    # Field names that are the question text itself.
    if any(len(name) > 40 for name in fields):
        return TEMPLATE_PROSE
    return TEMPLATE_UNKNOWN


_EMPTY = FormAmount(None, None, False, False, "not read")


def read_form(pdf_path: Path) -> FormRecord:
    """Extract the answers, or say which template stopped us."""
    try:
        fields = PdfReader(Path(pdf_path)).get_fields() or {}
    except Exception as exc:
        return FormRecord(TEMPLATE_UNKNOWN, 0, None, None, None, None, None,
                          _EMPTY, _EMPTY, _EMPTY, f"unreadable PDF: {exc}"[:160])

    template = detect_template(fields)
    if template is not TEMPLATE_NUMBERED:
        return FormRecord(template, len(fields), None, None, None, None, None,
                          _EMPTY, _EMPTY, _EMPTY,
                          f"{template} template is not yet mapped to logical fields")

    return FormRecord(
        template=template,
        field_count=len(fields),
        state=_value(fields, "state"),
        cms_id=_value(fields, "cms_id"),
        rating_period_start=_value(fields, "rating_period_start"),
        rating_period_end=_value(fields, "rating_period_end"),
        managed_care_programs=_value(fields, "managed_care_programs"),
        total=parse_form_amount(_value(fields, "total_amount")),
        federal_share=parse_form_amount(_value(fields, "federal_share")),
        nonfederal_share=parse_form_amount(_value(fields, "nonfederal_share")),
        issue=None,
    )


def cross_check_identifier(filename_identifier: str, cms_id: str | None) -> str | None:
    """Compare the identifier in the filename with the one inside the document.

    They disagree often enough to matter, and the disagreement is a finding for a
    person to resolve rather than something to paper over. One Arizona document
    is filed as AZ_Fee_AMC.PC.SP_Renewal_... while its own CMS ID field reads
    AZ_Fee_AMC_Renewal_..., naming a different provider class.
    """
    if not cms_id:
        return None
    # A field may list several ids separated by a slash when one submission
    # supersedes another. Agreement with any of them is agreement.
    candidates = [part.strip() for part in re.split(r"[/;]", cms_id) if part.strip()]
    target = filename_identifier.strip()
    if any(c == target for c in candidates):
        return None
    return f"filename says {target!r}; document says {cms_id.strip()[:80]!r}"
