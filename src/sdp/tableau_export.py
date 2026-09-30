"""Build an analysis-ready extract for Tableau, or any other BI tool.

    python -m src.sdp.tableau_export

The published dataset is deliberately complete: one row per document CMS lists,
including superseded versions and documents carrying no amount. That is correct
for an archive and dangerous in a BI tool, where dragging a measure onto a sheet
sums whatever is there. Doing that to `sdp_arrangements.csv` yields $318 billion,
which spans 2020 to 2027 and counts an amendment on top of the renewal it
amends.

This extract makes the safe reading the default:

  * one row per arrangement per rating period, with an amendment superseding the
    renewal or new filing it amends
  * only rows carrying a usable amount, so no measure is silently a zero
  * a rating period year, because a total is only meaningful within one
  * the reporting readiness assessment joined on, so the two findings can be put
    on one sheet
  * grandfathering caps kept in a column that is never the same measure as spend

Summing `amount_usd` within one `rating_period_year` is correct. Summing it
across years is not, and no arrangement of this file can prevent that, so the
documentation says it and the field name does not pretend otherwise.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ROOT = Path(__file__).resolve().parents[2]
PUBLISHED = ROOT / "data" / "published"
ARRANGEMENTS = PUBLISHED / "sdp_arrangements.csv"
READINESS = PUBLISHED / "sdp_reporting_readiness.json"
OUT = PUBLISHED / "sdp_tableau_extract.csv"

# An amendment supersedes the filing it amends. Ordering the review types this
# way and keeping the last one per arrangement resolves the lineage without
# needing CMS to state it, which it does not.
SUPERSESSION_ORDER = {"New": 0, "Renewal": 1, "Amendment": 2}

ARRANGEMENT_KEY = [
    "state_code", "payment_type_normalised", "provider_class",
    "rating_period_start", "rating_period_end",
]


def load_readiness() -> pd.DataFrame:
    """State reporting assessments, empty if the view has not been built."""
    if not READINESS.exists():
        return pd.DataFrame(columns=["state_name", "dq_assessment", "reports_usably"])
    view = json.loads(READINESS.read_text())
    return pd.DataFrame([{
        "state_name": s["state"],
        "dq_assessment": s["dq_assessment"],
        "reports_usably": s["reports_usably"],
        "dq_assessment_year": view["newest_year"],
    } for s in view["states"]])


def build() -> pd.DataFrame:
    df = pd.read_csv(ARRANGEMENTS)

    usable = df[df["amount_is_publishable"]].copy()

    # A row with no parseable rating period cannot be filtered to a year, and a
    # year filter is the one rule that makes this extract safe to sum. Five rows
    # are in this state, carrying roughly $1.1bn between them, every one because
    # CMS published a malformed date: New York's reads 202300401, nine digits.
    # They are dropped here and the amount is reported, because losing a
    # $650 million arrangement silently would be worse than the typo.
    undateable = usable[usable["rating_period_start"].isna()]
    usable = usable[usable["rating_period_start"].notna()].copy()
    usable["rating_period_year"] = usable["rating_period_start"].str[:4]

    # Eight states filed Question 4 as $0 or $0.00. Those are the published
    # values rather than a parsing failure, so they stay, but a zero drags an
    # average and shows as an absent bar, so it is flagged for exclusion.
    usable["amount_is_zero"] = usable["amount_usd"] == 0
    usable["_rank"] = usable["review_type_normalised"].map(SUPERSESSION_ORDER).fillna(-1)

    # Keep the highest-ranked filing per arrangement. Sorting by identifier as
    # well makes the choice deterministic where two filings tie.
    current = (usable
               .sort_values(["_rank", "sdp_identifier"])
               .drop_duplicates(subset=ARRANGEMENT_KEY, keep="last")
               .drop(columns=["_rank"]))

    superseded = len(usable) - len(current)

    caps = (df[df["grandfathered_cap_usd"].notna()]
            .groupby("state_name", as_index=False)["grandfathered_cap_usd"].sum()
            .rename(columns={"grandfathered_cap_usd": "state_grandfathered_cap_usd"}))

    out = (current
           .merge(load_readiness(), on="state_name", how="left")
           .merge(caps, on="state_name", how="left"))

    out = out[[
        "sdp_identifier", "state_code", "state_name",
        "rating_period_year", "rating_period_start", "rating_period_end",
        "payment_type_normalised", "provider_class", "review_type_normalised",
        "amount_usd", "amount_is_zero", "federal_share_cents", "amount_source",
        "document_type", "description",
        "dq_assessment", "reports_usably", "dq_assessment_year",
        "state_grandfathered_cap_usd",
        "identifier_mismatch", "source_url",
    ]].rename(columns={
        "payment_type_normalised": "payment_type",
        "review_type_normalised": "review_type",
    })
    out["federal_share_usd"] = out.pop("federal_share_cents") / 100

    out.attrs["superseded_removed"] = superseded
    out.attrs["undateable_rows"] = len(undateable)
    out.attrs["undateable_usd"] = float(undateable["amount_usd"].sum())
    return out.sort_values(["rating_period_year", "state_code", "sdp_identifier"])


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    if not ARRANGEMENTS.exists():
        print("nothing published; run 'python -m src.sdp.publish' first")
        return 2

    out = build()
    out.to_csv(OUT, index=False)

    print(f"{len(out)} rows, one per arrangement per rating period")
    print(f"  {out.attrs['superseded_removed']} superseded filings removed")
    if out.attrs["undateable_rows"]:
        print(f"  {out.attrs['undateable_rows']} rows dropped for having no parseable "
              f"rating period, worth ${out.attrs['undateable_usd']:,.0f}")
        print("    (all of them CMS date typos; see identifier_issue in the full dataset)")
    zeros = int(out["amount_is_zero"].sum())
    if zeros:
        print(f"  {zeros} rows filed as $0 by the state, kept and flagged")
    print(f"  {out['state_code'].nunique()} states\n")

    print("  amount by rating period year (safe to sum WITHIN a year):")
    for year, group in out.groupby("rating_period_year"):
        print(f"    {year}  {len(group):>4} arrangements  ${group['amount_usd'].sum():>16,.0f}")

    joined = out["dq_assessment"].notna().sum()
    print(f"\n  {joined} rows carry a reporting assessment")
    print(f"\n  written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
