"""Build a BI candidate extract with explicit missing amounts and lineage status.

Filter to one rating-period START year. Sums are known projected subtotals,
not complete annual spending. Filename lineage is inferred, not source-verified.
State document-cap aggregates are exported separately to prevent row multiplication.
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

from src.sdp.resolution import resolve

CAPS_OUT = PUBLISHED / 'sdp_state_caps.csv'
READINESS_COLUMNS = ['state_name', 'dq_assessment', 'reports_usably', 'dq_assessment_year']


def load_readiness() -> pd.DataFrame:
    """State reporting assessments, empty if the view has not been built."""
    if not READINESS.exists():
        return pd.DataFrame(columns=READINESS_COLUMNS)
    view = json.loads(READINESS.read_text())
    return pd.DataFrame([{
        "state_name": s["state"],
        "dq_assessment": s["dq_assessment"],
        "reports_usably": s["reports_usably"],
        "dq_assessment_year": view["newest_year"],
    } for s in view.get("states", [])], columns=READINESS_COLUMNS)


def build() -> pd.DataFrame:
    df = pd.read_csv(ARRANGEMENTS)

    dated = df[df['rating_period_start'].notna() & df['rating_period_end'].notna()].copy()
    undateable = df[~df.index.isin(dated.index)]
    current = resolve(dated)
    current['rating_period_year'] = current['rating_period_start'].str[:4]
    current['amount_is_zero'] = current['amount_usd'].eq(0)
    superseded = len(dated) - len(current)
    out = current.merge(load_readiness(), on='state_name', how='left', validate='many_to_one')

    out = out[[
        "sdp_identifier", "state_code", "state_name",
        "rating_period_year", "rating_period_start", "rating_period_end",
        "payment_type_normalised", "provider_class", "review_type_normalised",
        "amount_usd", "amount_is_zero", "federal_share_cents", "amount_source",
        "document_type", "description",
        "dq_assessment", "reports_usably", "dq_assessment_year",
        "identifier_suffix", "lineage_status", "candidate_identifiers",
        "amount_status", "resolution_version",
        "identifier_mismatch", "source_url", "source_sha256", "retrieved_at",
    ]].rename(columns={
        "payment_type_normalised": "payment_type",
        "review_type_normalised": "review_type",
    })
    out["federal_share_usd"] = out.pop("federal_share_cents") / 100

    out.attrs["superseded_removed"] = superseded
    out.attrs["undateable_rows"] = len(undateable)
    out.attrs["undateable_usd"] = float(undateable["amount_usd"].sum())
    return out.sort_values(["rating_period_year", "state_code", "sdp_identifier"])


def build_caps() -> pd.DataFrame:
    """One row per state: archive document-cap subtotal, not verified exposure.

    Documents can overlap; this total is NOT a deduplicated statutory liability.
    Source identifiers permit tracing each contribution back to the archive.
    """
    df = pd.read_csv(ARRANGEMENTS)
    caps = df[df['grandfathered_cap_cents'].notna()]
    out = caps.groupby(['state_code', 'state_name'], as_index=False).agg(
        cap_document_sum_cents=('grandfathered_cap_cents', 'sum'),
        cap_document_count=('sdp_identifier', 'count'),
        source_identifiers=('sdp_identifier', lambda ids: ' | '.join(sorted(ids))))
    out['cap_document_sum_usd'] = out.pop('cap_document_sum_cents') / 100
    out['measure_basis'] = 'Archive document-cap subtotal; overlap not resolved; not projected payments or actual spending'
    return out


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    if not ARRANGEMENTS.exists():
        print("nothing published; run 'python -m src.sdp.publish' first")
        return 2

    out = build()
    out.to_csv(OUT, index=False)
    build_caps().to_csv(CAPS_OUT, index=False)

    print(f"{len(out)} rows, one per arrangement per rating period")
    print(f"  {out.attrs['superseded_removed']} additional family records consolidated (identifier inference)")
    if out.attrs["undateable_rows"]:
        print(f"  {out.attrs['undateable_rows']} rows excluded for incomplete "
              f"rating period, worth ${out.attrs['undateable_usd']:,.0f}")
        print("    See identifier_issue in the archive; these cannot be assigned to a reporting year.")
    print(f"  {out.amount_usd.isna().sum()} unresolved/missing amounts retained as null")
    zeros = int(out["amount_is_zero"].sum())
    if zeros:
        print(f"  {zeros} rows filed as $0 by the state, kept and flagged")
    print(f"  {out['state_code'].nunique()} states\n")

    print("  known projected amount subtotals by rating-period START year (incomplete, inferred lineage):")
    for year, group in out.groupby("rating_period_year"):
        print(f"    {year}  {len(group):>4} arrangements  ${group['amount_usd'].sum(min_count=1):>16,.0f}")

    joined = out["dq_assessment"].notna().sum()
    print(f"\n  {joined} rows carry a reporting assessment")
    print(f"\n  written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
