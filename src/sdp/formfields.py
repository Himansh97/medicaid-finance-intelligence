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


# An identifier embedded anywhere in the field, which may also hold prose.
_ID_IN_TEXT = re.compile(r"[A-Za-z]{2}[_\-][A-Za-z.]+[_\-].*?\d{6,9}\s*-\s*\d{6,9}")

# CMS writes the same provider classes two ways: IPH and IP for inpatient
# hospital, OPH and OP for outpatient hospital. Treating those as different
# arrangements manufactures dozens of disagreements that are only spelling.
#
# The trailing digits matter and are kept: OPH1 and OPH2 are distinct classes,
# so the pattern rewrites the prefix and preserves the number.
_CLASS_SYNONYMS = ((r"\bIPH(\d*)", r"IP\1"), (r"\bOPH(\d*)", r"OP\1"))


def _candidates(raw: str | None) -> list[tuple]:
    """Every identifier the field names, reduced to comparable components.

    A field may list more than one, separated by a slash, when one submission
    supersedes another. Agreement with any of them is agreement: the document is
    not contradicting its filename, it is naming its own history.
    """
    found = []
    for chunk in re.split(r"[/;]", str(raw or "")):
        canon = _canonical(chunk)
        if canon and canon not in found:
            found.append(canon)
    return found


def _canonical(raw: str | None) -> tuple | None:
    """Reduce an identifier to comparable components, or None if there is none.

    Comparing raw strings is what the first version of this did, and it counted
    Nv-Fee-Amc-Renewal-20230101-20231231 as disagreeing with
    NV_Fee_AMC_Renewal_20230101-20231231. They are the same arrangement written
    with different separators and casing.
    """
    from src.sdp.identifier import parse  # local import avoids a cycle

    for chunk in re.split(r"[/;]", str(raw or "")):
        hit = _ID_IN_TEXT.search(chunk)
        if not hit:
            continue
        parsed = parse(hit.group(0))
        if not parsed["state_code"]:
            continue
        provider_class = (parsed["provider_class"] or "").upper().replace("_", ".")
        for pattern, replacement in _CLASS_SYNONYMS:
            provider_class = re.sub(pattern, replacement, provider_class)
        return (
            parsed["state_code"],
            parsed["payment_type_normalised"] or "",
            provider_class,
            parsed["review_type_normalised"] or "",
            parsed["rating_period_start"],
            parsed["rating_period_end"],
        )
    return None


_COMPONENTS = ("state", "payment_type", "provider_class",
               "review_type", "rating_period_start", "rating_period_end")


def cross_check_identifier(filename_identifier: str, cms_id: str | None) -> str | None:
    """Compare the filename's identifier with the one inside the document.

    Both sides are parsed into components before comparing, so a difference
    reported here is a difference of substance rather than of punctuation. Where
    they do differ, the message names which components, because a disagreement
    about the rating period means something quite different from one about
    spelling of the provider class.

    A field holding no identifier at all is not a disagreement. Hawaii's reads
    "A", "B" or "C"; one Florida document holds a date range in prose. Those are
    reported as unusable rather than counted as conflicts.
    """
    if not cms_id or not str(cms_id).strip():
        return None

    documents = _candidates(cms_id)
    if not documents:
        return f"CMS ID field holds no identifier: {str(cms_id).strip()[:60]!r}"

    filename = _canonical(filename_identifier)
    if filename is None or filename in documents:
        return None

    # Report against whichever listed identifier is closest, so the message
    # names the smallest real difference rather than an arbitrary one.
    document = min(documents,
                   key=lambda d: sum(1 for a, b in zip(filename, d) if a != b))
    differing = [name for name, a, b in zip(_COMPONENTS, filename, document) if a != b]
    return (f"document disagrees on {', '.join(differing)}: "
            f"filename {filename_identifier.strip()[:50]!r}, "
            f"document {str(cms_id).strip()[:50]!r}")
