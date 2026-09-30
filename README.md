# Medicaid Finance Intelligence & Reporting Automation

Two tracks that share a repository and never share data.

**The finance track** is a synthetic Medicaid finance warehouse: a fabricated dataset, a SQL schema, claim and eligibility resolution, quality gates and KPI views. Every record in it is invented. It exists to work through the definitions a finance team actually argues about, without touching anyone's health information.

**The state directed payments track** is an open dataset built from real public CMS documents. CMS publishes 1,158 approved state directed payment preprints as individual PDFs with no bulk download, no CSV and no API, which makes roughly $137 billion a year of Medicaid spending technically public and practically unreadable. This track extracts them into something queryable and says plainly what the figures can and cannot support.

Neither track uses protected health information, beneficiary records, or any file obtained under a data use agreement. See [the data boundary](AGENTS.md#the-data-boundary) and [real data sources](docs/real_data_sources.md).

Start with [business requirements](docs/business_requirements.md), then the [KPI dictionary](docs/kpi_dictionary.md), [data dictionary](docs/data_dictionary.md), and [architecture](docs/architecture.md).

The design uses CMS T-MSIS/TAF concepts without copying restricted beneficiary data or claiming to reproduce the official files. All future sample records will be generated from scratch. This is not a CVS system, CMS reporting submission, actuarial model, or production financial statement.

For another LLM or developer continuing this project, read [the handoff](docs/HANDOFF.md) and [agent instructions](AGENTS.md) first.

Repository: [Himansh97/medicaid-finance-intelligence](https://github.com/Himansh97/medicaid-finance-intelligence) (private; authorized GitHub access required).

## Structure

```text
medicaid-finance-intelligence/
├── README.md
├── AGENTS.md
├── docs/
│   ├── business_requirements.md
│   ├── kpi_dictionary.md
│   ├── data_dictionary.md
│   ├── architecture.md
│   └── HANDOFF.md
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
