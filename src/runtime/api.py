"""Unauthenticated synthetic-only API: local loopback deployments only."""
from contextlib import asynccontextmanager
import os
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
import psycopg

from src.runtime import jobs


@asynccontextmanager
async def lifespan(app):
    if os.environ.get('APP_ENV') != 'local':
        raise RuntimeError('The M1 API requires APP_ENV=local')
    yield


app = FastAPI(title='Synthetic finance local runtime', lifespan=lifespan)


class JobRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario: Literal['clean', 'defective']
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_.:-]+$')


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(status_code=422, content={'detail': 'Invalid request'})


@app.exception_handler(psycopg.Error)
async def database_error(request, exc):
    return JSONResponse(status_code=503, content={'detail': 'Database unavailable'})


@app.get('/health/live')
def live():
    return {'status': 'ok'}


@app.get('/health/ready')
def ready():
    with jobs.connect() as conn:
        conn.execute('SELECT id FROM operations.jobs LIMIT 0')
        revision = conn.execute('SELECT version_num FROM alembic_version').fetchone()
        if revision is None or revision['version_num'] != '0001_jobs':
            raise HTTPException(503, 'Database migration required')
    return {'status': 'ready'}


@app.post('/jobs', status_code=202)
def submit(request: JobRequest):
    try:
        with jobs.connect() as conn:
            return jobs.public_job(jobs.submit(conn, request.scenario, request.idempotency_key))
    except jobs.IdempotencyConflict:
        raise HTTPException(409, 'Idempotency key belongs to a different request') from None


def lookup(job_id):
    with jobs.connect() as conn:
        job = jobs.get(conn, job_id)
    if job is None:
        raise HTTPException(404, 'Job not found')
    return job


@app.get('/jobs/{job_id}')
def job_status(job_id: UUID):
    return jobs.public_job(lookup(job_id))


def result(job_id):
    job = lookup(job_id)
    if job['status'] != 'SUCCEEDED':
        raise HTTPException(409, 'Run results are not available')
    return job['result']


@app.get('/runs/{job_id}')
def run_result(job_id: UUID):
    return result(job_id)


@app.get('/runs/{job_id}/quality')
def quality(job_id: UUID):
    return result(job_id)['quality']


@app.get('/runs/{job_id}/kpis')
def kpis(job_id: UUID):
    return result(job_id)['kpis']


@app.get('/runs/{job_id}/preflight')
def preflight(job_id: UUID):
    return result(job_id)['preflight']
