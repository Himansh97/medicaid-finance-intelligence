# Business requirements

**Version:** 0.1 · **Date:** 2026-09-29 · **Status:** proposed portfolio design

## Purpose and audience

Give Medicaid finance analysts and market leaders a consistent monthly view of membership, paid medical spend, cost per member, and service use. Replace inconsistent market spreadsheets with documented definitions, reconciled totals, and traceable explanations. Technical reviewers should be able to identify each measure's source, grain, exclusions, and publication controls.

This delivery contains the repository structure and four design documents only. Requirements below describe the intended MVP; they are not claims of implemented capabilities.

## Perspective and boundaries

The primary financial view is **observed fee-for-service (FFS) Medicaid medical payments** for a synthetic Medicaid population. A separate view shows synthetic state-to-plan capitation. Managed-care encounters describe utilization and are excluded from financial spend in this MVP. This avoids presenting encounter amounts plus capitation as one cost total. The model supports a finance team's cross-market reporting workflow without claiming to reproduce a health plan's general ledger, medical loss ratio, profitability, or complete state expenditures.

Use three fictional markets, two fictional managed-care plans per market, and 24 complete synthetic service months as the future demonstration target. Market means a portfolio reporting region, with a separate state-code attribute for source concepts; fictional results must never be described as actual state performance. Each member has one primary market and delivery system per month. This simplification must be enforced and disclosed; overlapping real-world coverage and carve-outs require a future extension.

Only full-benefit Medicaid coverage contributes to primary denominators. Separate CHIP, dual-program ambiguity, limited benefits, and out-of-scope populations remain explicitly classified and excluded. These are portfolio scope decisions, not universal CMS measure definitions.

## Users and decisions

| User | Decision supported | Required evidence |
|---|---|---|
| Finance analyst | What drove the monthly change? | Spend, member months, PMPM, claim counts, category contributions, and as-of date |
| Market leader | Which market requires investigation? | Like-for-like filters, coverage status, trends, and materiality flags |
| Data steward | Can this release be trusted? | Reconciliation, rejected rows, rule results, and lineage |
| Finance approver | Can the report be published? | Versioned definitions, validation outcome, and unresolved limitations |
| Technical reviewer | Can calculations be reproduced? | Keys, grains, snapshot IDs, transformation versions, and explicit formulas |

## Functional requirements and acceptance evidence

| ID | Intended MVP requirement | Future acceptance evidence |
|---|---|---|
| BR-01 | Standardize market, plan, coverage, dates, and service categories centrally. | The same filtered cohort produces the same measure in SQL and Power BI; missing mappings block affected results. |
| BR-02 | Publish membership, member months, FFS spend/PMPM, claim utilization, and capitation separately. | Every measure follows the [KPI dictionary](kpi_dictionary.md); totals use summed numerators and denominators. |
| BR-03 | Preserve raw synthetic records and resolve claim revisions before aggregation. | Duplicate and replacement fixtures cannot inflate paid amount or utilization. |
| BR-04 | Gate publication on structural, financial, and population checks. | An injected blocking defect yields no new certified release; prior releases remain available with their original timestamps. |
| BR-05 | Explain month-over-month changes with deterministic arithmetic. | Market/category contributions reconcile to total change; volume and PMPM effects reconcile to spend change. |
| BR-06 | Flag potential anomalies for human review. | Flags show baseline, threshold, sample size, and reason; they never claim fraud or causation. |
| BR-07 | Provide Power BI-ready certified outputs. | Pages show release, as-of date, time basis, cohort, numerator/denominator, and data-quality status. |
| BR-08 | Make reruns and restatements auditable. | Identical inputs and versions reproduce results; late records create a new release with a change log. |
| BR-09 | Reserve a governed AI explanation interface for later. | Future AI reads only approved aggregates and validated variance facts, cites their identifiers, and abstains when evidence is missing. |

## Reporting contract

A reporting release is a consistent snapshot, not a collection of independently refreshed visuals. Default monthly reporting uses service month, with paid amounts observed through the displayed cutoff. Recent service periods remain **provisional** because late payments can change them; no completion factors or incurred-but-not-reported estimates are assumed. The payment-month view is separately labeled and must not silently use service-month membership as its denominator.

Cross-market comparison uses the same period, population, delivery system, benefit scope, and definition version. Differences are descriptive, not risk-adjusted efficiency rankings. An unavailable market is missing, not zero. A cross-market total is publishable only when all selected partitions pass validation; partial coverage must be a separately labeled exploratory view outside certified reporting.

Planned Power BI pages: executive monthly summary; market/category variance; FFS cost and utilization; managed-care utilization and capitation on distinct panels; and quality/release history. Certified exported tables accompany the visuals so business users can reproduce arithmetic.

## Quality and operational controls

| Control | Default action | Accountable role |
|---|---|---|
| Duplicate business keys, orphan required references, invalid dates, unresolved claim family | Quarantine; block affected release partition | Data steward |
| Missing expected market-month input, overlapping primary coverage, unclassified payment basis | Block partition and any dependent total | Data steward |
| Currency mismatch, invalid negative final amount, header/line difference greater than $0.01 per claim | Block partition | Data steward and finance analyst |
| Raw-to-curated signed financial bridge differs by more than $0.01 per market/run | Block partition | Finance analyst |
| Zero denominators, short anomaly history, legitimate zero encounter dollars | Show unavailable/not evaluated where appropriate; no fabricated values | Finance analyst |
| Large valid period movement | Review flag; does not itself mean bad data | Market finance lead |
| Failed mandatory controls | No finance override of structural failure; correct and rerun | Finance approver |

Quarantine is diagnostic, not permission to silently discard costs. Publication requires correction of blocking failures. Warnings may be accepted with a reason, owner, and release-linked record. Proposed thresholds are project policy, not CMS DQ Atlas thresholds.

## Privacy, reproducibility, and quality attributes

Generate all records from scratch with a recorded seed and scenario configuration. Do not ingest real claims, TAF Research Identifiable Files, names, addresses, dates of birth, SSNs, actual beneficiary IDs, or real provider identifiers. Use fictional prefixed IDs and broad age bands. De-identification is not a transformation implemented or certified by this project; any future use of externally de-identified data requires a separate provenance/privacy review.

Preserve source checksums, input counts/totals, mapping versions, rule versions, and release metadata. Store currency as fixed precision decimals; display dollars to two decimals while retaining calculation precision. A small local dataset is the initial target; no production SLA, hosting architecture, or performance claim is made.

## Delivery boundaries

**This Phase 1:** structure, definitions, logical model, architecture, assumptions, and acceptance criteria.

**Future, separately scoped work:** synthetic generator; SQL schema and transformations; executable quality checks and KPIs; variance/anomaly routines; Power BI model and reports; report automation; governed AI explanation.

**Excluded:** production PHI, live CMS ingestion, statutory reporting, GL reconciliation claims, actuarial reserves, forecasting, risk adjustment, fraud detection, clinical recommendations, autonomous AI actions, Azure/Fabric/Spark deployment, Docker, and CI/CD implementation.

The [data dictionary](data_dictionary.md) records CMS conceptual grounding and source links; the [architecture](architecture.md) defines publication and trust boundaries. Portfolio assumptions here remain reviewable design choices.
