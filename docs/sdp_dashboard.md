# Building the dashboard

**Data:** `data/published/sdp_tableau_extract.csv`, built by `python -m src.sdp.tableau_export`.

763 rows, one per arrangement per rating period, 43 states. Superseded filings are already removed, so a measure dragged onto a sheet is not double counting an amendment on top of the renewal it amends.

Two exclusions worth knowing about:

**Five rows are missing, worth $1.11 billion.** They carry real amounts, including $650 million for New York, but CMS published their dates malformed, so they cannot be assigned to a rating period year. Since the year filter is what makes this extract safe to sum, a row without one cannot be included. They remain in `sdp_arrangements.csv` with `identifier_issue` explaining why.

**Eight rows are filed as $0** by the state. Those are the published values rather than a parsing failure, so they are kept and flagged with `amount_is_zero`. Exclude them when showing an average, or they will drag it.

Tableau Public runs natively on macOS: `brew install --cask tableau-public`. Power BI Desktop does not, which is why this route exists.

## The one rule that matters

**Always filter to a single `rating_period_year` before showing a dollar total.**

Summing across years produces $275 billion, which is not a number about anything: it adds a 2022 arrangement to its own 2023 renewal. Put `rating_period_year` on the filter shelf first, before building anything else, and show it on every view.

**Use 2024.** It is the most complete year at $98.8 billion across 246 arrangements. 2025 and 2026 look like a collapse and are not one: those rating periods are still being approved, so the data thins toward the present. If you show a trend line, either stop it at 2024 or label the later years as incomplete on the chart itself, not in a footnote.

## Three views, in priority order

### 1. What CMS publishes versus what it states

The finding most people will not have heard. A simple bar or waterfall:

| | Documents |
|---|---|
| Published by CMS | 1,157 |
| Carrying an approved amount | 823 |
| Approval letters with no figure stated | 118 |
| Published with no approval letter at all | 615 |

This needs `sdp_arrangements.csv` rather than the extract, because the extract holds only the rows that do carry an amount. Filter on `amount_is_publishable` and `document_type`.

The title should state the point rather than name the chart: "CMS publishes $137 billion a year in directed payments. Most of the documents do not say how much."

### 2. Directed payment dollars by state

Filled map or ranked bar of `amount_usd`, filtered to `rating_period_year = 2024`, coloured by `dq_assessment`.

That colouring is the whole argument. Texas is the largest bar and its reporting assessment is `Unclassified`. New York is `Unusable`. Illinois is `High concern`. The eye does the work that a table of numbers would not.

Keep `federal_share_usd` as a tooltip: it is the figure most readers will actually want, and it is what KFF's $93 billion headline refers to.

### 3. Who will be able to report, and who has the money

A scatter, `amount_usd` against `dq_assessment`, or a simple two-column table sorted by dollars. The finding: of the ten states with the most directed payment money, **two** were reporting supplemental payments usably in 2020.

This view carries the heaviest caveat and must show it on the sheet:

> Reporting quality is measured for **supplemental** payments in **2020**. Directed payment reporting begins September 2026 and no public measure of it exists yet.

Without that line the view claims something it cannot support.

## Caveats that belong on the dashboard, not in a footnote

Put these where a screenshot would catch them, because a screenshot is how this will travel:

- **Projections, not spending.** Every figure is what a state expected at approval. CMS publishes no actuals.
- **2025 and 2026 are incomplete.** Later rating periods are still being approved.
- **Not a complete census.** Arrangements paying exact fee-for-service rates need no preprint and are absent from the source.
- **Coverage is 71%.** 334 of 1,157 documents carry no usable amount, mostly because CMS never stated one.

## Fields

| Field | Use |
|---|---|
| `rating_period_year` | **Filter on this first.** Always. |
| `amount_is_zero` | The state filed Question 4 as $0. Exclude from averages. |
| `amount_usd` | Total approved, federal and non-federal. |
| `federal_share_usd` | The federal portion. |
| `state_name` | Joins to Tableau's geographic role for maps. |
| `dq_assessment` | 2020 supplemental payment reporting quality. Colour by this. |
| `reports_usably` | Boolean shortcut for `dq_assessment = "Low concern"`. |
| `state_grandfathered_cap_usd` | Public Law 119-21 phase-down exposure. **Never the same measure as `amount_usd`.** |
| `provider_class`, `payment_type` | Breakdowns. Class is dot separated for multi-class arrangements. |
| `identifier_mismatch` | Set where the document contradicts its own filename. Useful as a quality filter, not as a story. |
| `source_url` | Make this a URL action so a mark links to the CMS PDF it came from. Worth doing: it is what makes the dashboard checkable. |

## What not to build

**A total across all years.** Covered above, but it is the most likely mistake and the hardest to spot once it is on a slide.

**Anything summing `state_grandfathered_cap_usd` beside `amount_usd`.** A statutory ceiling and a projected spend are different quantities. Tableau will happily add them.

**A per-capita or per-member figure.** There are no denominators in this dataset. Producing one would mean joining enrollment on a different time basis, which is exactly the kind of plausible-looking number this project exists not to produce.
