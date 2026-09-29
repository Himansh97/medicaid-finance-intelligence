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

Revised after review on 2026-09-29:

- kpi_dictionary.md: the statistical anomaly candidate now requires a score above threshold **and** a financial impact of at least $10,000, measured as |current PMPM − historical median PMPM| × current member months. A score alone was insufficient because the score is expressed in units of historical dispersion, so a quiet history makes a financially trivial move look extreme.
- kpi_dictionary.md: statistical detection is restricted to comparison-ready months. Provisional months receive a separately labeled preliminary movement advisory instead, carrying the cutoff and provisional status, producing no score and entering no anomaly count. Recorded explicitly: passing data-quality checks does not mean claims are fully developed.
- kpi_dictionary.md: acceptance examples 8, 9 and 10 cover a quiet history below materiality, a quiet history above it, and a provisional period.
- README.md: the structure tree previously omitted AGENTS.md and docs/HANDOFF.md, both of which exist and both of which the README directs a continuing agent to read first.

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
- A statistical anomaly candidate requires both a score above threshold and at least $10,000 of estimated financial impact against the same median. Both figures are proposed portfolio settings to be tested against generated histories, not Medicaid standards, and the $10,000 deliberately matches the deterministic materiality flag so the two can be tuned together.
- Statistical detection covers comparison-ready months only. Provisional months get a labeled preliminary movement advisory that never carries a score and never appears in the same visual component as a comparison-ready flag.

## Verification actually performed

Confirmed exactly four original requested design documents, checked local Markdown links and paired code fences, scanned for TODO/TBD placeholders, and verified no Python or SQL implementation files exist inside the project. These were documentation checks, not executable KPI tests or CMS compliance validation. Handoff additions were checked separately for local links.

Added during the 2026-09-29 review:

- Recomputed the spend variance bridge. Membership effect plus PMPM effect equals the spend change identically, and the documented example reconciles at $20,000 + $11,000 = $31,000, PMPM +5%, spend +15.5%.
- Recomputed acceptance example 2. Combined PMPM is $250; averaging the two market PMPMs gives the $200 the example warns against.
- Recomputed acceptance examples 8 and 9 against the stated history. A first draft of example 8 was wrong: its history had median $200.05 rather than $200.00, so the candidate scored 2.8 and failed both conditions instead of demonstrating a passing score with failing materiality. The example was corrected to an alternating $199.95/$200.05 history, giving median $200.00 and MAD $0.05, under which $200.40 scores 5.4 with $400 impact and $215.00 scores 202.3 with $15,000 impact.
- Resolved all four CMS links (HTTP 200) and all internal Markdown links.
- Confirmed every file in the repository now appears in the README structure tree.

These remain documentation and arithmetic checks. No KPI has been executed against a database, and the anomaly thresholds have not been tested against generated data.

## Next steps

1. Clone the private repository using an authorized GitHub account, or use this checkout. Read AGENTS.md and this handoff, then inspect branch status and the latest commit.
2. On a new request to implement, confirm or state the proposed finance conventions and select a small scope: synthetic fixtures, SQL warehouse, and deterministic quality/KPI checks.
3. Turn the acceptance examples into meaningful tests, including replacements, voids, members without claims, zero denominators, overlapping eligibility, and missing market feeds.
4. Keep Power BI, statistical anomaly routines, automation, and AI outside that task unless explicitly included.
5. When the anomaly rule is eventually implemented, test it against deliberately quiet histories, meaningful shifts, and incomplete periods before any alert reaches a dashboard. Acceptance examples 8, 9 and 10 exist for exactly those three cases. Tuning the two thresholds is part of that work, not a prerequisite to it.

## Outstanding context

The user's workspace instructions referenced RTK.md, but it was absent from the project and checked parent directories. No content from that missing file has been assumed. CMS source links are recorded in data_dictionary.md; the schema is a conceptual portfolio adaptation, not an official TAF file specification.
