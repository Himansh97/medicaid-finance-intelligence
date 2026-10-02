"""Read-only submission preflight for the synthetic SQLite pipeline.

This checks recorded evidence; it neither authenticates an approver nor creates
a certified snapshot. Run it again inside the future submission transaction.

    python -m src.releases.preflight --db data/processed/fixture.db --run-id RUN_FIXTURE_0001
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

# Versioned contract, deliberately independent from the result rows being tested.
# A missing rule cannot remove itself from the required inventory.
POLICY_VERSION = 'submission-preflight-v1'
RUN_RULES = {
    'DQ_ELIG_DUPLICATE_KEY': 'v1',
    'DQ_ELIG_UNRESOLVED_REFERENCE': 'v1',
    'DQ_LINE_UNMAPPED_SERVICE_CODE': 'v1',
    'DQ_MM_CONFLICTING_ASSIGNMENT': 'v1',
    'DQ_CLAIM_POPULATION_MATCH': 'v3',
    'DQ_HEADER_LINE_BALANCE': 'v1',
    'DQ_LEDGER_RECONCILES_TO_CLAIMS': 'v1',
    'DQ_CAPITATION_CORRECTION_LINKED': 'v1',
}


def assess_evidence(status, partitions, rows, run_id: str) -> dict:
    """Evaluate the same evidence contract for SQLite and PostgreSQL adapters."""
    result = dict(run_id=run_id, policy_version=POLICY_VERSION,
                  eligible_for_submission=False, expected_checks=0,
                  observed_checks=0, blockers=[])
    blockers = result['blockers']

    def block(code, **context):
        blockers.append(dict(code=code, **context))

    if status is None:
        block('UNKNOWN_RUN')
        return result
    if status != 'READY_FOR_REVIEW':
        block('RUN_NOT_READY', status=status)
    if not partitions:
        block('NO_EXPECTED_PARTITIONS')
    expected = {(rule, version, 'ALL', 'ALL') for rule, version in RUN_RULES.items()}
    expected.update(('DQ_MISSING_MARKET_FEED', 'v1', r['market_id'], r['month_start']) for r in partitions)
    result['expected_checks'] = len(expected)
    result['observed_checks'] = len(rows)
    seen = set()
    for row in rows:
        key = (row['rule_id'], row['rule_version'], row['market_id'], row['month_start'])
        context = dict(rule_id=key[0], rule_version=key[1], market_id=key[2], month_start=key[3])
        if key in seen:
            block('DUPLICATE_CHECK', **context)
        seen.add(key)
        if key not in expected:
            block('UNEXPECTED_CHECK', **context)
        # No warning disposition mechanism exists yet. Fail closed even if
        # somebody has written ACCEPTED_WITH_REASON without evidence.
        if (row['severity'] != 'BLOCKING' or row['disposition'] != 'PASS'
                or row['failing_row_count'] != 0):
            block('RULE_NOT_PASSED', **context, disposition=row['disposition'])
    for rule, version, market, month in sorted(expected - seen):
        block('MISSING_CHECK', rule_id=rule, rule_version=version,
              market_id=market, month_start=month)
    result['eligible_for_submission'] = not blockers
    return result


def assess(db_path: Path, run_id: str) -> dict:
    """Read SQLite evidence in one transaction without changing the database."""
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('BEGIN')
        run = conn.execute('SELECT status FROM pipeline_run WHERE run_id=?', (run_id,)).fetchone()
        partitions = conn.execute(
            "SELECT market_id, month_start FROM expected_partition WHERE run_id=? AND entity='claims' ORDER BY market_id, month_start",
            (run_id,)).fetchall()
        rows = conn.execute('SELECT * FROM dq_result WHERE run_id=? ORDER BY rule_id, rule_version, market_id, month_start', (run_id,)).fetchall()
        return assess_evidence(run['status'] if run else None, partitions, rows, run_id)
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args(argv)
    try:
        result = assess(args.db, args.run_id)
    except (FileNotFoundError, sqlite3.Error) as exc:
        print(json.dumps({'eligible_for_submission': False, 'error': str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result['eligible_for_submission'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
