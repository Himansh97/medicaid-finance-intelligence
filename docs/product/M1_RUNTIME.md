# M1 local runtime

M1 implements PostgreSQL fixture processing, a local API and durable worker. It is a development runtime, not the finished finance application. No authentication, uploads, approval UI, certified snapshots, React client or identity provider is implemented here; those start in M2/M3. Only two built-in fabricated scenarios can be submitted.

## Start

Prerequisites: Docker Engine/Desktop with Compose v2, Python 3 for the bootstrap/smoke script. From the repository root:

```sh
./scripts/dev-up.sh
python3 scripts/smoke_runtime.py
```

The bootstrap generates a private `.env` password only when absent, then builds and starts PostgreSQL, a one-shot Alembic migration, the API and worker. A named volume preserves data. Existing `.env` is never overwritten. Changing its database password does not change the password already stored in an existing PostgreSQL volume.

Open http://localhost:8000/docs for the interactive API. Bindings are loopback only; no PostgreSQL port is published. Do not expose this unauthenticated runtime to a network. `APP_ENV=local` is required. Use `API_PORT` in `.env` to change the host port; pass the matching URL to the smoke script. Docker checks migration completion and database readiness before starting consumers.

```sh
docker compose ps
docker compose logs --tail 50 api worker
docker compose stop worker
docker compose start worker
docker compose down
```

`down` retains the volume. Do not use `down -v` unless you intend to delete local synthetic jobs/results. Starting again reruns the no-op migration at the current version. M1 has a first migration and repeated-upgrade test; future nontrivial schema upgrades require their own data-preservation tests.

## API flow

POST `/jobs` with JSON `{"scenario":"clean","idempotency_key":"my-first-run"}`. Repeating the same request returns the same job. Reusing a key for a different scenario returns 409. Only `clean` and `defective` are accepted; extra fields and invalid keys are rejected.

Poll GET `/jobs/{id}`. After SUCCEEDED, GET `/runs/{id}`, `/runs/{id}/quality`, `/runs/{id}/kpis` and `/runs/{id}/preflight`. Results before completion return 409. The URL ID is the unique job UUID; inner `run_id` is the canonical fixture identifier scoped to that job's private schema.

Processing status and financial quality are distinct: the defective scenario completes its job successfully but has three financial/data-quality blockers and is not eligible for submission. None of the outputs is certified. KPI results retain availability labels and numerator/denominator components.

`/health/live` tests the HTTP process. `/health/ready` checks the database and expected migration. It does not assert worker health; inspect job progress/worker logs when jobs remain queued.

## Persistence and transaction design

Alembic owns the shared `operations.jobs` queue. Each job receives a `run_<uuid>` PostgreSQL schema because the original fixture uses fixed surrogate keys. This is deliberate M1 isolation, not a multi-tenant design or a long-term large-volume storage claim. There is no automatic schema cleanup. Before larger uploaded workloads, evaluate schema growth and migrate to run-qualified shared fact keys if appropriate.

Financial schema/SQL is instantiated from the existing canonical scripts inside the worker transaction; existing completed job results are retained rather than rebuilt on application restart. SQL portability changes are explicit: monetary cents use BIGINT, `instr` becomes `strpos`, ledger grouping includes run ID, and HAVING references expand SELECT aliases. Native PostgreSQL executes the transformations—SQLite is a reference test engine only.

Workers claim jobs with row locks and SKIP LOCKED, a unique lease token and a 120-second expiry. Three attempts bound retries. Fixture writes and result publication commit together. Expired/stale workers cannot publish; their transaction rolls back. Hard termination leaves a claim that another worker can reclaim after expiry. Statement timeout is 100 seconds; this intentionally supports the small M1 fixtures. Long jobs and heartbeat renewal need a later design before scaling.

Failure codes are generic to avoid leaking SQL or credentials. Stored results are replayable M1 artifacts, not the immutable, independently approved release manifests planned for M3.

## Verification commands

```sh
python -m pip install -r requirements-dev.txt
# Use a disposable test database: tests manipulate queued test jobs and create schemas/databases.
PG_TEST_DSN=postgresql://USER:PASSWORD@localhost:5432/TEST_DATABASE python -m pytest -q
```

Without PG_TEST_DSN the PostgreSQL tests skip explicitly. CI supplies PostgreSQL and separately builds Compose and exercises both scenarios. Never point PG_TEST_DSN at a database containing work you want to preserve.

## References

- PostgreSQL locking and SKIP LOCKED: https://www.postgresql.org/docs/16/sql-select.html
- FastAPI container deployment: https://fastapi.tiangolo.com/deployment/docker/
- Compose readiness and startup order: https://docs.docker.com/compose/how-tos/startup-order/


## Verified on this branch

Full suite with PostgreSQL 16.15: 189 passed, ten optional source-data tests skipped. A Starlette/httpx deprecation warning is upstream and does not fail the tests. Local Compose built successfully and both HTTP smoke scenarios passed. The clean scenario passed all 14 rules; the defective scenario retained three intentional blockers. No full-product or real-data readiness is claimed.

Live recovery check: queued a clean job while the worker was stopped, restarted it, observed one successful attempt, repeated submission with the same key, and reran the migration. Job ID and stored results were unchanged.
