"""How ready are states to report directed payment amounts in T-MSIS?

    python -m src.sdp.readiness

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
  * The newest published assessment is **2020**. Nothing here describes 2026.

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


def sdp_dollars_by_state() -> dict[str, float]:
    """Published SDP amounts per state, for joining to the readiness view.

    Empty when the dataset has not been published yet, which is not an error:
    the readiness view stands on its own.
    """
    published = OUT_DIR / "sdp_arrangements.csv"
    if not published.exists():
        return {}
    totals: dict[str, float] = collections.defaultdict(float)
    with published.open() as fh:
        for row in csv.DictReader(fh):
            if row.get("amount_is_publishable") != "True":
                continue
            name, usd = row.get("state_name"), row.get("amount_usd")
            if name and usd:
                totals[name] += float(usd)
    return dict(totals)


def build() -> dict:
    measures = fetch_measures()
    files = supplemental_payment_files(measures)
    if not files:
        return {"available": False,
                "reason": "DQ Atlas publishes no Supplemental Payments topic"}

    year, filename, content = files[0]
    rows = parse_topic_file(content)
    assessments = collections.Counter(r.get("DQ Assessment", "").strip() for r in rows)
    usable = sum(n for a, n in assessments.items() if a in USABLE_ASSESSMENTS)

    dollars = sdp_dollars_by_state()

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

    return {
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
            f"The newest published assessment is {year}. Nothing here describes "
            "the September 2026 requirement taking effect.",
            "Actual SDP amounts land in T-MSIS/TAF, which requires a ResDAC data "
            "use agreement and is out of scope for this project.",
        ],
    }


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    result = build()

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
        print("\n  the ten states with the most directed payment money, and whether")
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
