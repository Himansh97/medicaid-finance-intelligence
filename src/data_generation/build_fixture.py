"""Create the fixture database: apply the schema, load reference data and the
raw landing tables.

    python -m src.data_generation.build_fixture [--db PATH]

Rebuilding replaces the file. The database is a derived artifact and is not
committed; data/ is ignored except for its placeholders.

This loads raw input and dimensions only. The curated member-month and final
claim tables are created empty on purpose: filling them requires eligibility and
claim-version resolution, which is the next task and not something this script
should quietly do first.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sqlite3
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data_generation import fixture as fx

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "sql" / "schema"
DEFAULT_DB = ROOT / "data" / "processed" / "fixture.db"

# Which fixture rows belong to which landed file. Splitting claims by market is
# what makes a missing market feed expressible: the February market C file is
# simply never created.
FILES = [
    ("SRC_ELIG_2026Q1", "eligibility", None),
    ("SRC_CLAIMS_2026Q1", "claims", None),
    ("SRC_PAY_2026Q1", "payments", None),
    ("SRC_CAP_2026Q1", "capitation", None),
]


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    # Not the default in SQLite. Without it every REFERENCES clause in the schema
    # is a comment.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_schema(conn: sqlite3.Connection) -> list[str]:
    applied = []
    for path in sorted(SCHEMA_DIR.glob("*.sql")):
        conn.executescript(path.read_text())
        applied.append(path.name)
    return applied


def _hash(rows) -> str:
    return hashlib.sha256(repr(rows).encode()).hexdigest()[:16]


def load(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}

    def insert(table: str, rows) -> None:
        # Derived from the table rather than passed in. A hardcoded count drifts
        # the moment a column is added, and the failure reads as a data problem.
        columns = len(conn.execute(f"PRAGMA table_info({table})").fetchall())
        if rows and len(rows[0]) != columns:
            raise ValueError(
                f"{table} has {columns} columns; fixture row has {len(rows[0])}"
            )
        conn.executemany(
            f"INSERT INTO {table} VALUES ({','.join('?' * columns)})", rows
        )
        counts[table] = counts.get(table, 0) + len(rows)

    conn.execute(
        "INSERT INTO pipeline_run VALUES (?,?,?,?,?,?,?,?,?)",
        (fx.RUN_ID, fx.SCENARIO_ID, fx.SEED, _hash(fx.CASE_COVERAGE),
         fx.CODE_VERSION, fx.AS_OF_CUTOFF, fx.INGESTED_AT, None, "CREATED"),
    )
    counts["pipeline_run"] = 1

    raw = {
        "eligibility": fx.raw_eligibility_rows,
        "claims": None,
        "payments": fx.raw_payment_rows,
        "capitation": fx.raw_capitation_rows,
    }

    for file_id, entity, market_id in FILES:
        if entity == "claims":
            rows = fx.raw_claim_header_rows(file_id) + fx.raw_claim_line_rows(file_id)
        else:
            rows = raw[entity](file_id)
        conn.execute(
            "INSERT INTO source_file VALUES (?,?,?,?,?,?,?,?)",
            (file_id, fx.RUN_ID, "synthetic", entity, market_id,
             _hash(rows), len(rows), fx.INGESTED_AT),
        )
        counts["source_file"] = counts.get("source_file", 0) + 1

    insert("dim_market", fx.MARKETS)
    insert("dim_member", fx.MEMBERS)
    insert("dim_plan", fx.PLANS)
    insert("dim_provider", fx.PROVIDERS)
    insert("dim_service_category", fx.CATEGORIES)
    insert("service_category_map", fx.CATEGORY_MAP)
    insert("dim_date", fx.dim_date_rows())

    insert("raw_eligibility_span", fx.raw_eligibility_rows("SRC_ELIG_2026Q1"))
    insert("raw_claim_header", fx.raw_claim_header_rows("SRC_CLAIMS_2026Q1"))
    insert("raw_claim_line", fx.raw_claim_line_rows("SRC_CLAIMS_2026Q1"))
    insert("raw_payment_transaction", fx.raw_payment_rows("SRC_PAY_2026Q1"))
    insert("raw_capitation_transaction", fx.raw_capitation_rows("SRC_CAP_2026Q1"))

    insert("expected_partition", fx.expected_partitions())
    insert("expected_defect", [(fx.SCENARIO_ID, *d) for d in fx.EXPECTED_DEFECTS])

    conn.commit()
    return counts


def build(db_path: Path) -> dict[str, int]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = connect(db_path)
    try:
        apply_schema(conn)
        return load(conn)
    finally:
        conn.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args(argv)

    counts = build(args.db)
    print(f"built {args.db}")
    for table in sorted(counts):
        print(f"  {counts[table]:>4}  {table}")
    print("\ncurated tables are intentionally empty; resolution is the next task")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
