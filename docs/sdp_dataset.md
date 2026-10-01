# The state directed payments dataset

**Files:** `data/published/sdp_arrangements.csv` and `.parquet`
**Extraction version:** 0.4.0
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
| `identifier_mismatch` | The document's own CMS ID field **substantively** disagrees with its filename, naming which components differ. 56 rows. |
| `cms_id_unusable` | The CMS ID field holds no identifier at all. Hawaii's reads `A`, `B` or `C`; one Florida document holds a date range in prose. 31 rows. Not a conflict. |
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

**The identifier mismatch is unresolved on purpose.** 56 documents describe themselves substantively differently from their filename. One of the two is wrong and this project cannot tell which, so both are published and neither is preferred.

An earlier release reported 104. That figure was wrong, and the correction is worth stating because it cuts the headline in half. The first version of this check compared the two identifiers as raw strings, which counted `Nv-Fee-Amc-Renewal-20230101-20231231` as disagreeing with `NV_Fee_AMC_Renewal_20230101-20231231`, and counted `IPH.OPH1` as a different provider class from `IP.OP1` when CMS writes inpatient and outpatient hospital both ways. Both sides are now parsed into components before comparison, provider-class spellings are canonicalised while their numeric suffixes are preserved, and a field listing several identifiers counts as agreeing if any of them matches.

What the 56 actually disagree about:

| Component | Rows |
|---|---|
| Rating period only | 21 |
| Review type (with or without period) | 17 |
| Provider class | 10 |
| State, payment type and class together | 7 |
| Payment type only | 2 |

The rating-period and review-type cases look like a state reusing last year's form without updating the field: a document filed as `VA_Fee_Oth_Renewal_20240701-20250630` calls itself `VA_Fee_Oth_Renewal_20220701-20230630`. The seven that differ on state as well are referencing a different arrangement entirely. 50 of the 56 still carry a usable amount, so the disagreement is about labelling rather than about the money.

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


## Companion: reporting readiness

`data/published/sdp_reporting_readiness.json`, built by `python -m src.sdp.readiness`.

CMS requires states to report actual directed payment amounts in T-MSIS (`TOT-SDP-PAID-AMT`) from September 2026. Whether that produces usable data is the open question, and KFF put it this way: "It is unclear how comprehensive those data will be, most states currently do not report other types of supplemental payments in T-MSIS."

This turns that sentence into numbers, from public data only.

**It is a proxy and the file says so in three places.** There is no public measure of SDP reporting, because the requirement has only just taken effect. The nearest public evidence is CMS's own DQ Atlas assessment of **supplemental payment** reporting: a different payment category, but the same question, which is whether a state asked to report a payment amount in T-MSIS actually does.

In the preserved assessment snapshot, **2020**, across 53 states and territories:

| DQ assessment | States |
|---|---|
| Unclassified | 35 |
| Low concern | 10 |
| Unusable | 5 |
| Medium concern | 2 |
| High concern | 1 |

Ten of fifty-three were reporting usably. `Unclassified` generally means there was not enough data to assess, which for a reporting question is the answer rather than the absence of one.

**The SDP join is period-scoped.** `python -m src.sdp.readiness --rating-period-year 2024` uses the same identifier-based resolution as the BI extract and records the selected start year, known subtotal, known arrangement count and unknown arrangement count. In the corrected 2024 ranking, two of the ten largest known projected subtotals have Low concern assessments. These are incomplete projected subtotals, not total payments. Earlier cross-year figures (including Texas $49.9B) were invalid for this comparison and are withdrawn.

Three limits travel with every figure above:

- Supplemental payments are fee-for-service; directed payments are managed care. A state good at one is not necessarily good at the other.
- The assessment snapshot covers 2020. **Nothing here describes 2026.**
- Actual SDP amounts land in T-MSIS/TAF, which needs a ResDAC data use agreement and is out of scope. This project cannot close the gap it is describing.


## Derived reporting release 0.6.0

The document archive and its extraction version remain unchanged. Derived files carry `resolution_version=0.6.0`. See [dashboard contract](sdp_dashboard.md) for missing-amount status, inferred lineage, start-year filtering, and separate state document-cap subtotals. `--reuse-assessments` recalculates the SDP join from the committed assessment snapshot without fetching new source data; it does not refresh the assessment date.
