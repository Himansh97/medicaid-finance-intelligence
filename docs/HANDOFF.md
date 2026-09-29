# Project handoff

Last updated: 2026-09-29

## User objective and authorized scope

Build a Medicaid Finance Intelligence & Reporting Automation portfolio project that supports learning while building. The latest implementation authorization was limited to Phase 1: create the directory structure and write business requirements, KPI dictionary, data dictionary, and architecture. Design for cross-market finance reporting, quality controls, variance/anomaly review, Power BI, and a later AI layer that explains only validated outputs.

## Completed

- README.md: entry point, structure, scope.
- business_requirements.md: stakeholders, requirements, acceptance criteria, exclusions, quality responsibilities.
- kpi_dictionary.md: populations, formulas, aggregation rules, time bases, variance bridge, proposed review thresholds, future test examples.
- data_dictionary.md: CMS reference links, logical entities, keys, grains, field rules, claim lifecycle, lineage and release entities.
- architecture.md: proposed local-first flow, publication gates, reporting contracts, future AI boundary.
- AGENTS.md: instructions for subsequent agents.
- Reserved directories with .gitkeep files and a .gitignore for secrets/runtime artifacts/generated data.

Read the four design documents in the order above. They are the project specification; no prior chat access is needed to understand the current design.

## What does not exist

No synthetic data, executable generator, SQL schema, pipeline, automated tests, Power BI file, anomaly implementation, AI integration, cloud infrastructure, or deployment. The project is initialized on branch `main` with a private GitHub repository at https://github.com/Himansh97/medicaid-finance-intelligence and remote `origin`. The user authorized repository creation and pushing this foundation. Verify synchronization using `git status` and the remote branch before continuing.

## Design choices to preserve or explicitly revise

These are proposed portfolio defaults, not separately approved production requirements:

- Fully synthetic data, three fictional markets, 24 service months; PostgreSQL proposed but not installed.
- Primary dollars are observed FFS Medicaid payments. Capitation is separate; encounter dollars do not enter spend.
- Full-benefit Medicaid primary cohort; any-day eligibility contributes one member month. One primary market/plan/delivery-system assignment per member-month; conflicts block publication.
- Service-end month is the default analytical time basis. Payment-month ledger is separate. Synthetic adjudication and payment dates coincide to simplify reconciliation.
- Resolve claim versions before counting or summing. Keep membership independent of claims so members without claims remain in denominators.
- Mandatory failures block affected releases and dependent cross-market totals. Provisional periods, versions, and as-of cutoffs remain visible.
- AI, if later authorized, receives certified aggregates and evidence only.

## Verification actually performed

Confirmed exactly four original requested design documents, checked local Markdown links and paired code fences, scanned for TODO/TBD placeholders, and verified no Python or SQL implementation files exist inside the project. These were documentation checks, not executable KPI tests or CMS compliance validation. Handoff additions were checked separately for local links.

## Next steps

1. Clone the private repository using an authorized GitHub account, or use this checkout. Read AGENTS.md and this handoff, then inspect branch status and the latest commit.
2. On a new request to implement, confirm or state the proposed finance conventions and select a small scope: synthetic fixtures, SQL warehouse, and deterministic quality/KPI checks.
3. Turn the acceptance examples into meaningful tests, including replacements, voids, members without claims, zero denominators, overlapping eligibility, and missing market feeds.
4. Keep Power BI, statistical anomaly routines, automation, and AI outside that task unless explicitly included.

## Outstanding context

The user's workspace instructions referenced RTK.md, but it was absent from the project and checked parent directories. No content from that missing file has been assumed. CMS source links are recorded in data_dictionary.md; the schema is a conceptual portfolio adaptation, not an official TAF file specification.
