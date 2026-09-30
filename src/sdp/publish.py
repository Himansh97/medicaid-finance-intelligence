"""Publish the state directed payments dataset as CSV and Parquet.

    python -m src.sdp.publish

Writes to data/published/. Every approved preprint CMS lists gets a row,
including the ones where no amount could be read, because a dataset containing
only the successful extractions would misstate its own coverage. A reader can
filter the absences out; they cannot recover them if they were never shipped.

Every row carries where it came from: the source URL, the content hash of the
PDF it was read from, when that PDF was retrieved, and which extraction version
produced the row. A figure nobody can trace back to a document is not something
this project publishes.
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
EXTRACT = ROOT / "data" / "processed" / "sdp_amounts.json"
MANIFEST = ROOT / "data" / "raw" / "sdp" / "manifest.json"
OUT_DIR = ROOT / "data" / "published"

# Bump when a change alters the values a row can take, so a consumer can tell
# two releases apart without diffing them.
EXTRACTION_VERSION = "0.1.0"


def _amount(block: dict | None, field: str):
    if not block:
        return None
    return block.get(field)


def build_rows() -> list[dict]:
    extract = json.loads(EXTRACT.read_text())
    manifest = json.loads(MANIFEST.read_text())

    by_identifier = {r["sdp_identifier"]: r for r in extract["records"]}
    rows = []

    for entry in manifest["preprints"]:
        identifier = entry["sdp_identifier"]
        rec = by_identifier.get(identifier)
        form = (rec or {}).get("form") or {}
        total = form.get("total") or {}
        federal = form.get("federal_share") or {}
        nonfederal = form.get("nonfederal_share") or {}

        # An amount is publishable when it was read, its unit is not assumed,
        # and its size is credible. The components stay in the row so a reader
        # can apply a different rule.
        usable = (
            total.get("cents") is not None
            and not total.get("ambiguous_unit")
            and not total.get("implausible")
        )

        rows.append({
            "sdp_identifier": identifier,
            "state_code": entry.get("state_code"),
            "state_name": entry.get("state_name"),
            "payment_type": entry.get("payment_type"),
            "payment_type_normalised": entry.get("payment_type_normalised"),
            "provider_class": entry.get("provider_class"),
            "review_type": entry.get("review_type"),
            "review_type_normalised": entry.get("review_type_normalised"),
            "rating_period_start": entry.get("rating_period_start"),
            "rating_period_end": entry.get("rating_period_end"),
            "identifier_suffix": entry.get("identifier_suffix"),
            "description": entry.get("description"),

            "document_type": (rec or {}).get("letter_type"),
            "form_template": form.get("template"),

            "total_amount_cents": total.get("cents"),
            "total_amount_usd": (total["cents"] / 100) if total.get("cents") is not None else None,
            "total_amount_raw": total.get("raw"),
            "federal_share_cents": federal.get("cents"),
            "federal_share_raw": federal.get("raw"),
            "nonfederal_share_cents": nonfederal.get("cents"),
            "nonfederal_share_raw": nonfederal.get("raw"),

            # The approval letter, where one exists. An independent reading of
            # the same arrangement, useful as a check on the form.
            "letter_amount_cents": (rec or {}).get("amount_cents"),
            "letter_matched_phrase": (rec or {}).get("matched_phrase"),

            "amount_is_publishable": usable,
            "amount_unit_assumed": bool(total.get("ambiguous_unit")),
            "amount_implausible": bool(total.get("implausible")),
            "amount_issue": total.get("issue"),

            "cms_id_in_document": form.get("cms_id"),
            "identifier_mismatch": (rec or {}).get("identifier_mismatch"),
            "identifier_repairs": "; ".join(entry.get("identifier_repairs") or []) or None,
            "identifier_issue": entry.get("identifier_issue"),

            "source_url": entry.get("pdf_url"),
            "source_sha256": entry.get("content_sha256"),
            "retrieved_at": entry.get("retrieved_at") or manifest.get("retrieved_at"),
            "excluded_reason": entry.get("excluded_reason"),
            "extraction_version": EXTRACTION_VERSION,
        })

    return rows


def publish() -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(build_rows()).sort_values("sdp_identifier")

    csv_path = OUT_DIR / "sdp_arrangements.csv"
    parquet_path = OUT_DIR / "sdp_arrangements.parquet"
    frame.to_csv(csv_path, index=False)
    frame.to_parquet(parquet_path, index=False)

    publishable = frame[frame["amount_is_publishable"]]
    return {
        "rows": len(frame),
        "publishable_amounts": len(publishable),
        "states": frame["state_code"].nunique(),
        "sum_total_usd": float(publishable["total_amount_usd"].sum()),
        "identifier_mismatches": int(frame["identifier_mismatch"].notna().sum()),
        "robots_excluded": int(frame["excluded_reason"].notna().sum()),
        "csv": csv_path,
        "parquet": parquet_path,
        "columns": list(frame.columns),
    }


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)

    if not EXTRACT.exists():
        print("no extraction output; run 'python -m src.sdp.extract' first")
        return 2

    r = publish()
    print(f"published {r['rows']} rows across {r['states']} states")
    print(f"  {r['publishable_amounts']} with a publishable amount "
          f"({100 * r['publishable_amounts'] / r['rows']:.1f}%)")
    print(f"  ${r['sum_total_usd']:,.0f} summed across all rating periods "
          f"(NOT an annual figure)")
    print(f"  {r['identifier_mismatches']} rows where the document disagrees with its filename")
    print(f"  {r['robots_excluded']} rows with no PDF, excluded by robots.txt")
    print(f"\n  {r['csv'].relative_to(ROOT)}")
    print(f"  {r['parquet'].relative_to(ROOT)}")
    print(f"  {len(r['columns'])} columns; see docs/sdp_dataset.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
