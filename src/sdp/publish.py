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
EXTRACTION_VERSION = "0.4.0"


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
        form_usable = (
            total.get("cents") is not None
            and not total.get("ambiguous_unit")
            and not total.get("implausible")
        )

        # The form is preferred because it also carries the federal split and
        # covers documents published with no letter. Where the form has nothing
        # usable, the approval letter is a complete and independent reading of
        # the same arrangement, and ignoring it discards a quarter of the
        # coverage for no reason. The column says which one a row used.
        letter_cents = (rec or {}).get("amount_cents")
        letter_usable = (
            letter_cents is not None
            and (rec or {}).get("letter_type") == "approval"
        )

        # A phase-down determination states the ceiling a grandfathered
        # arrangement may not exceed under Public Law 119-21. It is not an
        # approved amount and must never be summed beside one, but it is the
        # forward-looking figure the whole phase-down debate turns on, so it is
        # published in a column of its own rather than thrown away.
        is_phase_down = (rec or {}).get("letter_type") == "phase_down_determination"
        cap_cents = letter_cents if is_phase_down else None

        if form_usable:
            amount_cents, amount_source = total["cents"], "form_field"
        elif letter_usable:
            amount_cents, amount_source = letter_cents, "approval_letter"
        else:
            amount_cents, amount_source = None, None

        usable = amount_cents is not None

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

            # The figure to use. Coalesced from the form, falling back to the
            # letter, with amount_source saying which.
            "amount_cents": amount_cents,
            "amount_usd": (amount_cents / 100) if amount_cents is not None else None,
            "amount_source": amount_source,

            "total_amount_cents": total.get("cents"),
            "total_amount_usd": (total["cents"] / 100) if total.get("cents") is not None else None,
            "total_amount_raw": total.get("raw"),
            "federal_share_cents": federal.get("cents"),
            "federal_share_raw": federal.get("raw"),
            "nonfederal_share_cents": nonfederal.get("cents"),
            "nonfederal_share_raw": nonfederal.get("raw"),

            # The approval letter, where one exists. An independent reading of
            # the same arrangement, useful as a check on the form.
            "grandfathered_cap_cents": cap_cents,
            "grandfathered_cap_usd": (cap_cents / 100) if cap_cents is not None else None,

            "letter_amount_cents": (rec or {}).get("amount_cents"),
            "letter_matched_phrase": (rec or {}).get("matched_phrase"),

            "amount_is_publishable": usable,
            # These describe the amount that was actually chosen. A row
            # published from the letter must not inherit the form's caveats:
            # several rows have an ambiguous form entry and a perfectly clear
            # letter, and flagging those as assumed would be false.
            "amount_unit_assumed": bool(total.get("ambiguous_unit")) if amount_source == "form_field" else False,
            "amount_implausible": bool(total.get("implausible")) if amount_source == "form_field" else False,
            "amount_issue": total.get("issue") if amount_source != "approval_letter" else None,
            # The form's own caveats, kept for anyone comparing the two readings.
            "form_unit_assumed": bool(total.get("ambiguous_unit")),
            "form_implausible": bool(total.get("implausible")),

            "cms_id_in_document": form.get("cms_id"),
            # Separated because they mean different things: one is a document
            # contradicting itself, the other is a field nobody filled usefully.
            "identifier_mismatch": (
                (rec or {}).get("identifier_mismatch")
                if str((rec or {}).get("identifier_mismatch") or "").startswith("document disagrees")
                else None),
            "cms_id_unusable": (
                (rec or {}).get("identifier_mismatch")
                if str((rec or {}).get("identifier_mismatch") or "").startswith("CMS ID field holds no")
                else None),
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
    by_source = frame["amount_source"].value_counts().to_dict()
    return {
        "rows": len(frame),
        "publishable_amounts": len(publishable),
        "states": frame["state_code"].nunique(),
        "sum_total_usd": float(publishable["amount_usd"].sum()),
        "by_source": by_source,
        "identifier_mismatches": int(frame["identifier_mismatch"].notna().sum()),
        "cms_id_unusable": int(frame["cms_id_unusable"].notna().sum()),
        "grandfathered_caps": int(frame["grandfathered_cap_cents"].notna().sum()),
        "sum_cap_usd": float(frame["grandfathered_cap_usd"].sum()),
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
    for src, n in r["by_source"].items():
        print(f"      {n:>5}  from {src}")
    print(f"  ${r['sum_total_usd']:,.0f} summed across all rating periods "
          f"(NOT an annual figure)")
    print(f"  {r['grandfathered_caps']} grandfathering caps under Public Law 119-21, "
          f"${r['sum_cap_usd']:,.0f}")
    print(f"  {r['identifier_mismatches']} rows where the document substantively "
          f"disagrees with its filename")
    print(f"  {r['cms_id_unusable']} rows where the CMS ID field holds no identifier")
    print(f"  {r['robots_excluded']} rows with no PDF, excluded by robots.txt")
    print(f"\n  {r['csv'].relative_to(ROOT)}")
    print(f"  {r['parquet'].relative_to(ROOT)}")
    print(f"  {len(r['columns'])} columns; see docs/sdp_dataset.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
