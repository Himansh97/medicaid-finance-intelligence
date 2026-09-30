# Changelog

All notable changes to the published dataset. Dates are the retrieval date of
the underlying CMS documents, not the date the code changed.

## 0.5.0 (2026-09-30)

- `sdp_tableau_extract.csv` added: 763 rows, one per arrangement per rating
  period, built for BI tools where a measure gets summed without asking.
  Superseded amendments are resolved, a rating period year is present for
  filtering, and the reporting assessment is joined on.
- Five rows are excluded from the extract, worth $1.11bn, because CMS published
  their dates malformed and they cannot be assigned to a year. They remain in
  `sdp_arrangements.csv`.
- Eight rows filed as $0 by the state are kept and flagged `amount_is_zero`.
- No change to `sdp_arrangements`.

## 0.4.0 (2026-09-30)

- **Correction.** `identifier_mismatch` reported 104 rows in 0.3.0 and reports
  56 now. The earlier check compared raw strings, so separator and casing
  differences, stray whitespace, and CMS's two spellings of inpatient and
  outpatient hospital (`IPH`/`IP`, `OPH`/`OP`) were all counted as conflicts.
  Both sides are now parsed into components before comparison, and the message
  names which components differ.
- `cms_id_unusable` added: 31 rows whose CMS ID field holds no identifier at
  all, previously miscounted as conflicts.
- A field listing several identifiers now counts as agreeing if any of them
  matches, which is the case when one submission supersedes another.

## 0.3.0 (2026-09-30)

- `sdp_reporting_readiness.json` added: DQ Atlas supplemental payment reporting
  quality by state, offered explicitly as a proxy for directed payment reporting
  readiness, joined to the arrangements dataset.
- No change to `sdp_arrangements`.

## 0.2.0 (2026-09-30)

- `amount_cents` and `amount_source` added: the figure to use, taken from the
  form field and falling back to the approval letter. Coverage rises from 802 to
  823 rows, because the previous release ignored the letter entirely when the
  form had nothing usable.
- `grandfathered_cap_cents` added. 211 phase-down determinations under Public
  Law 119-21 carry a ceiling the arrangement may not exceed, totalling $146.4
  billion. These are published in their own column and must never be summed
  beside `amount_cents`.
- `amount_unit_assumed` and `amount_implausible` now describe the amount that
  was actually chosen. In 0.1.0 they described the form reading even on rows
  published from the letter, which wrongly flagged 14 clear letter figures as
  having an assumed unit. The form's own caveats moved to `form_unit_assumed`
  and `form_implausible`.

## 0.1.0 (2026-09-30)

First release. 1,157 rows across 43 states, built from approved state directed
payment preprints published by CMS.

- 802 rows (69.3%) carry a publishable total amount.
- Amounts are read from the preprint's fillable form fields, with the CMS
  approval letter as an independent second reading where one exists.
- Rating periods span 2020 to 2027. Summing the file is not an annual figure.
- 104 rows have a document whose own CMS ID disagrees with its filename. Both
  values are published and neither is preferred.
- 7 rows have no PDF: `robots.txt` disallows the path they are served from, so
  they keep their listing metadata and lose only PDF-derived fields.
- 8 identifiers could not be fully parsed. All eight are typos in CMS's
  published data, six of them 9-digit dates.
- Two form templates are unmapped: prose (154 documents) and minimal (111).

Known limitation: amendments are not netted against the arrangements they
amend, so summing a renewal and its amendments double counts.
