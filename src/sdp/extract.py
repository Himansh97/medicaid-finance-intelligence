"""Run amount extraction over every downloaded preprint and report the result.

    python -m src.sdp.extract
    python -m src.sdp.extract --limit 100

Writes data/processed/sdp_amounts.json and prints the numbers that matter: how
many amounts were anchored to a recognised phrase, which phrases carried them,
and what the remainder consists of.

That remainder is reported as a headline rather than buried, because it is the
honest measure of the dataset. Some of it is extraction the patterns do not yet
cover. Some of it is approvals where CMS stated no dollar amount at all, which is
a fact about Medicaid oversight and not a defect in this code.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.sdp.amounts import extract_amount
# The form fields are the primary source: they cover the documents published
# with no approval letter, and they carry the federal and non-federal split that
# no letter states. The letter is the cross-check.
from src.sdp.formfields import cross_check_identifier, read_form
# The expected local path is derived from the identifier, not read from the
# manifest. The manifest records local_path only when a download run finishes, so
# reading it would make this blind to a fetch still in progress and to files
# placed by hand.
from src.sdp.fetch_preprints import _local_path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "raw" / "sdp" / "manifest.json"
OUT = ROOT / "data" / "processed" / "sdp_amounts.json"

# An approval whose letter says the arrangement is made through an adjustment but
# names no figure. Separated from pattern misses because the two mean different
# things: one is our gap, the other is the source's.
NO_AMOUNT_STATED = "no dollar amount in the approval letter"


def run(limit: int | None = None) -> dict:
    manifest = json.loads(MANIFEST.read_text())
    entries = manifest["preprints"]
    if limit:
        entries = entries[:limit]

    records, phrases, issues = [], collections.Counter(), collections.Counter()

    for entry in entries:
        path = _local_path(entry["sdp_identifier"])
        if not path.exists() or path.stat().st_size == 0:
            continue
        result = extract_amount(path)
        form = read_form(path)
        id_mismatch = cross_check_identifier(entry["sdp_identifier"], form.cms_id)
        phrases[result.matched_phrase or "unanchored"] += 1
        if result.issue:
            issues[result.issue.split(",")[0][:60]] += 1

        records.append({
            "sdp_identifier": entry["sdp_identifier"],
            "state_code": entry.get("state_code"),
            "payment_type_normalised": entry.get("payment_type_normalised"),
            "provider_class": entry.get("provider_class"),
            "review_type_normalised": entry.get("review_type_normalised"),
            "rating_period_start": entry.get("rating_period_start"),
            "rating_period_end": entry.get("rating_period_end"),
            # Provenance travels with the figure. A number nobody can trace back
            # to a document and a phrase is not publishable.
            "source_sha256": entry.get("content_sha256"),
            "local_path": str(path.relative_to(ROOT)),
            "source_url": entry.get("pdf_url"),
            **result.as_dict(),
            "form": form.as_dict(),
            "identifier_mismatch": id_mismatch,
        })

    approvals = [r for r in records if r["letter_type"] == "approval"]
    phase_down = [r for r in records if r["letter_type"] == "phase_down_determination"]
    form_only = [r for r in records if r["letter_type"] == "form_only_no_letter"]
    anchored = sum(1 for r in approvals if r["amount_cents"] is not None)

    def usable(r):
        t = r["form"]["total"]
        return (t["cents"] is not None and not t["ambiguous_unit"]
                and not t["implausible"])

    from_form = [r for r in records if usable(r)]
    mismatches = sum(1 for r in records if r["identifier_mismatch"])
    no_amount = sum(1 for r in approvals if r["issue"] == NO_AMOUNT_STATED)

    return {
        "evaluated": len(records),
        "approvals": len(approvals),
        "phase_down_determinations": len(phase_down),
        "form_only_no_letter": len(form_only),
        "anchored": anchored,
        "no_amount_stated_by_cms": no_amount,
        "unresolved": len(approvals) - anchored - no_amount,
        "totals_from_form_fields": len(from_form),
        "identifier_mismatches": mismatches,
        "sum_total_cents": sum(r["form"]["total"]["cents"] for r in from_form),
        "sum_federal_cents": sum(
            r["form"]["federal_share"]["cents"] for r in from_form
            if r["form"]["federal_share"]["cents"] is not None
            and not r["form"]["federal_share"]["ambiguous_unit"]
            and not r["form"]["federal_share"]["implausible"]),
        "phrases": dict(phrases),
        "issues": dict(issues),
        "records": records,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    if not MANIFEST.exists():
        print("no manifest; run 'python -m src.sdp.fetch_preprints manifest' first")
        return 2

    summary = run(limit=args.limit)
    if not summary["evaluated"]:
        print("no PDFs downloaded yet; run 'python -m src.sdp.fetch_preprints download'")
        return 2

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=1))

    total = summary["approvals"] or 1
    pct = lambda n: f"{100 * n / total:5.1f}%"
    print(f"evaluated {summary['evaluated']} documents:")
    print(f"  {summary['approvals']:>5}  approval letters")
    print(f"  {summary['phase_down_determinations']:>5}  phase-down determinations "
          f"(Public Law 119-21)")
    print(f"  {summary['form_only_no_letter']:>5}  preprint form only, no letter attached\n")
    print("  of the approvals:")
    print(f"  amount anchored to a phrase   {summary['anchored']:>5}  {pct(summary['anchored'])}")
    print(f"  CMS stated no amount          {summary['no_amount_stated_by_cms']:>5}  "
          f"{pct(summary['no_amount_stated_by_cms'])}   (a fact about the source)")
    print(f"  unresolved                    {summary['unresolved']:>5}  {pct(summary['unresolved'])}"
          f"   (our gap)")

    print("\n  phrase carrying the amount:")
    for name, n in sorted(summary["phrases"].items(), key=lambda kv: -kv[1]):
        print(f"    {n:>5}  {name}")

    if summary["issues"]:
        print("\n  issues:")
        for issue, n in sorted(summary["issues"].items(), key=lambda kv: -kv[1]):
            print(f"    {n:>5}  {issue}")

    amounts = [r["amount_cents"] for r in summary["records"]
               if r["amount_cents"] and r["letter_type"] == "approval"]
    if amounts:
        print(f"\n  total of anchored amounts: ${sum(amounts) / 100:,.0f}")
        print(f"  largest single arrangement: ${max(amounts) / 100:,.0f}")
    ev = summary["evaluated"]
    print(f"\n  FORM FIELDS (the primary source)")
    print(f"    {summary['totals_from_form_fields']:>5}  "
          f"{100 * summary['totals_from_form_fields'] / ev:5.1f}%  usable totals")
    print(f"    ${summary['sum_total_cents'] / 100:>18,.0f}  sum of totals")
    print(f"    ${summary['sum_federal_cents'] / 100:>18,.0f}  sum of federal share")
    print("    (spans many rating periods; NOT an annual figure)")
    print(f"\n    {summary['identifier_mismatches']:>5}  documents whose own CMS ID "
          f"disagrees with their filename")
    print(f"\n  written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
