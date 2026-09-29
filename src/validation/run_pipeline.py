"""Apply transformations and quality rules to a built fixture database.

    python -m src.validation.run_pipeline [--db PATH]

Order is fixed: exposure before claims, because a claim's population match needs
member months to exist; claims before ledgers, because a payment references the
claim version it paid.

The run ends READY_FOR_REVIEW only when every blocking rule passed. It does not
publish: certification needs a finance approver and a release manifest, which are
a later task. A run that fails is kept, not deleted, because the quarantine and
rule results are the diagnostic evidence.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data_generation import fixture as fx
from src.data_generation.build_fixture import DEFAULT_DB, connect

ROOT = Path(__file__).resolve().parents[2]
TRANSFORM_DIR = ROOT / "sql" / "transformations"
QUALITY_DIR = ROOT / "sql" / "quality"


def _statements(sql: str):
    """Split on semicolons that end a statement, ignoring comment lines.

    sqlite3 executes one statement per call when parameters are bound, and
    executescript does not bind them, so the file has to be split.
    """
    cleaned = "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )
    return [s.strip() for s in cleaned.split(";") if s.strip()]


def _apply(conn: sqlite3.Connection, directory: Path, params: dict) -> list[str]:
    applied = []
    for path in sorted(directory.glob("*.sql")):
        for statement in _statements(path.read_text()):
            conn.execute(statement, params)
        applied.append(path.name)
    return applied


def run(db_path: Path, run_id: str = fx.RUN_ID) -> dict:
    conn = connect(db_path)
    try:
        params = {"run_id": run_id, "mapping_version": fx.MAPPING_VERSION}

        conn.execute(
            "UPDATE pipeline_run SET status='VALIDATING' WHERE run_id=?", (run_id,)
        )
        transforms = _apply(conn, TRANSFORM_DIR, params)
        rules = _apply(conn, QUALITY_DIR, params)

        failures = conn.execute(
            "SELECT rule_id, market_id, month_start, failing_row_count "
            "FROM dq_result "
            "WHERE run_id=? AND severity='BLOCKING' AND disposition='FAIL' "
            "ORDER BY rule_id, market_id, month_start",
            (run_id,),
        ).fetchall()

        status = "FAILED" if failures else "READY_FOR_REVIEW"
        conn.execute(
            "UPDATE pipeline_run SET status=? WHERE run_id=?", (status, run_id)
        )
        conn.commit()

        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "eligibility_span", "fact_member_month", "claim_header_version",
                "claim_line_version", "fact_claim_header_final",
                "fact_claim_line_final", "fact_payment_transaction",
                "fact_capitation_transaction", "dq_result",
            )
        }
        return {
            "status": status,
            "transforms": transforms,
            "rules": rules,
            "counts": counts,
            "failures": failures,
        }
    finally:
        conn.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args(argv)

    if not args.db.exists():
        print(f"no database at {args.db}; run build_fixture first")
        return 2

    result = run(args.db)
    print(f"applied {len(result['transforms'])} transformations, "
          f"{len(result['rules'])} quality files")
    for table in sorted(result["counts"]):
        print(f"  {result['counts'][table]:>4}  {table}")

    print(f"\nrun status: {result['status']}")
    if result["failures"]:
        print("blocking failures:")
        for rule_id, market, month, failing in result["failures"]:
            where = "" if market == "ALL" else f" [{market} {month}]"
            print(f"  {rule_id}{where}: {failing} failing")
        print("\nThe fixture plants defects on purpose, so a failing run here is "
              "the controls working rather than a broken pipeline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
