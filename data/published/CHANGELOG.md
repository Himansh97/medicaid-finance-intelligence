# Changelog

All notable changes to the published dataset. Dates are the retrieval date of
the underlying CMS documents, not the date the code changed.

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
