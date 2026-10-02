import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from src.runtime.api import app
from src.runtime import jobs, worker
from test_runtime_jobs import database


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'local')
    with TestClient(app) as client:
        yield client


def test_local_only(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    with pytest.raises(RuntimeError, match='APP_ENV=local'), TestClient(app):
        pass


def test_validation_no_input_echo(client):
    assert client.get('/health/live').status_code == 200
    for payload in ({'scenario': 'upload', 'idempotency_key': 'x'},
                    {'scenario': 'clean', 'idempotency_key': 'x', 'sql': 'sensitive'},
                    {'scenario': 'clean', 'idempotency_key': ''}):
        response = client.post('/jobs', json=payload)
        assert response.status_code == 422
        assert response.json() == {'detail': 'Invalid request'}
    assert client.get('/jobs/not-a-uuid').status_code == 422


@pytest.mark.postgres
@pytest.mark.parametrize('scenario', ['clean', 'defective'])
def test_api_end_to_end(database, client, scenario):
    assert client.get('/health/ready').status_code == 200
    key = str(uuid4())
    response = client.post('/jobs', json={'scenario': scenario, 'idempotency_key': key})
    assert response.status_code == 202
    job_id = response.json()['id']
    assert 'lease_token' not in response.json()
    assert client.post('/jobs', json={'scenario': scenario, 'idempotency_key': key}).json()['id'] == job_id
    assert client.post('/jobs', json={'scenario': 'defective' if scenario == 'clean' else 'clean', 'idempotency_key': key}).status_code == 409
    assert client.get(f'/runs/{job_id}').status_code == 409
    with jobs.connect() as conn:
        conn.execute("UPDATE operations.jobs SET status='FAILED', error_code='TEST_CLEANUP' WHERE status='QUEUED' AND id<>%s", (job_id,))
    assert worker.run_once()
    assert client.get(f'/jobs/{job_id}').json()['status'] == 'SUCCEEDED'
    result = client.get(f'/runs/{job_id}').json()
    for part in ('quality', 'kpis', 'preflight'):
        assert client.get(f'/runs/{job_id}/{part}').json() == result[part]
    assert client.get(f'/jobs/{uuid4()}').status_code == 404
