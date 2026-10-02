"""Execute canonical synthetic finance SQL natively in PostgreSQL 16+.

Each job owns an isolated schema because canonical fixture keys are fixed. The
caller owns the transaction: this module never commits. SQL differences are
limited to BIGINT cents, instr -> strpos, HAVING alias expansion and explicit
ledger grouping. ISO date text and all finance definitions remain unchanged.
"""
from decimal import Decimal
from pathlib import Path
import re

from psycopg import sql
from psycopg.rows import dict_row

from src.data_generation import fixture as fx
from src.data_generation.build_fixture import ELIG_FILE, PAY_FILE, CAP_FILE, _hash, claims_file_id
from src.releases.preflight import assess_evidence
from src.validation.run_pipeline import _statements

ROOT = Path(__file__).resolve().parents[2]
COUNTS = ('eligibility_span', 'fact_member_month', 'claim_header_version',
          'claim_line_version', 'fact_claim_header_final', 'fact_claim_line_final',
          'fact_payment_transaction', 'fact_capitation_transaction', 'dq_result')


def _translate(statement):
    statement = re.sub(r'(\b\w*cents\s+)INTEGER\b', r'\1BIGINT', statement)
    statement = statement.replace('instr(', 'strpos(')
    # PostgreSQL does not allow SELECT aliases in HAVING. Correlated run_id
    # must also belong to the grouping key, even when WHERE fixes its value.
    statement = statement.replace('GROUP BY p.claim_family_key', 'GROUP BY p.run_id, p.claim_family_key')
    statement = statement.replace('HAVING ABS(ledger - final_balance) > 1', '''HAVING ABS(SUM(p.signed_amount_cents) - COALESCE((
        SELECT f.header_paid_amount_cents FROM fact_claim_header_final f
        WHERE f.run_id = p.run_id AND f.claim_family_key = p.claim_family_key), 0)) > 1''')
    return re.sub(r'(?<!:):(run_id|mapping_version)\b', r'%(\1)s', statement)


def _load(conn, scenario):
    def insert(table, rows):
        if rows:
            query = sql.SQL('INSERT INTO {} VALUES ({})').format(
                sql.Identifier(table), sql.SQL(',').join(sql.Placeholder() for _ in rows[0]))
            with conn.cursor() as cursor:
                cursor.executemany(query, rows)

    insert('pipeline_run', [(fx.RUN_ID, fx.SCENARIO_ID, fx.SEED,
        _hash(fx.CASE_COVERAGE), fx.CODE_VERSION, fx.AS_OF_CUTOFF, fx.INGESTED_AT, None, 'CREATED')])
    def register(file_id, entity, rows, market=None, month=None):
        insert('source_file', [(file_id, fx.RUN_ID, 'synthetic', entity, market,
                               month, _hash(rows), len(rows), fx.INGESTED_AT)])
    eligibility = fx.raw_eligibility_rows(ELIG_FILE)
    if scenario == 'clean':
        eligibility = [row for row in eligibility if row[1] != 'ELG_008']
    payments, capitation = fx.raw_payment_rows(PAY_FILE), fx.raw_capitation_rows(CAP_FILE)
    register(ELIG_FILE, 'eligibility', eligibility)
    register(PAY_FILE, 'payments', payments)
    register(CAP_FILE, 'capitation', capitation)
    headers, lines = [], []
    for market, month in fx.ARRIVING_CLAIMS_PARTITIONS:
        file_id = claims_file_id(market, month)
        h = fx.raw_claim_header_rows(file_id, market, month)
        l = fx.raw_claim_line_rows(file_id, market, month)
        if scenario == 'clean':
            l = [tuple('SVC_PROF_01' if value == 'SVC_UNMAPPED_99' else value for value in row) for row in l]
        register(file_id, 'claims', h + l, market, month)
        headers.extend(h)
        lines.extend(l)
    if scenario == 'clean':
        register(claims_file_id('SYN_MKT_C', '2026-02-01'), 'claims', [], 'SYN_MKT_C', '2026-02-01')
    for table, rows in (
        ('dim_market', fx.MARKETS), ('dim_member', fx.MEMBERS), ('dim_plan', fx.PLANS),
        ('dim_provider', fx.PROVIDERS), ('dim_service_category', fx.CATEGORIES),
        ('service_category_map', fx.CATEGORY_MAP), ('dim_date', fx.dim_date_rows()),
        ('raw_eligibility_span', eligibility), ('raw_claim_header', headers),
        ('raw_claim_line', lines), ('raw_payment_transaction', payments),
        ('raw_capitation_transaction', capitation), ('expected_partition', fx.expected_partitions()),
        ('expected_defect', [(fx.SCENARIO_ID, *d) for d in fx.EXPECTED_DEFECTS])):
        insert(table, rows)


def _rows(conn, query, params=None):
    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def _json_safe(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def execute_fixture(conn, schema_name, scenario='defective'):
    """Build or replay one isolated fixture; caller must commit or roll back."""
    if not re.fullmatch(r'run_[0-9a-f]{32}', schema_name):
        raise ValueError('schema_name must be run_ followed by 32 lowercase UUID hex digits')
    if scenario not in ('defective', 'clean'):
        raise ValueError('scenario must be defective or clean')
    if conn.autocommit:
        raise ValueError('execute_fixture requires a caller-owned transaction')
    conn.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(schema_name)))
    conn.execute(sql.SQL('SET LOCAL search_path TO {}, pg_catalog').format(sql.Identifier(schema_name)))
    exists = conn.execute('SELECT to_regclass(%s)', (schema_name + '.pipeline_run',)).fetchone()
    # Support connections whose configured row factory returns dictionaries.
    exists = next(iter(exists.values())) if isinstance(exists, dict) else exists[0]
    if exists is None:
        for path in sorted((ROOT / 'sql/schema').glob('*.sql')):
            for statement in _statements(path.read_text()):
                conn.execute(_translate(statement))
        conn.execute('CREATE TABLE fixture_execution (scenario TEXT PRIMARY KEY)')
        conn.execute('INSERT INTO fixture_execution VALUES (%s)', (scenario,))
        _load(conn, scenario)
        conn.execute("UPDATE pipeline_run SET status='VALIDATING'")
        params = {'run_id': fx.RUN_ID, 'mapping_version': fx.MAPPING_VERSION}
        for directory in ('transformations', 'quality', 'kpis'):
            for path in sorted((ROOT / 'sql' / directory).glob('*.sql')):
                for statement in _statements(path.read_text()):
                    translated = _translate(statement)
                    conn.execute(translated, params if '%(' in translated else None)
        conn.execute("""UPDATE pipeline_run SET status=CASE WHEN EXISTS (
            SELECT 1 FROM dq_result WHERE severity='BLOCKING' AND disposition='FAIL')
            THEN 'FAILED' ELSE 'READY_FOR_REVIEW' END""")
    stored_scenario = _rows(conn, 'SELECT scenario FROM fixture_execution')[0]['scenario']
    if stored_scenario != scenario:
        raise ValueError('schema already belongs to a different fixture scenario')
    status = _rows(conn, 'SELECT status FROM pipeline_run')[0]['status']
    if status not in ('FAILED', 'READY_FOR_REVIEW'):
        raise ValueError('existing fixture execution is incomplete')
    quality = _rows(conn, 'SELECT * FROM dq_result ORDER BY rule_id, rule_version, market_id, month_start')
    partitions = _rows(conn, "SELECT market_id, month_start FROM expected_partition WHERE entity='claims' ORDER BY market_id, month_start")
    views = _rows(conn, "SELECT table_name FROM information_schema.views WHERE table_schema=%s AND table_name LIKE 'v_kpi_%%' ORDER BY table_name", (schema_name,))
    kpis = {v['table_name']: _rows(conn, sql.SQL('SELECT * FROM {} ORDER BY 1,2,3').format(sql.Identifier(v['table_name']))) for v in views}
    counts = {table: _rows(conn, sql.SQL('SELECT COUNT(*) AS n FROM {}').format(sql.Identifier(table)))[0]['n'] for table in COUNTS}
    return _json_safe(dict(run_id=fx.RUN_ID, status=status, quality=quality, kpis=kpis,
                           counts=counts, preflight=assess_evidence(status, partitions, quality, fx.RUN_ID)))
