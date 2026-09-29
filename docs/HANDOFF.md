# Project handoff

Last updated: 2026-09-29

## User objective and authorized scope

Build a Medicaid Finance Intelligence & Reporting Automation portfolio project that supports learning while building. The latest implementation authorization was limited to Phase 1: create the directory structure and write business requirements, KPI dictionary, data dictionary, and architecture. Design for cross-market finance reporting, quality controls, variance/anomaly review, Power BI, and a later AI layer that explains only validated outputs.

## Completed

- README.md: entry point, structure, scope.
- business_requirements.md: stakeholders, requirements, acceptance criteria, exclusions, quality responsibilities.
- kpi_dictionary.md: populations, formulas, aggregation rules, time bases, variance bridge, proposed review thresholds, future test examples.
- data_dictionary.md: CMS reference links, logical entities, keys, grains, field rules, claim lifecycle, lineage and release entities.
- architecture.md: proposed local-first flow, publication gates, reporting contracts, future AI boundary.
- AGENTS.md: instructions for subsequent agents.
- Reserved directories with .gitkeep files and a .gitignore for secrets/runtime artifacts/generated data.

Revised after review on 2026-09-29:

- kpi_dictionary.md: the statistical anomaly candidate now requires a score above threshold **and** a financial impact of at least $10,000, measured as |current PMPM − historical median PMPM| × current member months. A score alone was insufficient because the score is expressed in units of historical dispersion, so a quiet history makes a financially trivial move look extreme.
- kpi_dictionary.md: statistical detection is restricted to comparison-ready months. Provisional months receive a separately labeled preliminary movement advisory instead, carrying the cutoff and provisional status, producing no score and entering no anomaly count. Recorded explicitly: passing data-quality checks does not mean claims are fully developed.
- kpi_dictionary.md: acceptance examples 8, 9 and 10 cover a quiet history below materiality, a quiet history above it, and a provisional period.
- README.md: the structure tree previously omitted AGENTS.md and docs/HANDOFF.md, both of which exist and both of which the README directs a continuing agent to read first.

Read the four design documents in the order above. They are the project specification; no prior chat access is needed to understand the current design.

## Phase 2a, first implementation (2026-09-29)

Schema and fixture, authorized separately from Phase 1 documentation.

- `sql/schema/` applies in numeric order: operational entities, raw landing tables, dimensions, exposure, claims, financial ledgers. `sql/schema/README.md` records the engine decision and the one storage departure from the data dictionary.
- **SQLite is the development engine, PostgreSQL remains the deployment target.** No Postgres is installed on the development machine and the fixture must run for any reviewer without setup. The DDL stays inside the intersection of both engines where that costs nothing.
- **Money is stored as signed integer cents**, not `DECIMAL(18,2)`. SQLite has no decimal type and would store a float, which cannot represent most cent values exactly. This project blocks a release on cent-level disagreement, so an approximate representation would undermine the control it exists to test. This is a storage decision; no KPI definition changes.
- `src/data_generation/fixture.py` holds the fixture as hand-written rows with no randomness. `CASE_COVERAGE` maps each of the ten cases named in architecture.md to the row that represents it, so a test can assert the fixture has not lost one.
- `src/data_generation/build_fixture.py` creates the database, applies the schema and loads reference data plus the raw landing tables. The database is a derived artifact under `data/processed/` and is not committed.
- Raw tables accept defects deliberately. A fixture unable to express a duplicate or an orphan cannot demonstrate that a rule catches one. `expected_defect` declares the three planted defects so a later test can assert each was caught; the pipeline never reads it.
- An eleventh case beyond the architecture's ten was added: a line carrying `SVC_UNMAPPED_99`, absent from the category map, because unmapped lines are documented as blocking a release and a map with no gap cannot demonstrate that.

## Phase 2b, resolution and quality rules (2026-09-29)

- `sql/transformations/` in five ordered files: eligibility spans deduplicated on the business key, member months built from a union of covered days, claim versions loaded with replacement chains resolved, finals selected, signed ledgers loaded.
- `sql/quality/` in three files: structural, population and financial rules, each writing a `dq_result` row per evaluated partition.
- `src/validation/run_pipeline.py` applies both in order and sets the run status. It never certifies; a release manifest and finance approval are a later task.
- The fixture run ends `FAILED`, which is the controls working. Exactly the three declared defects fail and nothing else.

**A rule was wrong and has been corrected.** `DQ_MISSING_MARKET_FEED` originally inferred that a feed had arrived from the presence of claim rows. That made a market with a genuinely quiet month indistinguishable from a market whose feed failed, and it flagged market B's February as missing when market B simply had no February claims. The rule now establishes arrival from `source_file`, which gained `market_id` and `month_start` for the purpose. The fixture demonstrates both sides: market B sends an empty February file that must pass, market C sends none and must block. `NON_DEFECT_CONTROLS` records the empty file as a deliberate non-defect, because a rule could otherwise satisfy the missing-feed case by failing every empty partition.

`expected_partition` now covers claims only. Eligibility arrives as spans that cross months, so a market-month expectation does not describe how it is delivered; its absence is a missing file rather than a missing partition.

## Phase 2c, the KPI layer (2026-09-29)

`sql/kpis/` in three files, created as views on every run so a definition change cannot leave a stale materialised copy claiming to be current.

- `100_components.sql` aggregates exposure and claims to the reporting grain separately, before anything joins them. Joining claim lines to member months and then summing membership repeats a member once per line, which inflates a denominator plausibly and reconciles to nothing.
- `200_kpi_month.sql` assembles K01, K02, K04 to K08 at month by market for the FFS primary cohort, K10 and K11 for managed care in a separate view, and K03 over the period.
- `300_kpi_category.sql` gives K09 and the category contribution to PMPM.

Every ratio is computed from summed components, none is stored, and none is an average of other ratios. Every ratio returns NULL on a zero denominator rather than zero or infinity. Numerator and denominator sit beside every rate so a reader can reproduce the arithmetic and a dashboard cannot show a rate whose components it never received.

**A gap was found and closed while building this.** The KPI views initially reported market C's February FFS spend as $0.00, because a market that spent nothing and a market whose feed never arrived both produce no claim rows. The release gate blocked publication, but a consumer reading the view directly would have published that zero. `v_partition_status` now travels with every measure, carrying `AVAILABLE`, `UNAVAILABLE_PARTITION` or `UNAVAILABLE_RUN`. A blocking failure scoped to the whole run makes every partition unavailable, because a defect nobody has localised could be anywhere.

**A known interaction, currently harmless.** A claim whose lines did not all map contributes to K06 (it is an accepted claim) but not to K04 (its dollars come from lines). K08 is therefore understated for that market-month. The release is blocked by `DQ_LINE_UNMAPPED_SERVICE_CODE` whenever this happens, so no published figure is affected, but the two measures disagree in the unpublished view and a future reader should not be surprised by it.

## What does not exist

No synthetic data, executable generator, SQL schema, pipeline, automated tests, Power BI file, anomaly implementation, AI integration, cloud infrastructure, or deployment. The project is initialized on branch `main` with a private GitHub repository at https://github.com/Himansh97/medicaid-finance-intelligence and remote `origin`. The user authorized repository creation and pushing this foundation. Verify synchronization using `git status` and the remote branch before continuing.

## Design choices to preserve or explicitly revise

These are proposed portfolio defaults, not separately approved production requirements:

- Fully synthetic data, three fictional markets, 24 service months; PostgreSQL proposed but not installed.
- Primary dollars are observed FFS Medicaid payments. Capitation is separate; encounter dollars do not enter spend.
- Full-benefit Medicaid primary cohort; any-day eligibility contributes one member month. One primary market/plan/delivery-system assignment per member-month; conflicts block publication.
- Service-end month is the default analytical time basis. Payment-month ledger is separate. Synthetic adjudication and payment dates coincide to simplify reconciliation.
- Resolve claim versions before counting or summing. Keep membership independent of claims so members without claims remain in denominators.
- Mandatory failures block affected releases and dependent cross-market totals. Provisional periods, versions, and as-of cutoffs remain visible.
- AI, if later authorized, receives certified aggregates and evidence only.
- A statistical anomaly candidate requires both a score above threshold and at least $10,000 of estimated financial impact against the same median. Both figures are proposed portfolio settings to be tested against generated histories, not Medicaid standards, and the $10,000 deliberately matches the deterministic materiality flag so the two can be tuned together.
- Statistical detection covers comparison-ready months only. Provisional months get a labeled preliminary movement advisory that never carries a score and never appears in the same visual component as a comparison-ready flag.

## Verification actually performed

Confirmed exactly four original requested design documents, checked local Markdown links and paired code fences, scanned for TODO/TBD placeholders, and verified no Python or SQL implementation files exist inside the project. These were documentation checks, not executable KPI tests or CMS compliance validation. Handoff additions were checked separately for local links.

Added during the 2026-09-29 review:

- Recomputed the spend variance bridge. Membership effect plus PMPM effect equals the spend change identically, and the documented example reconciles at $20,000 + $11,000 = $31,000, PMPM +5%, spend +15.5%.
- Recomputed acceptance example 2. Combined PMPM is $250; averaging the two market PMPMs gives the $200 the example warns against.
- Recomputed acceptance examples 8 and 9 against the stated history. A first draft of example 8 was wrong: its history had median $200.05 rather than $200.00, so the candidate scored 2.8 and failed both conditions instead of demonstrating a passing score with failing materiality. The example was corrected to an alternating $199.95/$200.05 history, giving median $200.00 and MAD $0.05, under which $200.40 scores 5.4 with $400 impact and $215.00 scores 202.3 with $15,000 impact.
- Resolved all four CMS links (HTTP 200) and all internal Markdown links.
- Confirmed every file in the repository now appears in the README structure tree.

These remain documentation and arithmetic checks. No KPI has been executed against a database, and the anomaly thresholds have not been tested against generated data.

Added for the schema and fixture:

- `python -m src.data_generation.build_fixture` builds the database from an empty file, applying six schema files and loading 138 rows across 16 tables.
- `python -m pytest tests -q` passes 26 tests. The same file also runs under `python tests/test_fixture_and_schema.py`.
- Most of those tests write a forbidden row and assert the database refuses it: foreign-key enforcement, an accepted FFS claim with no paid amount, a negative terminal balance, unordered service dates, an unreferenced reversal, a positive reversal, unlinked negative capitation, a member month weighted other than 1, CHIP inside the primary cohort, two assignments for one member in one month, out-of-range eligible days, and a repeated claim version.
- The refusal tests were mutation-checked: weakening the member-month weight constraint fails exactly the test covering it, and restoring it returns the suite to green. A constraint nobody has tried to violate is a comment.
- Two errors were found and fixed during this work. Column definitions had been placed after table-level `CHECK` clauses in four tables, which is not valid SQL. Column counts in the loader were hardcoded and one was wrong; the loader now derives them from `PRAGMA table_info` so that failure cannot recur.

Added for resolution and quality rules:

- `python -m src.validation.run_pipeline` applies five transformations and three quality files, producing 7 spans, 11 member months, 9 claim versions, 5 final claims, 8 payment and 4 capitation rows, and 14 rule results.
- `python -m pytest tests -q` passes 51 tests across both files.
- Resolution figures were read back and checked by hand: the replacement family resolves to $120 once rather than $220 or twice; the voided and denied families are absent from the finals while their versions remain for the ledger to reference; the ledger equals the final balance for every family including the voided one at zero; capitation lands at the corrected $475 attributed to coverage month rather than payment month; primary-cohort member months are 7 FFS and 2 managed care, with the CHIP member excluded.
- Two mutation checks were run rather than assumed. Removing the constraint that an accepted FFS claim must state a paid amount fails exactly the test covering it. Reverting `DQ_MISSING_MARKET_FEED` to infer arrival from row counts fails exactly the two tests guarding the zero-versus-unavailable distinction.
- Test pollution was found and fixed: one test deleted `dq_result` and re-ran the pipeline against the shared database, corrupting every test ordered after it. It now builds its own database.
- Three schema-refusal tests were found to be passing for the wrong reason. They referenced a source file that no longer existed, so a foreign key failed before the constraint under test. They now look up a real file id.

Added for the KPI layer:

- `python -m pytest tests -q` passes 67 tests across three files.
- Acceptance examples 1, 2, 4, 5 and 7 are now executable tests rather than prose. Example 1 checks PMPM divides by covered exposure and not by claimants, with one claimant among three covered members. Example 2 checks that combining markets sums components, and asserts the averaged answer differs so the test cannot pass by coincidence. Example 4 checks a two-line claim is one claim and the sum of its lines while appearing under both categories. Example 5 checks capitation and encounters stay out of FFS spend. Example 7 checks a failed feed reads as unavailable rather than zero.
- Figures were read back and checked: category shares reconcile to exactly 100% in every market-month, and category contributions sum to the market-month PMPM to six decimal places. January market A is $23.33 outpatient plus $16.67 professional against a $40.00 PMPM.
- K03 returns NULL for market B FFS, which has exposure in one month of two. Dividing by the months that happened to appear would report an average the period does not support.
- Two mutation checks. Returning 0 instead of NULL for a zero denominator fails exactly the test covering it. Taking spend from claim headers rather than lines fails both category reconciliation tests, which is the intended tripwire for that error.

Still unverified: no mart, variance calculation, release manifest or export has been executed. The anomaly thresholds remain untested against generated data.

## Next steps

1. Clone the private repository using an authorized GitHub account, or use this checkout. Read AGENTS.md and this handoff, then inspect branch status and the latest commit.
2. Schema, fixture, resolution, quality rules and the KPI layer are done. The next unit is the spend variance bridge: K13 month over month, with the membership and PMPM effects that reconcile to the spend change, and market and category contributions at disjoint grains. The worked example in kpi_dictionary.md and the ordering note about the interaction term are the specification. Keep the statistical anomaly rule out of it until there is a longer generated history to tune the two thresholds against.
3. Turn the acceptance examples into meaningful tests, including replacements, voids, members without claims, zero denominators, overlapping eligibility, and missing market feeds.
4. Keep Power BI, statistical anomaly routines, automation, and AI outside that task unless explicitly included.
5. When the anomaly rule is eventually implemented, test it against deliberately quiet histories, meaningful shifts, and incomplete periods before any alert reaches a dashboard. Acceptance examples 8, 9 and 10 exist for exactly those three cases. Tuning the two thresholds is part of that work, not a prerequisite to it.

## Outstanding context

The user's workspace instructions referenced RTK.md, but it was absent from the project and checked parent directories. No content from that missing file has been assumed. CMS source links are recorded in data_dictionary.md; the schema is a conceptual portfolio adaptation, not an official TAF file specification.
