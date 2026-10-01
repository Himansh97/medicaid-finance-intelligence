"""How ready are states to report directed payment amounts in T-MSIS?

    python -m src.sdp.readiness --rating-period-year 2024

CMS guidance issued in March 2026 requires states to report actual state directed
payment amounts in T-MSIS (`TOT-SDP-PAID-AMT`) from September 2026. Whether that
will produce usable data is the open question in Medicaid SDP oversight, and KFF
put it this way: "It is unclear how comprehensive those data will be, most states
currently do not report other types of supplemental payments in T-MSIS."

This module turns that sentence into numbers, from public data only.

**It is a proxy and says so.** There is no public measure of SDP reporting, for
the obvious reason that the requirement has only just taken effect. The nearest
public evidence is CMS's own DQ Atlas assessment of **supplemental payment**
reporting, which is a different payment category but the same question: when CMS
asks states to report a payment amount in T-MSIS, do they?

Two limitations that must travel with every figure produced here:

  * Supplemental payments are fee-for-service. Directed payments are managed
    care. A state good at one is not necessarily good at the other.
  * The assessment snapshot used here contains **2020**. Nothing here describes 2026.

Actual SDP amounts land in T-MSIS/TAF, which requires a ResDAC data use
agreement and is out of scope for this project. See docs/real_data_sources.md.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import json
from pathlib import Path
import re
import sys

import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.sdp.fetch_preprints import TIMEOUT, USER_AGENT

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "published"
RAW = ROOT / "data" / "raw" / "sdp"

# DQ Atlas is an Angular application backed by the data.medicaid.gov datastore.
# Its published export bundles every topic as JSON payloads holding CSV text.
MEASURES_URL = (
    "https://download.medicaid.gov/data/dq-atlas/"
    "20211018_v2_ETL_DEV_OT_SPLIT/measure_allStates_download.csv"
)
TOPIC_MARKER = "Supplemental_Pmts"

# DQ Atlas grades a state on each topic. "Unclassified" is the important one: it
# generally means there was not enough data to assess, which for a reporting
# question is itself the answer.
USABLE_ASSESSMENTS = {"Low concern"}


def fetch_measures() -> str:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    response = session.get(MEASURES_URL, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def supplemental_payment_files(measures_csv: str) -> list[tuple[int, str, str]]:
    """Every Supplemental Payments topic file, newest year first."""
    csv.field_size_limit(10_000_000)
    found = []
    for row in csv.DictReader(io.StringIO(measures_csv)):
        try:
            payload = json.loads(row["payload"])
        except (ValueError, KeyError):
            continue
        name = payload.get("fileName", "")
        if TOPIC_MARKER not in name:
            continue
        year = re.search(r"_(\d{4})_", name)
        if year:
            found.append((int(year.group(1)), name, payload.get("fileContent", "")))
    return sorted(found, reverse=True)


def parse_topic_file(content: str) -> list[dict]:
    """The file carries several title lines before its real header row."""
    lines = [line for line in content.split("\n") if line.strip()]
    header = next((i for i, line in enumerate(lines) if line.startswith('"State"')), None)
    if header is None:
        return []
    return list(csv.DictReader(lines[header:]))


def sdp_coverage_by_state(rating_period_year: int) -> dict:
    """Known projected subtotals and unknown counts for a start-year cohort."""
    import pandas as pd
    from src.sdp.resolution import resolve
    published = OUT_DIR / 'sdp_arrangements.csv'
    if not published.exists():
        return {}
    archive = pd.read_csv(published)
    dated = archive[archive.rating_period_start.str[:4].eq(str(rating_period_year))
                    & archive.rating_period_end.notna()]
    current = resolve(dated)
    result = {}
    for state, group in current.groupby('state_name'):
        known = group[group.amount_is_publishable]
        result[state] = {
            'sdp_amount_usd': float(known.amount_cents.sum()) / 100 if len(known) else None,
            'sdp_known_arrangements': len(known),
            'sdp_unknown_arrangements': int((~group.amount_is_publishable).sum()),
        }
    return result


def sdp_dollars_by_state(rating_period_year: int) -> dict[str, float]:
    return {state: item['sdp_amount_usd'] for state, item in
            sdp_coverage_by_state(rating_period_year).items() if item['sdp_amount_usd'] is not None}


def attach_sdp_amounts(result: dict, rating_period_year: int) -> dict:
    from src.sdp.resolution import RESOLUTION_VERSION
    coverage = sdp_coverage_by_state(rating_period_year)
    result['caveats'] = [c.replace('The newest published assessment is', 'The preserved assessment snapshot covers')
                         for c in result.get('caveats', [])]
    result['sdp_rating_period_start_year'] = rating_period_year
    result['resolution_version'] = RESOLUTION_VERSION
    result['sdp_amount_basis'] = ('Known projected subtotal for rating periods starting in the selected year; '
                                  'identifier-inferred lineage; missing amounts excluded, not zero; not actual spending')
    for state in result.get('states', []):
        state.update(coverage.get(state['state'], {'sdp_amount_usd': None,
                    'sdp_known_arrangements': 0, 'sdp_unknown_arrangements': 0}))
    return result


def build(rating_period_year: int = 2024) -> dict:
    measures = fetch_measures()
    files = supplemental_payment_files(measures)
    if not files:
        return {"available": False,
                "reason": "DQ Atlas publishes no Supplemental Payments topic"}

    year, filename, content = files[0]
    rows = parse_topic_file(content)
    assessments = collections.Counter(r.get("DQ Assessment", "").strip() for r in rows)
    usable = sum(n for a, n in assessments.items() if a in USABLE_ASSESSMENTS)

    dollars = sdp_dollars_by_state(rating_period_year)

    states = [{
        "state": r.get("State"),
        # Joined from the published dataset so the two questions sit side by
        # side: how much directed payment money a state moves, and whether it
        # has ever managed to report a payment amount to T-MSIS.
        "sdp_amount_usd": dollars.get(r.get("State")),
        "data_year": r.get("Data Year"),
        "dq_assessment": r.get("DQ Assessment"),
        "supplemental_payment_records": r.get("# Supplemental Payment Records"),
        "pct_missing_or_zero_payment": r.get(
            "% Supplemental Payment Records with Missing or Zero Payment"),
        "pct_non_missing_payment_amount": r.get(
            "% Supplemental Payment Records with Non-Missing Service Tracking Payment Amt"),
        "reports_usably": r.get("DQ Assessment", "").strip() in USABLE_ASSESSMENTS,
    } for r in rows]

    return attach_sdp_amounts({
        "available": True,
        "proxy_for": "state directed payment reporting in T-MSIS",
        "measured": "supplemental payment reporting quality",
        "newest_year": year,
        "source_file": filename,
        "source_url": MEASURES_URL,
        "states_assessed": len(rows),
        "states_reporting_usably": usable,
        "assessments": dict(assessments),
        "states": states,
        "caveats": [
            "Supplemental payments are fee-for-service; directed payments are "
            "managed care. This is a proxy, not a measurement of SDP reporting.",
            f"The selected assessment snapshot covers {year}. Nothing here describes "
            "the September 2026 requirement taking effect.",
            "Actual SDP amounts land in T-MSIS/TAF, which requires a ResDAC data "
            "use agreement and is out of scope for this project.",
        ],
    }, rating_period_year)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--rating-period-year', type=int, required=True)
    parser.add_argument('--reuse-assessments', action='store_true',
                        help='Recalculate SDP joins using the existing assessment snapshot; no source refresh')
    args = parser.parse_args(argv)
    if args.reuse_assessments:
        result = attach_sdp_amounts(json.loads((OUT_DIR / 'sdp_reporting_readiness.json').read_text()),
                                    args.rating_period_year)
    else:
        result = build(args.rating_period_year)

    if not result["available"]:
        print(result["reason"])
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "sdp_reporting_readiness.json"
    out.write_text(json.dumps(result, indent=1))

    total = result["states_assessed"]
    usable = result["states_reporting_usably"]
    print(f"DQ Atlas supplemental payment reporting, {result['newest_year']} "
          f"(a proxy, see caveats)\n")
    print(f"  {total} states and territories assessed")
    print(f"  {usable} reporting usably ({100 * usable / total:.0f}%)\n")
    for assessment, n in sorted(result["assessments"].items(), key=lambda kv: -kv[1]):
        print(f"    {n:>3}  {assessment or '(blank)'}")

    print("\n  caveats:")
    for c in result["caveats"]:
        print(f"    - {c}")
    ranked = sorted((s for s in result["states"] if s["sdp_amount_usd"]),
                    key=lambda s: -s["sdp_amount_usd"])[:10]
    if ranked:
        covered = sum(1 for s in ranked if s["reports_usably"])
        print(f"\n  ten largest KNOWN projected subtotals, rating periods starting {args.rating_period_year}; incomplete coverage")
        print("  they were reporting supplemental payments usably in "
              f"{result['newest_year']}:\n")
        for s in ranked:
            mark = "yes" if s["reports_usably"] else "no "
            print(f"    {mark}  {s['state']:<16} "
                  f"${s['sdp_amount_usd']:>16,.0f}   {s['dq_assessment']}")
        print(f"\n    {covered} of {len(ranked)} were reporting usably.")

    print(f"\n  written to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
