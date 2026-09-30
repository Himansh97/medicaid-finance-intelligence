"""Parse the CMS state directed payment control name.

The convention is STATE_PAYMENTTYPE_PROVIDERCLASS_REVIEWTYPE_START-END, for
example MO_Fee_BHO_Renewal_20250701-20260630. About 95% of published identifiers
follow it. The rest do not, in at least seven distinct ways, all of them present
in CMS's own published data:

    hyphens instead of underscores   CA-Fee-D-Renewal-20230101-20231231
    stray whitespace                 AZ_Fee_AMC_Amend_ 20211001-20220930
    MMDDYYYY instead of YYYYMMDD     UT_Fee_IPH1_Amend_07012022-06302023
    a mistyped date                  FL_..._Renewal_202221001-20230930
    no review type at all            WI_Fee_HCBS9_20250101-20251231
    class fused to payment type      FL_Fee.IPH.OPH5_Renewal_...
    inconsistent casing              Fl-Fee-Pc-Sp-Renewal-...

Every repair is recorded on the record that received it, so a reader can see
exactly what was changed and undo it. Nothing is silently corrected: a value this
module could not resolve stays None and carries a reason, because an identifier
that is quietly guessed at is worse than one that is openly unknown.
"""

from __future__ import annotations

import re

# Fields in fixed order once separators are normalised.
_RANGE = re.compile(r"(?P<start>\d{6,9})\s*-\s*(?P<end>\d{6,9})\s*$")
_YEAR_RANGE = re.compile(r"(?P<start>(?:19|20)\d{2})\s*-\s*(?P<end>(?:19|20)\d{2})\s*$")
_STATE = re.compile(r"^(?P<state>[A-Za-z]{2})[_\-]")

# Review types CMS actually uses, lowercased for matching. Amend, Amend1, Amend2,
# Amend3 and Amendment all occur and all mean an amendment; the distinction is
# preserved in the raw value and collapsed only in review_type_normalised.
_REVIEW_WORDS = {"new", "renewal", "amend", "amendment", "amend1", "amend2", "amend3"}

# Payment types CMS uses. "Proposal" appears once, in an early Florida identifier.
_PAYMENT_WORDS = {"fee", "vbp", "proposal"}


def _plausible_year(text: str) -> bool:
    return len(text) == 4 and text.isdigit() and 1990 <= int(text) <= 2100


def _iso_date(token: str) -> tuple[str | None, str | None]:
    """Return (ISO date, repair applied) for one date token.

    YYYYMMDD is the convention. MMDDYYYY appears in Utah's identifiers and is
    detected by asking whether the leading four digits could be a year at all,
    which they cannot be when they start with a month.
    """
    token = token.strip()
    if not token.isdigit():
        return None, None

    if len(token) == 8:
        if _plausible_year(token[:4]):
            return f"{token[:4]}-{token[4:6]}-{token[6:8]}", None
        if _plausible_year(token[4:]):
            # 07012022 is 1 July 2022, not year 0701.
            return f"{token[4:]}-{token[:2]}-{token[2:4]}", "date read as MMDDYYYY"
        return None, "8 digits but neither half is a plausible year"

    # 7 or 9 digits is a typo in the published identifier. It is reported rather
    # than repaired: there is no way to know which digit was wrong.
    return None, f"date has {len(token)} digits, expected 8"


def parse(identifier: str) -> dict:
    """Split a control name into its parts, recording every repair applied."""
    result = {
        "state_code": None, "payment_type": None, "payment_type_normalised": None,
        "provider_class": None,
        "review_type": None, "review_type_normalised": None,
        "rating_period_start": None, "rating_period_end": None,
        "identifier_suffix": None, "identifier_parsed": False,
        "identifier_issue": None, "identifier_repairs": [],
    }
    repairs: list[str] = []
    text = identifier.strip()

    # One identifier is published as \GA_Fee_IPH.OPH2_Amend_... A stray leading
    # character would otherwise push the whole field order along by one.
    stripped = text.lstrip("\\/ \t.")
    if stripped != text:
        repairs.append("leading stray character removed from the identifier")
        text = stripped

    # A trailing suffix distinguishes otherwise identical arrangements: the New
    # Jersey county, the Ohio hospital, a California rename note. It is split off
    # before parsing and kept.
    body = text
    tail = None
    m = re.search(r"(\d{6,9}\s*-\s*\d{6,9})\s+(?P<tail>\S.*)$", text)
    if m:
        tail = m.group("tail").strip()
        body = text[: m.end(1)].strip()
        result["identifier_suffix"] = tail

    # Some identifiers separate fields with hyphens. The date range also uses a
    # hyphen, so the range is lifted out before separators are normalised.
    range_match = _RANGE.search(body) or _YEAR_RANGE.search(body)
    if not range_match:
        result["identifier_issue"] = "no rating period found in the identifier"
        return result

    head = body[: range_match.start()].strip().rstrip("_-").strip()
    start_raw, end_raw = range_match.group("start"), range_match.group("end")

    if _YEAR_RANGE.search(body) and not _RANGE.search(body):
        # Fl-Proposal-D-Amendment-2020-2021 states years only.
        result["rating_period_start"] = f"{start_raw}-01-01"
        result["rating_period_end"] = f"{end_raw}-12-31"
        repairs.append("rating period given as years only; assumed full calendar years")
    else:
        start_iso, start_fix = _iso_date(start_raw)
        end_iso, end_fix = _iso_date(end_raw)
        result["rating_period_start"], result["rating_period_end"] = start_iso, end_iso
        for fix in (start_fix, end_fix):
            if fix and fix not in repairs:
                repairs.append(fix)

    state = _STATE.match(head + "_")
    if state:
        raw_state = state.group("state")
        result["state_code"] = raw_state.upper()
        if raw_state != raw_state.upper():
            repairs.append("state code was not upper case")
        head = head[len(raw_state):].lstrip("_-")

    if "-" in head and "_" not in head:
        head = head.replace("-", "_")
        repairs.append("fields were hyphen separated")

    tokens = [t for t in re.split(r"[_\s]+", head) if t]

    if tokens and tokens[-1].lower() in _REVIEW_WORDS:
        result["review_type"] = tokens[-1]
        result["review_type_normalised"] = (
            "Amendment" if tokens[-1].lower().startswith("amend")
            else tokens[-1].capitalize()
        )
        tokens = tokens[:-1]
    else:
        # WI_Fee_HCBS9_20250101-20251231 has no review type. Inventing one would
        # put an arrangement in a category CMS never assigned it to.
        repairs.append("no review type in the identifier")

    if tokens:
        # A combined arrangement is written VBP.Fee when underscore separated,
        # but hyphen separation flattens it to VBP-Fee-IPH-OPH, where the second
        # token is a payment type rather than a provider class. Merging them here
        # keeps HI-VBP-Fee-IPH-OPH and NM_VBP.Fee_NF2 describing the same thing.
        if len(tokens) > 2 and tokens[1].lower() in _PAYMENT_WORDS:
            tokens = [f"{tokens[0]}.{tokens[1]}", *tokens[2:]]
            repairs.append("combined payment type was split across two tokens")

        result["payment_type"] = tokens[0]
        # FEE, Fee, vbp, Vbp and VBP all occur, as do Fee.VBP and VBP.Fee for
        # what appears to be the same combination. The raw value is kept because
        # the inconsistency is itself a finding about CMS's naming; the
        # normalised value is what analysis should group on. Sorting the parts
        # makes Fee.VBP and VBP.Fee the same thing.
        parts = sorted(p.upper() for p in tokens[0].split(".") if p)
        result["payment_type_normalised"] = ".".join(parts) or None
        rest = tokens[1:]
        if not rest and "." in tokens[0]:
            # FL_Fee.IPH.OPH5_Renewal: payment type and provider class share a
            # token, joined by a dot.
            first, _, remainder = tokens[0].partition(".")
            result["payment_type"], result["provider_class"] = first, remainder
            repairs.append("payment type and provider class were one token")
        elif rest:
            result["provider_class"] = "_".join(rest)

    result["identifier_repairs"] = repairs
    result["identifier_parsed"] = bool(
        result["state_code"] and result["rating_period_start"] and result["rating_period_end"]
    )
    if not result["identifier_parsed"]:
        result["identifier_issue"] = "; ".join(repairs) or "could not resolve required fields"
    return result
