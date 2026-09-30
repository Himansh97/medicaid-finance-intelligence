# The state directed payments dataset

**Files:** `data/published/sdp_arrangements.csv` and `.parquet`
**Extraction version:** 0.2.0
**Source:** approved state directed payment preprints published by CMS, see [real data sources](real_data_sources.md)

One row per approved preprint CMS lists, 1,157 rows across 43 states.

## Read this before using the numbers

**These are projections, not spending.** A preprint records what a state expected an arrangement to cost when CMS approved it. MACPAC records that preprints are not resubmitted to reconcile against what was actually paid. Nothing in this dataset is an actual expenditure.

**The totals are not annual.** Rows span rating periods from 2020 to 2027 and include new arrangements, renewals and amendments of the same underlying payment. Summing the whole file produces a figure that means very little. Filter to one rating period before summing, and decide deliberately how to treat amendments, which frequently restate a full-year total rather than a delta.

**This is not a complete census of directed payments.** Arrangements paying exact Medicare or Medicaid fee-for-service rates do not require a preprint, so they are absent from the CMS listing and therefore from here.

**About 31% of rows carry no usable amount.** That is mostly a property of the source, not of the extraction. See coverage below.

## Coverage

| | Rows | |
|---|---|---|
| Total | 1,157 | every preprint CMS lists |
| Publishable amount | 823 | 71.1% |
| No usable amount | 334 | 28.9% |

The 334 break down as: documents published with no approval letter and an unmapped form template, amounts whose unit is assumed rather than stated, one implausible figure, and 7 rows whose PDF was not fetched because `robots.txt` disallows the path it is served from.

Filter on `amount_is_publishable` to get the 823.

Coverage by form template is uneven, and not in the way the template names suggest. The `numbered` template yields 802 amounts from its form fields. The `prose` and `minimal` templates yield none from fields, because their fields are present but unfilled: those documents were flattened before publication. Where they carry an approval letter, the letter supplies the amount instead, which is why the two are not the coverage gap they first appear to be. The components behind that flag are all present as separate columns, so a reader who disagrees with the rule can apply their own.

## Columns

### Identity

| Column | Meaning |
|---|---|
| `sdp_identifier` | CMS control name, taken from the PDF filename. The primary key. |
| `state_code`, `state_name` | Two-letter code parsed from the identifier, and the name as listed. |
| `payment_type` | As published. `Fee`, `VBP`, `VBP.Fee`, and inconsistently `FEE`, `vbp`, `Fee.VBP`. |
| `payment_type_normalised` | Upper-cased and sorted, so `Fee.VBP` and `VBP.Fee` group together. **Group on this.** |
| `provider_class` | Provider classes, dot separated for multi-class arrangements: `IPH.OPH.BHI`. |
| `review_type` | As published: `New`, `Renewal`, `Amend`, `Amend2`, `Amend3`, `Amendment`. |
| `review_type_normalised` | The four amendment spellings collapse to `Amendment`. **Group on this.** |
| `rating_period_start`, `rating_period_end` | ISO dates. |
| `identifier_suffix` | Trailing text distinguishing otherwise identical arrangements: a New Jersey county, an Ohio hospital. |
| `description` | The one-line description from the CMS listing. |

### Amounts

Money is in integer cents. `total_amount_usd` is provided for convenience and is derived; use the cents column when the arithmetic has to be exact.

| Column | Meaning |
|---|---|
| `amount_cents`, `amount_usd` | **The figure to use.** Taken from the form field, falling back to the approval letter. |
| `amount_source` | `form_field` or `approval_letter`, so a reader knows which reading produced the row. |
| `grandfathered_cap_cents`, `grandfathered_cap_usd` | For phase-down determinations only: the ceiling a grandfathered arrangement may not exceed under Public Law 119-21. **Never sum this beside `amount_cents`.** 211 rows, $146.4 billion. |
| `total_amount_cents`, `total_amount_usd` | Estimated total from the form field specifically. Question 4 of the preprint. |
| `total_amount_raw` | Exactly what was typed, e.g. `$310.4 million including the impact of...`. |
| `federal_share_cents`, `federal_share_raw` | Question 4a. |
| `nonfederal_share_cents`, `nonfederal_share_raw` | Question 4b. |
| `letter_amount_cents` | The amount read independently from the CMS approval letter, where one exists. |
| `letter_matched_phrase` | Which phrase in the letter carried it. Useful for judging that reading. |

`letter_amount_cents` and `total_amount_cents` come from different parts of the document by different methods. Where both are present they are two independent readings of the same arrangement, and comparing them is a reasonable check on either.

**They agree exactly on 194 of 214 rows, 90.7%.** The disagreements are not random. Combined `FEE.VBP` arrangements disagree on 10 of 15, while pure `FEE` arrangements agree on 169 of 174. The pattern says the approval letter tends to state one component of a combined arrangement while the form states the combined total, with Hawaii the clearest case at ratios between four and thirteen. Neither reading is wrong; they are answering slightly different questions, and a user comparing the two columns should expect this on combined arrangements.

### Quality

| Column | Meaning |
|---|---|
| `amount_is_publishable` | True when the total was read, its unit was stated, and its size is credible. |
| `amount_unit_assumed` | The field had no currency symbol and no scale word. One federal share reads `396.97` beside a total of `$510.73 Million`; it probably means millions, which is not the same as knowing. |
| `amount_implausible` | The figure exceeds any credible arrangement size, which in practice means the field combined a full number with a scale word. Pennsylvania filed `$9,085,139 million`. |
| `amount_issue` | Why, in words. |
| `identifier_mismatch` | The document's own CMS ID field disagrees with its filename. 104 rows. |
| `cms_id_in_document` | What the document calls itself. |
| `identifier_repairs` | Deviations from CMS's naming convention that were repaired, semicolon separated. |
| `identifier_issue` | Why an identifier could not be fully parsed. Eight rows, all CMS typos. |
| `document_type` | `approval`, `phase_down_determination` (Public Law 119-21 grandfathering) or `form_only_no_letter`. |
| `form_template` | `numbered`, `prose` or `minimal`. Only `numbered` is mapped to fields. |

### Provenance

| Column | Meaning |
|---|---|
| `source_url` | The CMS URL the PDF was fetched from. |
| `source_sha256` | Content hash of that PDF, so a reader can confirm they have the same document. |
| `retrieved_at` | When. |
| `excluded_reason` | Set where no PDF was fetched. Currently only the `robots.txt` exclusion. |
| `extraction_version` | Which version of the code produced the row. |

## Known limitations

**The identifier mismatch is unresolved on purpose.** 104 documents describe themselves differently from their filename, sometimes by provider class and sometimes by rating period year. One of the two is wrong and this project cannot tell which, so both are published and neither is preferred.

**Two form templates are unmapped.** The prose template (154 documents) has the answers present under field names that are the question text itself. They are recoverable with more work. The minimal template (111 documents) appears to hold nothing useful.

**Amendments are not netted.** An amendment usually restates a full-year total rather than a change, so summing a renewal and its amendments double counts. No attempt is made to resolve arrangement lineage.

**The 7 robots-excluded rows keep their metadata.** Only the PDF-derived fields are missing. A file placed at its expected local path by hand will be picked up on the next run.

## Reproducing it

```bash
python -m src.sdp.fetch_preprints manifest   # 13 requests
python -m src.sdp.fetch_preprints download   # ~1,150 PDFs, resumable, rate limited
python -m src.sdp.extract                    # read amounts
python -m src.sdp.publish                    # write CSV and Parquet
python -m pytest tests -q
```

The fetch honours `robots.txt` and the 1 second crawl delay it asks for.
