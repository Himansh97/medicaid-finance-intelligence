# Medicaid Finance Intelligence & Reporting Automation

A synthetic-data portfolio project for a Medicaid finance team. **Current deliverable: Phase 1 documentation and repository structure only.** No data, database, pipeline, dashboard, anomaly detector, or AI implementation exists yet.

Start with [business requirements](docs/business_requirements.md), then the [KPI dictionary](docs/kpi_dictionary.md), [data dictionary](docs/data_dictionary.md), and [architecture](docs/architecture.md).

The design uses CMS T-MSIS/TAF concepts without copying restricted beneficiary data or claiming to reproduce the official files. All future sample records will be generated from scratch. This is not a CVS system, CMS reporting submission, actuarial model, or production financial statement.

For another LLM or developer continuing this project, read [the handoff](docs/HANDOFF.md) and [agent instructions](AGENTS.md) first.

Repository: [Himansh97/medicaid-finance-intelligence](https://github.com/Himansh97/medicaid-finance-intelligence) (private; authorized GitHub access required).

## Structure

```text
medicaid-finance-intelligence/
├── README.md
├── docs/
│   ├── business_requirements.md
│   ├── kpi_dictionary.md
│   ├── data_dictionary.md
│   └── architecture.md
├── data/{raw,synthetic,processed}/
├── sql/{schema,transformations,quality,kpis}/
├── src/{data_generation,validation,analytics,ai}/
├── powerbi/
├── tests/
└── reports/
```

Empty directories contain `.gitkeep` files only. `src/ai` reserves a location; it does not authorize AI development. `data/raw` is reserved for immutable synthetic input snapshots.

## Scope and next decision

Review the proposed finance perspective, denominator rules, claim lifecycle, and publication gates before implementing a generator and SQL warehouse in a separately scoped task. No cloud accounts, paid services, dependencies, or external data access are required to review this foundation.
