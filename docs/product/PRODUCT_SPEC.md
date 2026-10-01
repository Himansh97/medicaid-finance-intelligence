# Medicaid Finance Review Platform — version-one specification

Status: implementation started; not a completed or production-certified product.
Decision recorded 2026-09-30: local Docker first, then Azure. Product expansion authorized in chat after the audit repair merged as b6a0fd8.

## Outcome and scope

An analyst can load supported synthetic data, resolve validation issues, review financial movements, submit a reporting snapshot, obtain a separate approver's decision, and distribute a reproducible report. Managers can explore approved numbers and ask an AI assistant for evidence-backed explanations. Users should not need SQL or a terminal during normal operation.

The first release is for one organization, multiple fictional markets and named users. Roles: administrator, data steward, analyst, approver and read-only viewer. Server-side market restrictions apply to every query/export. An administrator does not automatically receive financial approval rights. The run submitter cannot approve their own release.

All beneficiary/claim inputs remain fabricated from scratch. The application does not detect or certify de-identification. Upload instructions and sample templates explicitly prohibit real patient information. The public CMS SDP explorer uses separate datasets, processing paths and screens; projected payments never populate synthetic finance metrics.

## Architecture decision

Choose a modular Python application with a React client and one PostgreSQL database, divided into finance, operations and public-research schemas. A separately running worker executes the same Python domain modules as the API. Durable database jobs avoid introducing another queue service initially. Private file storage uses a Docker volume locally and Azure Blob Storage through a storage interface later.

Alternatives considered:
- Streamlit plus SQLite would accelerate exploration but leave substantial work for access control, workflow and the final user interface.
- Microservices plus Spark/Fabric would increase deployment and consistency costs before the workload requires them.
- Selected FastAPI/React/PostgreSQL design supports the required workflows while keeping transactions and release consistency understandable.

Docker services: web/reverse proxy, API, worker, PostgreSQL and local identity provider. OIDC authentication uses a local provider for development and Microsoft Entra ID for Azure. Avoid implementing password storage. Browser sessions use secure server-managed cookies, CSRF protection, short-lived sessions and logout. Development identity configuration cannot silently be enabled in deployed environments.

PostgreSQL migration must prove equivalence with existing SQLite KPI examples; SQLite remains a fast unit-test adapter until parity is established. Use integer cents for monetary components. Ratios are computed from summed components. Version database changes with migrations and test both fresh installation and upgrade.

## End-to-end workflow

1. User signs in and sees only permitted markets and reporting releases.
2. Steward downloads versioned templates and uploads a synthetic batch (eligibility, claim headers/lines, payment ledger, capitation, reference mappings). Required files, column types, date formats, maximum file/row limits and source hashes are checked before processing. Uploaded names never become server paths.
3. Worker processes an immutable input snapshot. Progress and errors remain visible after a restart. Same idempotency key cannot create duplicate runs; retry creates no duplicate facts. Input corrections create a new batch rather than overwriting history.
4. Quality screen shows failed rules, counts, reconciliations and authorized synthetic record details. Mandatory failures cannot be overridden. A warning needs a recorded reason, owner and timestamp before approval.
5. Analyst reviews draft KPI and variance views labeled uncertified. Provisional periods retain that label even if every data check passes.
6. Analyst submits an immutable candidate with definition/rule/mapping/code versions, cutoff, cohort and source checksums. Approver can reject with reason or approve. Approval and snapshot publication commit atomically. A failure leaves the previous release available with its original timestamp.
7. Viewer selects one certified release; all tiles, drilldowns, downloads and AI evidence use that release. Restatements create new releases with an explicit comparison and do not mutate older snapshots.
8. Manager downloads a report or requests an AI explanation. AI consumes only allowlisted approved aggregate facts. Missing or incomparable data produces a refusal or limitation, never an invented number.

## Required product modules

| Module | Version-one behavior | Acceptance gate |
|---|---|---|
| Onboarding | Templates, mapping validation, upload status, scenario loading | Invalid types, missing files, size violations and duplicate submissions handled visibly |
| Quality workbench | Rule results, failed-row diagnostics, reconciliation and reruns | Missing feed cannot become zero; defects cannot be approved away |
| Finance workspace | Membership, FFS PMPM/spend/utilization; separate encounters/capitation | SQL/API/browser/export totals agree; weighted ratios and zero denominators tested |
| Variance review | Prior-period bridge, category/market contributions, investigation notes | Components reconcile in cents; incompatible definitions/cohorts cannot compare |
| Anomaly review | Materiality and statistical candidates; preliminary advisory for provisional periods | Quiet-history and minimum-exposure cases tested; no causal/fraud assertions |
| Release center | Submission, rejection, independent approval, immutable snapshots | Unauthorized/self approval blocked; concurrent approvals create one release |
| Reports | CSV and management PDF with filters, release IDs and caveats | Export honors authorization and reproduces screen values |
| Power BI | Read-only certified dataset and documented model/measures | Same filters produce same totals; failed/draft runs absent from certified dataset |
| AI assistant | Cited KPI/variance explanations, budgets, abstention, feedback | Wrong-release, unsupported-value and prompt-injection evaluation cases pass |
| CMS explorer | Search/filter source documents, unknown coverage and lineage caveats | No cross-track financial joins; no projection described as actual spending |
| Administration | Role/market access, configuration versions and audit review | Permission tests cover direct API requests and downloads, not just hidden UI |
| Operations | Job retries, structured logs, health checks, backups and restore | Worker restart and database restoration verified in documented drills |

## Finance semantics

The existing four design documents remain authoritative for KPI definitions. FFS observed service-month payments, managed-care encounters and coverage-month capitation are separate measures. No profitability, MLR, reserves, risk adjustment or causal medical-cost conclusions are implied.

Variance uses the documented ordering: membership effect = (MM_current − MM_prior) × PMPM_prior; PMPM effect = MM_current × (PMPM_current − PMPM_prior). Preserve precise components and make rounding/reconciliation explicit. Zero denominators and mismatched definitions yield unavailable comparisons.

Statistical flags use the preceding 12 certified consecutive comparable months, score threshold and at least $10,000 estimated impact, with MM at least 100. MAD=0 or inadequate history is not evaluated. Provisional months get preliminary movement advisories, no statistical anomaly count. These are configurable portfolio assumptions, not CMS standards.

## Release safety

Certification requires complete expected quality-rule coverage, expected input partitions, no failed/unevaluated mandatory rules, resolved warnings, reconciled financial components, recorded versions and a valid independent approver. A READY_FOR_REVIEW string alone is insufficient. The first code increment implements read-only preflight of existing rule evidence; it is not certification or authentication.

The full release snapshot records source hashes, rule outcomes, mapping/KPI versions, reporting period, cutoff, provisional/comparison-ready status, submitter/approver identities, approval reason/time and a snapshot checksum. Report reads come from immutable snapshot tables rather than live draft views. Database privileges limit direct mutation; application audit rows alone are not protection against an administrator with database access.

## AI boundary

Use a provider interface with explicit credentials and an on-screen unavailable state when no provider is configured. An offline evidence viewer remains functional without AI. Do not simulate model answers and label them AI.

The backend selects authorized certified facts and calculates all values before the model call. Validate output citations and referenced values; reject unsupported claims. Record release/evidence IDs, prompt/model versions, latency, token/cost estimates and human feedback. Redact credentials and sensitive input from logs. AI cannot execute arbitrary SQL, change data, approve a release or send external communications.

## Delivery and operations

Local start: documented Docker Compose command, health checks, migrations and synthetic seed action. No committed secrets or default production credentials. Azure follows only after local acceptance: container hosting, managed PostgreSQL, Blob storage, Entra ID, Key Vault and centralized logs, provisioned through versioned infrastructure code. Hosting service/SKU choices require a budget and current platform verification before deployment.

Power BI Desktop/model publishing and hosted sharing have external installation/account/licensing dependencies; they are explicit integration requirements, not part of the web app's startup. No claim of completed Power BI integration until a real model/report is tested.

Initial performance acceptance workload: 100,000 synthetic claim lines, 24 months, three markets. Proposed gates to measure (not achieved claims): ordinary dashboard requests p95 under two seconds with five concurrent users on a documented four-vCPU/eight-GB environment; jobs stay asynchronous; upload/processing time and memory recorded. Increase workload only after baseline measurements.

Backup acceptance: restore a database plus corresponding file snapshot into an isolated environment and verify release hashes/report totals. Document measured recovery time; do not claim an SLA before measurement. Include dependency/security scanning, error-state tests, keyboard navigation, accessible labels and browser end-to-end tests.

## Definition of version-one completion

A fresh reviewer can follow setup, sign in as each role, run clean and bad-data scenarios, correct and rerun, review reconciled variances, submit/approve a release, export consistent reports, and get cited AI answers with a configured provider. Authorization, stale/failed refresh, worker recovery, backup restoration and upgrade checks pass. Power BI consumes the same certified data. Azure deployment is separately verified. User documentation and a walkthrough accompany a tagged release; known limits remain visible.

Real-data deployment, multi-tenant SaaS, billing, arbitrary source connectors, actuarial forecasting, Spark/Fabric processing and clinical/fraud decisions are outside this version. These exclusions give version one a finish line; they do not remove the full application, operational and integration requirements above.
