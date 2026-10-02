"""Real PostgreSQL acceptance parity; opt in with PG_TEST_DSN."""
import json
import os
import sqlite3
import uuid

import pytest

from src.data_generation import fixture as fx
from src.data_generation.build_fixture import build, connect
from src.validation.run_pipeline import run
from src.releases.preflight import assess


@pytest.fixture
def pg():
    dsn = os.getenv('PG_TEST_DSN')
    if not dsn:
        pytest.skip('PG_TEST_DSN is not configured')
    import psycopg
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        yield conn
        conn.rollback()


def ordered(rows):
    return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))


@pytest.mark.postgres
@pytest.mark.parametrize('scenario', ['defective', 'clean'])
def test_postgres_matches_sqlite(pg, tmp_path, scenario):
    from src.runtime.postgres import execute_fixture
    db = tmp_path / 'baseline.db'
    build(db)
    if scenario == 'clean':
        with connect(db) as conn:
            conn.execute("DELETE FROM raw_eligibility_span WHERE source_row_id='ELG_008'")
            conn.execute("UPDATE raw_claim_line SET service_code='SVC_PROF_01' WHERE service_code='SVC_UNMAPPED_99'")
            conn.execute('INSERT INTO source_file VALUES (?,?,?,?,?,?,?,?,?)', (
                'EMPTY_C_FEB', fx.RUN_ID, 'synthetic', 'claims', 'SYN_MKT_C',
                '2026-02-01', 'empty', 0, fx.INGESTED_AT))
    baseline = run(db)
    schema = 'run_' + uuid.uuid4().hex
    result = execute_fixture(pg, schema, scenario)
    assert result['run_id'] == fx.RUN_ID
    assert result['status'] == baseline['status']
    assert result['counts'] == baseline['counts']
    assert result['preflight'] == assess(db, fx.RUN_ID)
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        views = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view' AND name LIKE 'v_kpi_%'")]
        assert set(result['kpis']) == set(views)
        for view in views:
            expected = ordered([dict(r) for r in conn.execute('SELECT * FROM ' + view)])
            actual = ordered(result['kpis'][view])
            assert len(actual) == len(expected)
            for left, right in zip(actual, expected):
                assert left == pytest.approx(right)
        assert ordered(result['quality']) == ordered([dict(r) for r in conn.execute('SELECT * FROM dq_result')])
    assert json.loads(json.dumps(result)) == result
    assert execute_fixture(pg, schema, scenario) == result
    with pytest.raises(ValueError, match='different fixture scenario'):
        execute_fixture(pg, schema, 'clean' if scenario == 'defective' else 'defective')
    cents_types = pg.execute("SELECT DISTINCT data_type FROM information_schema.columns WHERE table_schema=%s AND column_name LIKE '%%cents' AND table_name NOT LIKE 'v_%%'", (schema,)).fetchall()
    assert cents_types == [('bigint',)]
    pg.rollback()
    assert pg.execute('SELECT to_regnamespace(%s)', (schema,)).fetchone()[0] is None


def test_rejects_unsafe_schema_before_database_access():
    from src.runtime.postgres import execute_fixture
    with pytest.raises(ValueError):
        execute_fixture(None, 'public')
