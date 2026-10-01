# Product implementation roadmap

Local Docker first, then Azure. Status labels reflect verified implementation, not planned capabilities. No calendar promises before the PostgreSQL/runtime spike establishes effort. Each milestone has a reviewable PR and a tested acceptance gate.

## Work completed in this branch

M0 specification and roadmap written. Read-only preflight implemented with 13 tests. Full suite: 177 passed, ten optional source checks skipped. Mutation removing blockers caused nine expected failures. Population rule v3 excludes legitimate out-of-cohort records from failure counts; regression verifies KPI exclusion. Docker executable detected, daemon responsiveness not verified. M1 and later remain planned.

## Current baseline

Audit fixes merged at b6a0fd8. Existing SQLite schema, fabricated fixture, transformations, quality rules and KPI views; separate public CMS archive/extracts. Baseline: 164 passing tests and ten optional source checks. No application, authenticated approval flow, immutable reporting releases, PostgreSQL deployment, Docker stack, dashboard or AI integration yet.

## Milestones and dependencies

| ID | Deliverable | Depends on | Exit evidence |
|---|---|---|---|
| M0 | Product specification, architecture decisions, executable release preflight | Existing audited pipeline | Failed/incomplete/unevaluated rule evidence blocks readiness; repaired fixture passes; no mutation |
| M1 | PostgreSQL adapter/migrations, FastAPI structure, durable jobs, Docker services | M0 | Fresh compose start and upgrade work; SQLite/PostgreSQL acceptance parity; worker restart does not duplicate results |
| M2 | OIDC login, roles/market authorization, synthetic upload templates, versioned batches | M1 | API permission matrix passes; upload limits/types/idempotency verified; UI shows recoverable errors |
| M3 | Analyst quality workspace and immutable submission/approval/release flow | M2 | Self/unauthorized approval denied; missing rule/partition/warning prevents certification; failed publication is atomic |
| M4 | Finance dashboard, deterministic variance, period readiness, anomaly review | M3 | Components reconcile; comparable release selection enforced; quiet-history/provisional scenarios correct |
| M5 | CSV/PDF reports and tested Power BI certified model | M4 | Screen/API/exports/Power BI agree; same release/filter/access restrictions; no draft leakage |
| M6 | Governed AI explanation with evidence validation and cost limits | M4, M5 | Live configured provider tested; unavailable-provider fallback honest; injection/unsupported claims rejected |
| M7 | Separate CMS explorer integrated into app navigation | M2, audited SDP files | Source links and missing/lineage caveats visible; no finance-data mixing |
| M8 | Local release hardening and user acceptance | M1–M7 | Setup/upgrade/restore/security/accessibility/end-to-end/performance checks documented; reviewer completes workflow |
| M9 | Azure infrastructure, deployment, identity and operational verification | M8, account and budget | Staging smoke/rollback/restore drills pass; secrets external; HTTPS and monitoring verified |

The product is not called finished after M0 or a polished UI. Full local release requires M8; Azure readiness requires M9. Real patient-data operation is not authorized by this roadmap.

## Implementation breakdown

### M0 — start now

Files: `src/releases/preflight.py`, `tests/test_release_preflight.py`, this specification/roadmap and HANDOFF.
- Define a versioned expected rule inventory: eight run-wide checks plus one market/month feed check for each expected claims partition.
- Add read-only assessment returning run ID, eligibility for submission, reason codes and evidence counts. Treat unknown run, wrong status, absent rules, unexpected/stale versions, failures, NOT_EVALUATED and unresolved warnings as blockers.
- Verify with the existing intentionally defective fixture and a clean test scenario that fixes input defects before rerunning. Never make bad data pass by changing stored rule results.
- Tests deliberately remove a rule, change its version, mark it unevaluated or spoof the run status. Assert refusal and unchanged database.
- This is the first control, not full certification. No authenticated approval or immutable release is claimed.

### M1 — runtime and persistence

First inventory every SQLite-only SQL feature and choose explicit PostgreSQL equivalents. Preserve integer cents and tested result grains. Add Alembic migrations and a database adapter; keep domain code independent of HTTP. FastAPI endpoints start with health/readiness, run status and preflight. Add a database-backed job table with claim leases, retry limits, idempotency and failure reasons. Use transaction boundaries around state transitions. Compose starts PostgreSQL/API/worker/web/identity services; add `.env.example`, bootstrap and health checks. CI runs PostgreSQL integration tests and fresh startup. Pin supported versions after checking official documentation and available runtimes.

### M2–M3 — usable, authorized workflow

Implement authentication and permission enforcement before exposing uploads or approval actions. Define versioned CSV contracts with examples and aggregate size limits. Build React pages for batches, job status, quality issues, draft results and approvals. Corrections create new immutable batches. Database-level transitions and uniqueness protect approval from concurrent requests. Store warning decisions and release manifests; approved outputs are snapshots, not mutable views. Test independent analyst/approver sessions through browser and direct API calls.

### M4 — financial investigation

Build 24-month synthetic scenarios with ordinary seasonal variation, meaningful shifts, corrections and late-arriving data. Add exact variance components before anomaly scores. Include market/category contributions, drilldown and analyst notes. Threshold settings and definitions are versioned. Every visual shows release, cohort, time basis, cutoff and provisional status. Market access filters are applied before aggregation. Test all-market totals and authorized subsets independently.

### M5–M7 — integrations

CSV exports escape spreadsheet-formula injection and include metadata; PDFs render and are visually checked. Power BI receives only certified aggregate tables and reproduces SQL ratios. AI receives an allowlist of evidence records, with cited facts validated after generation; a mock provider is only for tests. CMS explorer uses separate endpoints and public aggregates; unresolved source lineage cannot be promoted to verified fact through UI wording.

### M8–M9 — shipping

Write operator and user guides alongside features. Complete fresh-machine installation and database upgrade tests. Restore backups in an isolated environment, compare snapshot hashes and published totals, simulate worker interruption, test access restrictions and measure workload performance. Tag a local release only after the acceptance checklist passes. For Azure, confirm budget and identity/account access, select hosting using current official guidance, provision staging, verify deployment rollback, and promote only with the user's deployment authorization.

## Work order and review rules

One milestone at a time; dependencies are not optional. Keep branch work separate from main and make CI evidence visible in every PR. No mock API, sample screenshot or planned infrastructure counts as a working integration. Every handoff names completed work, exact checks run, known limits and the next runnable task.

## Decisions and external dependencies

Confirmed: local Docker followed by Azure. Working assumption: one organization, single deployment, several markets; synthetic uploads only. Need before M2: identity provider account choices and final role matrix. Need before M5: available Power BI authoring/sharing environment. Need before M6: LLM provider credentials and spend limit. Need before M9: Azure subscription, region, budget and deployment permission. Those do not block M0.
