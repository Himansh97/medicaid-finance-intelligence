"""Real PostgreSQL concurrency, transaction fencing and restart evidence."""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import psycopg
from psycopg.rows import dict_row
from alembic import command
from alembic.config import Config

from src.runtime import jobs, worker


@pytest.fixture
def database(monkeypatch):
    dsn = os.environ.get('PG_TEST_DSN')
    if not dsn:
        pytest.skip('PG_TEST_DSN is not configured')
    monkeypatch.setenv('DATABASE_URL', dsn)
    command.upgrade(Config('alembic.ini'), 'head')
    return dsn


def submit(scenario='clean', key=None):
    with jobs.connect() as conn:
        return jobs.submit(conn, scenario, key or str(uuid4()))


@pytest.mark.postgres
def test_idempotency_concurrent(database):
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: submit(key=key)['id'], range(4)))
    assert len(set(ids)) == 1
    with jobs.connect() as conn, pytest.raises(jobs.IdempotencyConflict):
        jobs.submit(conn, 'defective', key)


@pytest.mark.postgres
def test_restart_fences_old_worker_and_bounds_retries(database):
    job = submit()
    with jobs.connect() as conn:
        # Limit claims to our row, avoiding leftover work from other tests.
        conn.execute("UPDATE operations.jobs SET status='FAILED', error_code='TEST_CLEANUP' WHERE status='QUEUED' AND id<>%s", (job['id'],))
        first = jobs.claim(conn)
    with jobs.connect() as conn:
        conn.execute("UPDATE operations.jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", (job['id'],))
    with jobs.connect() as conn:
        second = jobs.claim(conn)
    assert second['id'] == first['id']
    assert second['attempts'] == 2
    schema = 'stale_' + uuid4().hex
    with pytest.raises(jobs.LostLease), jobs.connect() as conn:
        conn.execute(f'CREATE SCHEMA {schema}')
        jobs.finish(conn, first, {'stale': True})
    with jobs.connect() as conn:
        assert conn.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s', (schema,)).fetchone() is None
        jobs.finish(conn, second, {'status': 'FAILED'})
    with jobs.connect() as conn:
        saved = jobs.get(conn, job['id'])
    assert saved['status'] == 'SUCCEEDED'
    assert saved['result'] == {'status': 'FAILED'}


@pytest.mark.postgres
def test_claim_concurrency_and_exhaustion(database):
    with jobs.connect() as conn:
        conn.execute("UPDATE operations.jobs SET status='FAILED', error_code='TEST_CLEANUP' WHERE status='QUEUED'")
    created = [submit() for _ in range(4)]
    def claim_one(_):
        with jobs.connect() as conn:
            return jobs.claim(conn)
    with ThreadPoolExecutor(max_workers=4) as pool:
        claimed = list(pool.map(claim_one, range(4)))
    assert {row['id'] for row in claimed} == {row['id'] for row in created}
    for row in claimed:
        with jobs.connect() as conn:
            conn.execute("UPDATE operations.jobs SET attempts=max_attempts, lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", (row['id'],))
    with jobs.connect() as conn:
        assert jobs.claim(conn) is None
        assert all(jobs.get(conn, row['id'])['status'] == 'FAILED' for row in created)


@pytest.mark.postgres
def test_worker_rolls_back_failed_attempt(database, monkeypatch):
    job = submit()
    with jobs.connect() as conn:
        conn.execute("UPDATE operations.jobs SET status='FAILED', error_code='TEST_CLEANUP' WHERE status='QUEUED' AND id<>%s", (job['id'],))
    def broken(conn, schema, scenario):
        conn.execute(f'CREATE SCHEMA {schema}')
        raise RuntimeError('sensitive exception content')
    for _ in range(3):
        assert worker.run_once(broken)
    assert not worker.run_once(broken)
    with jobs.connect() as conn:
        saved = jobs.get(conn, job['id'])
        assert saved['status'] == 'FAILED'
        assert saved['attempts'] == 3
        assert saved['error_code'] == 'PROCESSING_ERROR'
        assert conn.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s', ('run_' + job['id'].hex,)).fetchone() is None


@pytest.mark.postgres
def test_migration_fresh_and_upgrade(database, monkeypatch):
    # A separate database verifies an empty install and a no-op existing upgrade.
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict
    from sqlalchemy.engine import URL
    name = 'migration_' + uuid4().hex
    with psycopg.connect(database, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            params = conninfo_to_dict(database)
            params['dbname'] = name
            isolated = URL.create('postgresql+psycopg', username=params.get('user'), password=params.get('password'), host=params.get('host'), port=int(params['port']) if params.get('port') else None, database=name).render_as_string(hide_password=False)
            monkeypatch.setenv('DATABASE_URL', isolated.replace('postgresql+psycopg://', 'postgresql://', 1))
            config = Config('alembic.ini')
            command.upgrade(config, 'head')
            command.upgrade(config, 'head')
            with jobs.connect() as conn:
                assert conn.execute('SELECT version_num FROM alembic_version').fetchone()['version_num'] == '0001_jobs'
                assert jobs.submit(conn, 'clean', 'migration-check')['status'] == 'QUEUED'
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
