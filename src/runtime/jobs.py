"""Durable bounded-retry queue. No uploaded records or executable inputs."""
import os
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class IdempotencyConflict(ValueError):
    pass


class LostLease(RuntimeError):
    pass


def connect():
    return psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, connect_timeout=5)


def submit(conn, scenario: str, idempotency_key: str):
    if scenario not in ('clean', 'defective') or not 1 <= len(idempotency_key) <= 128:
        raise ValueError('Invalid synthetic job request')
    job = conn.execute('''INSERT INTO operations.jobs (id, scenario, idempotency_key)
        VALUES (%s,%s,%s) ON CONFLICT (idempotency_key) DO NOTHING RETURNING *''',
        (uuid4(), scenario, idempotency_key)).fetchone()
    if job is None:
        job = conn.execute('SELECT * FROM operations.jobs WHERE idempotency_key=%s',
                           (idempotency_key,)).fetchone()
        if job['scenario'] != scenario:
            raise IdempotencyConflict('Idempotency key belongs to a different request')
    return job


def get(conn, job_id: UUID):
    return conn.execute('SELECT * FROM operations.jobs WHERE id=%s', (job_id,)).fetchone()


def claim(conn, lease_seconds=120):
    if not 1 <= lease_seconds <= 3600:
        raise ValueError('Invalid lease duration')
    # Exhausted abandoned work is terminal; no worker may publish with its old token.
    conn.execute('''UPDATE operations.jobs SET status='FAILED', error_code='RETRY_EXHAUSTED',
        lease_token=NULL, lease_expires_at=NULL, updated_at=clock_timestamp()
        WHERE status='RUNNING' AND lease_expires_at <= clock_timestamp()
        AND attempts >= max_attempts''')
    return conn.execute('''WITH candidate AS (
        SELECT id FROM operations.jobs WHERE attempts < max_attempts AND
        (status='QUEUED' OR (status='RUNNING' AND lease_expires_at <= clock_timestamp()))
        ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1
    ) UPDATE operations.jobs j SET status='RUNNING', attempts=attempts+1,
        lease_token=%s, lease_expires_at=clock_timestamp() + %s * interval '1 second',
        updated_at=clock_timestamp(), error_code=NULL
        FROM candidate c WHERE j.id=c.id RETURNING j.*''',
        (uuid4(), lease_seconds)).fetchone()


def finish(conn, job, result):
    row = conn.execute('''UPDATE operations.jobs SET status='SUCCEEDED', result=%s,
        lease_token=NULL, lease_expires_at=NULL, updated_at=clock_timestamp()
        WHERE id=%s AND status='RUNNING' AND lease_token=%s
        AND lease_expires_at > clock_timestamp() RETURNING id''',
        (Jsonb(result), job['id'], job['lease_token'])).fetchone()
    if row is None:
        # Raising within the fixture transaction rolls back all its domain writes too.
        raise LostLease('Job lease is no longer valid')


def fail(conn, job):
    conn.execute('''UPDATE operations.jobs SET
        status=CASE WHEN attempts < max_attempts THEN 'QUEUED' ELSE 'FAILED' END,
        error_code='PROCESSING_ERROR', lease_token=NULL, lease_expires_at=NULL,
        updated_at=clock_timestamp() WHERE id=%s AND status='RUNNING' AND lease_token=%s
        AND lease_expires_at > clock_timestamp()''', (job['id'], job['lease_token']))


def public_job(job):
    return {key: job[key] for key in
            ('id', 'scenario', 'status', 'attempts', 'max_attempts', 'created_at', 'updated_at', 'error_code')}
