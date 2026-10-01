# Medicaid state directed payments, as data

Medicaid state directed payments move roughly **$137 billion a year**, about $93 billion of it federal. CMS publishes the approving documents for all of it.

It publishes them as **1,158 individual PDFs**. No bulk download, no CSV, no API.

So the money is technically public and practically unreadable. This repository turns those documents into a dataset, and reports what they do and do not contain.

**[→ The dataset](data/published/sdp_arrangements.csv)** · [Parquet](data/published/sdp_arrangements.parquet) · [schema and limits](docs/sdp_dataset.md) · [changelog](data/published/CHANGELOG.md)

---

## The finding

Nearly a third of what CMS publishes carries no readable amount, and the money is rarely where the form asks for it.

| | Documents |
|---|---|
| Published by CMS | 1,157 |
| Carrying a usable amount | 823 (71%) |
| **Carrying none** | **334 (29%)** |

The shape of the source explains the gap. Only 298 of the documents are approval letters; 615 are the preprint form published alone with no letter attached, and 235 are preliminary determinations under the 2025 phase-down law, which state a statutory ceiling rather than an approval.

**Of the 298 approval letters, 118 state no figure at all.** They read "incorporated in the capitation rates through a risk based rate adjustment" and stop. Most of those arrangements are recoverable because the amount sits in the form field instead, which is why reading both sources matters; 13 are not recoverable from either.

For the 2024 rating period, the most complete year, the dataset holds **246 arrangements totalling $98.8 billion**.

Two things fall out of the extraction that are worth more than the totals.

**$146.4 billion sits under grandfathering caps.** 211 documents are preliminary determinations under Public Law 119-21, stating the ceiling an existing arrangement may not exceed before the section 71116 phase down begins. CMS projects the new limits will cut $510 billion in federal spending between 2026 and 2035. These caps are published here in their own column and are never summed beside approved amounts.

**The states with the most money have the weakest reporting record.** From September 2026, CMS requires states to report actual directed payment amounts in T-MSIS. Of the ten states moving the most directed payment money, **two** were reporting supplemental payments usably at the last public assessment. Texas at $49.9 billion is `Unclassified`. New York is `Unusable`. Illinois is `High concern`.

That last point is a proxy and the repository says so everywhere it appears: it measures *supplemental* payment reporting, in *2020*. No public measure of directed payment reporting exists, because the requirement has only just taken effect.

## What this cannot tell you

Leading with the limits, because a dataset that hides them is worse than no dataset.

- **These are projections, not spending.** A preprint records what a state expected at approval. MACPAC records that preprints are never resubmitted to reconcile against what was actually paid.
- **Actual amounts are out of reach.** They land in T-MSIS/TAF, which needs a ResDAC data use agreement. This project describes that gap and cannot close it.
- **Do not sum the file.** Rows span 2020 to 2027 and include amendments that restate full-year totals. Filter to one rating period year first. [The BI extract](data/published/sdp_tableau_extract.csv) does that resolution for you.
- **Not a complete census.** Arrangements paying exact fee-for-service rates need no preprint, so they never appear in the source.
- **Coverage is 71%.** The missing 29% is mostly CMS not stating an amount, not extraction failing.

## How the numbers were got

The amounts are not where the form asks for them. Question 4 of the preprint requests the total dollar amount and appears in every document, but the state's answer never reaches the extracted text layer. It is in the PDF's fillable form fields, and where those are empty, in the prose of CMS's approval letter.

Reading both gives two independent figures for the same arrangement. **They agree exactly on 194 of 214 rows, 90.7%.** The disagreements are not noise: combined `FEE.VBP` arrangements disagree on 10 of 15 while pure `FEE` agrees on 169 of 174, because the letter tends to state one component where the form states the combined total. Neither reading is wrong and the schema says so rather than picking one.

CMS's own data is inconsistent in ways the parser records rather than hides. Identifiers arrive hyphen separated, lower cased, with stray whitespace, with dates written `MMDDYYYY`, with a leading backslash. 60 of 1,157 needed a documented repair. **Eight could not be parsed at all and every one is a typo in CMS's published data**, six of them nine-digit dates. Those keep the fields that were readable and state why the rest are missing, because an identifier quietly guessed at is worse than one openly unknown.

Amounts are written `$310.4 million`, `$59.12M`, `$227.9 M`, `Approximately $3,093.1 million`, `$388,500,819 including the impact of...`. All parse to integer cents. One reads `$9,085,139 million`, which taken literally is ten times total annual US Medicaid spending; it is flagged as implausible and left unresolved rather than divided by a thousand to look sensible.

## Reproducing it

```bash
python -m src.sdp.fetch_preprints manifest   # 13 requests to the CMS listing
python -m src.sdp.fetch_preprints download   # ~1,150 PDFs, resumable, rate limited
python -m src.sdp.extract                    # read the amounts
python -m src.sdp.publish                    # CSV and Parquet
python -m src.sdp.readiness                  # the reporting view
python -m src.sdp.tableau_export             # BI extract
python -m pytest tests -q                    # 160 tests
```

The fetch honours `robots.txt`, including its one second crawl delay and its `Disallow: /media/*`, which costs 7 of 1,157 documents. Those keep their listing metadata and are reported as excluded rather than dropped.

## The other half of this repository

A **synthetic Medicaid finance warehouse** shares the repo and shares no data with the above. A fabricated dataset, SQL schema, claim and eligibility resolution, quality gates and KPI views, built to work through the definitions a finance team argues about without touching anyone's health information. Start at [business requirements](docs/business_requirements.md), then the [KPI dictionary](docs/kpi_dictionary.md), [data dictionary](docs/data_dictionary.md) and [architecture](docs/architecture.md).

Neither track uses protected health information, beneficiary records, or any file obtained under a data use agreement. The boundary is written down in [AGENTS.md](AGENTS.md#the-data-boundary) and every source is listed in [real data sources](docs/real_data_sources.md).

## Layout

```text
src/sdp/          fetch, parse, extract, publish, readiness, BI export
src/              generator, resolution, quality, KPI layer (synthetic track)
sql/              schema, transformations, quality rules, KPI views
data/published/   the dataset, the extract, the readiness view, changelog
docs/             dataset schema, dashboard spec, data sources, handoff
tests/            160 tests
```

Raw PDFs and intermediate output are not committed. The published dataset is, because an open dataset nobody can download is not open.

## Not

Legal, actuarial or financial advice. Not a CMS submission, not a statement of what CMS requires, not a reproduction of any official file. Every figure is traceable to a source URL and a content hash so it can be checked rather than believed.
