"""Parse the CMS approved state directed payment preprint listing.

The listing is server-rendered Drupal with generic USWDS utility classes and no
semantic card markup, so parsing by CSS class would break the first time CMS
adjusts its theme. The stable anchors are the literal text "SDP Identifier:" and
the PDF href, both of which carry meaning rather than presentation.

The SDP identifier is also the PDF filename, which makes it the authoritative
key: STATE_PAYMENTTYPE_PROVIDERCLASS_REVIEWTYPE_STARTDATE-ENDDATE, for example
MO_Fee_BHO_Renewal_20250701-20260630.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import html
import re

from src.sdp.identifier import parse as parse_identifier

BASE = "https://www.medicaid.gov"
LISTING_PATH = (
    "/medicaid/managed-care/guidance/state-directed-payments"
    "/approved-state-directed-payment-preprints"
)

# Preprints live under two different paths depending on when CMS published them.
PDF_HREF = re.compile(
    r'href="((?:/medicaid/managed-care/downloads|/media/file)/[^"]*\.pdf)"',
    re.IGNORECASE,
)
_STRIP = re.compile(r"<script.*?</script>|<style.*?</style>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")

# The identifier read from the filename, which may disagree with the body of the
# PDF. That disagreement is a finding, not something to resolve silently.
#
# A trailing suffix is common and meaningful: New Jersey appends the county
# ("... Atlantic"), Ohio appends the hospital ("... Dayton Children's"), and
# California appends a rename note. It is captured rather than discarded,
# because it is often the only thing distinguishing two otherwise identical
# arrangements in the same state and rating period.
#
# The end date is matched as 7 or 8 digits on purpose. NM_VBP.Fee_NF2_Renewal_
# 20260101-2026123 is 7, which is a typo in CMS's published identifier. Matching
# it lets the record be loaded and reported as malformed, where a strict pattern
# would drop the arrangement entirely and lose the finding with it.
IDENTIFIER = re.compile(
    r"^(?P<state>[A-Z]{2})_(?P<rest>.+?)_(?P<start>\d{8})-(?P<end>\d{7,8})"
    r"(?:\s+(?P<suffix>.+))?$"
)


@dataclass(frozen=True)
class PreprintRef:
    """One preprint as the listing describes it, before any PDF is opened."""

    sdp_identifier: str
    state_name: str
    description: str
    pdf_url: str
    # Parsed from the identifier. None where it does not follow the convention,
    # which is recorded rather than guessed at.
    state_code: str | None
    payment_type: str | None
    provider_class: str | None
    review_type: str | None
    payment_type_normalised: str | None
    review_type_normalised: str | None
    rating_period_start: str | None
    rating_period_end: str | None
    identifier_suffix: str | None
    identifier_parsed: bool
    identifier_issue: str | None
    identifier_repairs: list

    def as_dict(self) -> dict:
        return asdict(self)


def _text_lines(fragment: str) -> list[str]:
    text = html.unescape(_TAGS.sub("\n", fragment))
    return [line.strip() for line in text.split("\n") if line.strip()]


def _iso(yyyymmdd: str) -> str:
    return f"{yyyymmdd[0:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


def parse_listing(page_html: str) -> list[PreprintRef]:
    """Extract every preprint on one listing page."""
    cleaned = _STRIP.sub("", page_html)
    refs: list[PreprintRef] = []

    # Each preprint begins at an "SDP Identifier:" label. The first chunk is
    # everything before the first one, which is page furniture.
    for block in re.split(r"SDP Identifier:", cleaned)[1:]:
        link = PDF_HREF.search(block)
        if not link:
            continue
        lines = _text_lines(block)
        if not lines:
            continue

        identifier = lines[0]
        refs.append(PreprintRef(
            sdp_identifier=identifier,
            state_name=lines[1] if len(lines) > 1 else "",
            description=lines[2] if len(lines) > 2 else "",
            pdf_url=BASE + link.group(1),
            **parse_identifier(identifier),
        ))

    return refs


def listing_url(page: int = 0, limit: int = 100) -> str:
    """The listing serves 10 per page by default; 100 is accepted.

    Twelve requests instead of a hundred and sixteen. This is somebody's public
    web server, and the difference matters.
    """
    return f"{BASE}{LISTING_PATH}?limit={limit}&page={page}"
