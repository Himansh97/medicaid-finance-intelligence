# Real data sources

**Status:** active. Applies to the state directed payments track only. The finance track uses no real data of any kind.

Every real source used by this project is listed here with what it is, where it came from, when it was retrieved, and what it cannot support. A source that is not on this list is not in the project.

## What is deliberately excluded

| Excluded | Why |
|---|---|
| T-MSIS and TAF Research Identifiable Files | Beneficiary-level. Require a ResDAC data use agreement. Out of scope by design. |
| Any file obtained under a DUA | Same reason. This project publishes openly, and republishing DUA data would breach the agreement it was obtained under. |
| Protected health information of any kind | Never, on either track. |

This exclusion has a consequence worth stating up front. CMS issued guidance in March 2026 requiring states to report actual state directed payment amounts in T-MSIS (`TOT-SDP-PAID-AMT`, fields CIP339, CLT259, COT253, CRX178) from September 2026. **Those actuals land in restricted TAF, so this project cannot read them.** Everything here is projected spending. The gap between projected and actual is the central open question in Medicaid SDP oversight, and this project can describe it but not close it.

## Sources in use

### 1. Approved state directed payment preprints

- **What:** The application forms in which states document how they direct managed care plans to pay providers, and CMS's approval letters. Aggregate payment arrangements. No beneficiary data.
- **Where:** https://www.medicaid.gov/medicaid/managed-care/guidance/state-directed-payments/approved-state-directed-payment-preprints
- **Scope:** All preprints approved on or after 3 February 2023. 1,158 as of retrieval.
- **Format:** Individual PDFs. No bulk download, no CSV, no API. Text PDFs rather than scans, on a standardised numbered CMS template.
- **Retrieved:** recorded per file, with a SHA-256 content hash, by `src/sdp/fetch_preprints.py`.
- **What it cannot support:** Actual spending. These are states' projections at approval time. MACPAC records that preprints are not resubmitted to reconcile against what was really paid. Arrangements that pay exact Medicare or Medicaid FFS rates do not require a preprint at all, so this is not a complete census of directed payments.

### 2. DQ Atlas topic exports

- **What:** CMS's public assessments of T-MSIS data quality, by state and year. Aggregate only.
- **Where:** https://www.medicaid.gov/dq-atlas/
- **Format:** Downloadable CSV per topic. No data use agreement required.
- **Used for:** Whether states are reporting SDP paid amounts in T-MSIS at all, and at what assessed quality.
- **What it cannot support:** Any dollar figure. DQ Atlas describes the quality of data, not its contents.

## Sources evaluated and not used

**CMS-64 Financial Management Data** (https://data.medicaid.gov). Downloaded and examined. Rejected as a calibration source for now, for reasons worth recording:

- Covers 2016 only. The recent CMS-64 datasets on data.medicaid.gov are narrow policy slices (New Adult Group, FFCRA FMAP, CAA 2023 FMAP), not general service-category expenditure.
- 273 service categories that are CMS-64 form lines, not analytical categories. Mapping them onto six service categories is a judgment call, not a lookup.
- Population rollups such as "Total VIII Group" and "Total Newly Eligible" sit in the same column as service lines, so summing that column double counts.
- Contains no denominators, so it cannot produce a PMPM without joining enrollment on a different time basis.

It remains useful for one thing: MCO, PIHP and PAHP lines were 43.5% of $550.9 billion in 2016 net expenditures, which is a citable order-of-magnitude check on any managed care share this project computes.

## Rules for adding a source

1. Confirm it contains no beneficiary-level data and needs no data use agreement.
2. Add it here before writing code against it, with its limits stated.
3. Record retrieval date and content hash for every file, following the `source_file` pattern in `sql/schema/001_operational.sql`.
4. Write down what it cannot support. That section is not optional, and a source with no stated limits usually means nobody looked for them.
