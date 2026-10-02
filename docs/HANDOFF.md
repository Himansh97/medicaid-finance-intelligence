# Project handoff

Last updated: 2026-09-30

## User objective and authorized scope

Build a Medicaid Finance Intelligence & Reporting Automation portfolio project that supports learning while building. Phase 1 documentation, the subsequent synthetic pipeline and public SDP track, and the September 30 audit repairs are authorized. The latest request authorizes merging PR #2 and implementing M1; the user selected local Docker first, then Azure. Design for cross-market finance reporting, quality controls, variance/anomaly review, Power BI, and a later AI layer that explains only validated outputs.

## M1 local runtime — 2026-10-01

PR #2 was merged as dc43626. M1 code is on feat/m1-runtime, with usage in [M1_RUNTIME.md](product/M1_RUNTIME.md). The PostgreSQL adapter executes canonical finance SQL natively, compares clean/defective scenarios against SQLite, and shares preflight policy through assess_evidence. Each job uses a private run_UUID schema to isolate fixed fixture keys; this is not a scalable multi-tenant storage claim.

FastAPI exposes loopback-only synthetic job submission/status/results, quality, KPIs and preflight. Alembic creates the durable jobs table. Worker claim leases, fencing tokens, bounded retries and atomic result transactions prevent duplicate/stale publication. No upload/authentication/approval endpoints are implemented. API requests accept only clean/defective built-in scenarios.

Docker Compose runs PostgreSQL 16.15, migration, API and worker. Bootstrap generates a private ignored local password. PostgreSQL has no host port and API binds 127.0.0.1:8000. Interactive API at http://localhost:8000/docs. Local Docker is running; do not stop unrelated containers or delete volumes. Local native PostgreSQL test cluster also runs on 127.0.0.1:55439 under /tmp/medicaid-m1-pg; it contains test-only data.

Verification: full suite with real PostgreSQL: 189 passed, ten optional raw-CMS checks skipped. One upstream Starlette/httpx deprecation warning remains. Individual native parity tests cover all KPI views, complete quality rows, counts, preflight, replay, transaction rollback and BIGINT cents. Job tests cover concurrency/idempotency, expired-token fencing, retries and fresh/repeated migration. Live Docker smoke processed clean (READY_FOR_REVIEW) and defective (FAILED with three blockers) scenarios successfully. Those finance outcomes are distinct from successful job execution.

Final branch review is by the parent agent; the separate final reviewer could not run because of its usage limit. Module agents validated their own implementations. No independent final-review completion is claimed.

Next: review/merge M1 PR, then M2 identity, role/market authorization and supported synthetic uploads. React/reverse proxy and local identity provider move into M2 when their actual flows exist; M1 has an API console, not a placeholder web product. No cloud resources were created. Existing per-job finance schemas are retained rather than upgraded in place; future shared-fact/storage migration and real release certification remain separate work.

## Product foundation — current work

Read [product specification](product/PRODUCT_SPEC.md) and [roadmap](product/ROADMAP.md). They extend the original phase-only delivery scope while preserving finance definitions and the two-track data boundary. M0 has started; no application or Docker stack is claimed complete.

Implemented `src/releases/preflight.py`: read-only SQLite submission-readiness check requiring all eight run-wide rule versions plus one feed check for every expected claims partition. Missing, unexpected, stale, duplicate, failed or unevaluated evidence blocks eligibility. Warnings are not waivable until recorded warning decisions exist. The run must be READY_FOR_REVIEW. This is not authentication, approval, immutable snapshots, or certification; it trusts the existing input manifest and recorded results and cannot prove they were not modified upstream.

Verification: 13 preflight tests; full suite 177 passed, 10 optional source checks skipped. A mutation bypassing blockers caused nine tests to fail; restoring the control returned the suite to green. A Docker executable exists locally, but its daemon status query did not complete and was interrupted; container startup remains unverified.

Independent review found a false block for legitimate OUT_OF_COHORT claims: population rule v2 counted them as failing rows despite PASS. Added a failing regression, changed v3 counts/impact to NO_EXPOSURE or CONFLICTING_EXPOSURE only, and verified excluded claims remain outside KPI numerators. Preflight requires v3; existing databases must be rebuilt/rerun before this new gate accepts them. No other important findings in review.

Next runnable milestone: M1 PostgreSQL parity and Docker/API/worker foundation. Before containers, inspect PostgreSQL compatibility of all schema/transformation SQL and prove the same fixture outcomes. Do not expose approval/upload endpoints before authorization exists. No paid/cloud resources are authorized by the local-first decision alone.

Preflight command after building and running a fixture:

```bash
python -m src.releases.preflight --db data/processed/fixture.db --run-id RUN_FIXTURE_0001
```

Exit 0 means eligible for future submission, 1 means blocked, 2 means an input/database error. The existing intentionally defective fixture should return 1. The clean positive case lives in the tests and repairs source inputs before running the pipeline.

## Historical implementation notes

The following sections record earlier phases and their checks at that time. The current audit repair and next-steps sections below supersede earlier counts and limitations.

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

## Phase 2d, the state directed payments track begins (2026-09-30)

A second track, authorized separately. Real public CMS documents, isolated from the synthetic finance work.

**Boundary.** `AGENTS.md` now carries an explicit two-track data boundary replacing the original synthetic-only rule. What protects people is unchanged and stated more sharply: no PHI, no beneficiary records, no T-MSIS or TAF, nothing under a data use agreement. What changed is that real public policy documents are in scope, in their own layer, and the two kinds of data never share a table, view, file or directory. `docs/real_data_sources.md` records each source and what it cannot support.

**Acquisition.** `src/sdp/fetch_preprints.py` walks the CMS listing and downloads preprints. It stops when a page yields nothing new rather than trusting a page count, rate limits to the 1 second `robots.txt` asks for, hashes content, and never re-fetches an unchanged file.

**Two decisions worth recording.**

`robots.txt` disallows `/media/*`, and 7 of the 1,157 preprints (0.6%) are served from there. The fetcher honours that and does not retrieve them. Those arrangements keep their full listing metadata and lose only PDF-derived fields. A person browsing the site is not a crawler, so a file placed at its expected local path by hand is used and marked `fetch_provenance: manual`, which closes the gap without this code ignoring a published rule.

The site returns 403 to a bare descriptive User-Agent but accepts `curl` and `python-requests` defaults, so the block is on the string's shape rather than on automation. The fetcher sends the conventional identified-crawler form, `Mozilla/5.0 (compatible; medicaid-finance-intelligence/0.1; +<repo>)`, which names the project and offers a contact point. A borrowed browser string would have worked and would have said nothing true.

**Parsing.** `src/sdp/identifier.py` reads the CMS control name. The published convention is `STATE_PAYMENTTYPE_PROVIDERCLASS_REVIEWTYPE_START-END`, and about 95% of identifiers follow it. The parser repairs eight documented deviations and records each repair on the record that received it. **60 of 1,157 identifiers (5.2%) needed at least one repair**, most commonly hyphen separators (46) and a lower-case state code (22).

Where the source is wrong and cannot be resolved, nothing is guessed. **Eight identifiers remain unparsed, and all eight are errors in CMS's published data**: six carry a 9-digit date such as `202221001`, one a 7-digit date, and two have no rating period at all. Each keeps the fields that were readable and states why the rest are missing.

## Phase 2e, amount extraction (2026-09-30)

`src/sdp/amounts.py` reads the approved dollar amount; `src/sdp/extract.py` runs it over the corpus and reports the result.

**The money is in CMS's approval letter, not the state-completed form.** Question 4 of the preprint asks for the total dollar amount and appears in every document, but the states' answers do not survive into the text layer. The letter, which is the first two or three pages, is the better source regardless: CMS writes it, so the wording is consistent in a way state-typed entries are not.

**Six phrasings carry the amount**, discovered by inspecting the corpus rather than assumed: `separate payment term (of|amount) (up to)`, `payment term for this state directed payment is`, `risk[- ]based (rate) adjustment`, `total (dollar) amount of`, `amount of up to`, `not to exceed`. The connective words vary letter to letter with no apparent pattern.

**Numbers appear in three formats.** Plain digits, and scaled as million or billion. Arizona writes every figure the scaled way, so a digits-only pattern loses that state entirely. Conversion is to integer cents by shifting the decimal rather than multiplying floats, so nine-figure amounts stay exact.

**Selection is by position in the document, not by pattern order.** 82 of 309 letters checked match more than one phrase, because CMS states the amount in the approval bullet and restates it later. The approval bullet comes first, so the earliest match is the approving one. Choosing by the order patterns happen to be declared in this file would be an accident of authorship rather than a fact about the document. Where a second phrase gives a *different* figure, which does occur, both are reported rather than one quietly preferred.

**Three outcomes are counted separately**, and collapsing them would let a drop in extraction quality hide behind CMS's own omissions:

- an amount anchored to a recognised phrase
- CMS stated no amount at all, which is a fact about the source
- unresolved, which is our gap

On the first 390 preprints: 72.8% anchored, 25.6% no amount stated by CMS, **1.5% unresolved**.

That middle category is the interesting one. Some approvals read "incorporated in the capitation rates through a risk based rate adjustment" and stop, with no figure anywhere in the document. CMS approved those arrangements without a stated ceiling. This is the same phenomenon behind KFF's finding that 38 of 139 hospital preprints lacked complete rate data.

## Phase 2f, the form fields (2026-09-30)

`src/sdp/formfields.py`. The state's answers are in the preprint's fillable AcroForm fields, not in the text layer. Reading the page as text finds Question 4's label and never its answer, which is what made the approval letter look like the only source.

The form is the better source on both counts that matter: it covers the 615 documents published with no letter attached, and it carries the federal and non-federal split that no letter states.

**Three form templates are in circulation**: numbered (77%, the current one, with `4-Text`, `4.a-Text`, `0.2-CMS ID`), prose (13%, where field names are the question text), and minimal (10%, effectively empty). Only the numbered template is mapped; the other two are reported as unmapped rather than as empty answers, because a gap in this code and a gap in the source are different things.

**Amounts are free text and the variety is wide**: `$310.4 million`, `$510.73 Million`, `$59.12M`, `$227.9 M`, `Approximately $3,093.1 million`, `$388,500,819  including the impact of...`, `$95,851,058 (including the imp...`. All parse. One federal share reads simply `396.97` beside a total of `$510.73 Million`; it almost certainly means millions, and almost certainly is not good enough, so the unit is flagged as assumed rather than resolved.

**A plausibility ceiling was added.** Pennsylvania filed `$9,085,139 million`, combining a full-precision figure with a scale word. Read literally that is $9 trillion, about ten times total annual US Medicaid spending, and it alone dominated the first aggregate. Whether they meant $9,085,139 or $9.085 billion is not knowable from the field, so it is reported as implausible and left unresolved rather than quietly divided by a thousand to look sensible. The ceiling sits above the largest credible arrangement in the corpus, Texas at about $9.1 billion.

**The identifier cross-check is live, and it finds a lot.** Of 213 documents carrying a CMS ID, **104 (48.8%) disagree with their own filename**. Some differ by provider class, `AZ_Fee_AMC.PC.SP_Renewal_...` filed against a document calling itself `AZ_Fee_AMC_Renewal_...`. Some differ by rating period year. Which is correct is not something this code can decide, so both are recorded.

### Coverage

| Source | Arrangements with an amount |
|---|---|
| Approval letters | 180 |
| **Form fields** | **802** |

Summed across all rating periods, the usable form totals come to **$314.1 billion, of which $180.1 billion is federal share**. That is not an annual figure and must not be compared directly to KFF's $137 billion annual estimate. The state ranking does corroborate: Texas, California, North Carolina, Virginia and Illinois lead in both.

## Phase 2g, publication (2026-09-30)

`src/sdp/publish.py` writes `data/published/sdp_arrangements.csv` and `.parquet`, with [the schema](sdp_dataset.md) and a changelog. **1,157 rows across 43 states, 36 columns, 802 with a publishable amount.**

Every preprint CMS lists gets a row, including the ones with no readable amount, because a file containing only the successful extractions would misstate its own coverage. Every row carries its source URL, the content hash of the PDF it was read from, when that PDF was retrieved, and which extraction version produced it.

**The two independent readings agree on 90.7% of rows** where both exist, 194 of 214. That is form fields against approval-letter prose, two different parts of the document read by two different methods, so the agreement is a real check on both rather than a tautology.

The 20 disagreements are systematic, not noise. Combined `FEE.VBP` arrangements disagree on 10 of 15 while pure `FEE` agrees on 169 of 174. The letter tends to state one component of a combined arrangement while the form states the combined total, Hawaii most clearly at ratios of four to thirteen. Neither reading is wrong; they answer slightly different questions, and the dataset documentation says so.

**Historical total withdrawn.** The earlier $98.8B comparison mixed selection assumptions and must not validate the current dataset. Release 0.6.0 reports the known projected subtotal and its explicit coverage instead.

One rule in AGENTS.md was in conflict and has been amended rather than quietly ignored: generated data stays out of version control, except the published dataset, which is the deliverable and is about a megabyte. Raw PDFs, the manifest and intermediate output remain ignored.

## Audit of the identifier mismatch (2026-09-30)

The 104 identifier mismatches reported in earlier releases were audited on request. **The figure was wrong and is now 56.** The fault was in this project's check, not in CMS's documents.

Of 213 documents carrying a CMS ID field:

| | Rows |
|---|---|
| Agree, once both sides are parsed | 126 |
| CMS ID field holds no identifier at all | 31 |
| Substantively disagree | 56 |

Three defects in the original check, each inflating the count:

1. **Raw string comparison.** `Nv-Fee-Amc-Renewal-20230101-20231231` was counted as disagreeing with `NV_Fee_AMC_Renewal_20230101-20231231`. Same arrangement, different separators and casing. Stray whitespace did the same.
2. **Provider-class spellings treated as different classes.** CMS writes inpatient hospital as both `IPH` and `IP`, outpatient as both `OPH` and `OP`. A dozen Arizona conflicts were only spelling. The canonicalisation preserves the numeric suffix, because `OPH1` and `OPH2` are genuinely different classes.
3. **Fields holding no identifier counted as conflicts.** Hawaii's CMS ID field reads `A`, `B` or `C`; one Florida document holds a date range in prose. Those are unusable fields, not contradictions, and now have their own column.

A fourth defect was introduced by the fix and caught by an existing test: a field listing several identifiers, which happens when one submission supersedes another, was being compared only against the first. Agreement with any of them is agreement.

What the surviving 56 disagree about: 21 on rating period alone, 17 on review type, 10 on provider class, 7 on state and payment type and class together, 2 on payment type. The rating-period and review-type cases look like a state reusing last year's form without updating the field. 50 of the 56 still carry a usable amount, so the disagreement concerns labelling rather than the money.

**The lesson worth keeping:** a quality check that reports a finding needs auditing as carefully as the data it examines. This one manufactured roughly half its own headline, and the number was published twice before anyone looked at it closely.

## What does not exist

This section described Phase 1 and had gone badly out of date, claiming there was no SQL schema, pipeline or test suite long after all three existed. Corrected 2026-09-30.

**Finance track, does not exist:** the spend variance bridge (K13), the statistical anomaly rule, marts, the release manifest and approval flow, any Power BI or Tableau file, AI integration, cloud infrastructure, deployment.

**SDP track, does not exist:** actual paid amounts, which sit in T-MSIS/TAF behind a ResDAC data use agreement and are out of scope by design. No dashboard has been built; `docs/sdp_dashboard.md` specifies one. The prose and minimal form templates remain unmapped, though they are not the coverage gap they appear to be.

**Both tracks:** no MongoDB. It was planned, and the evidence since argues against it: the published dataset is a flat table and PostgreSQL alone would serve. The install is in any case blocked on outdated Command Line Tools on the development machine.

**The repository is public as of 2026-09-30**, with a description that matches what it now contains. The dataset is reachable, which was the point: CMS publishes $137 billion a year as 1,158 individual PDFs and no structured dataset existed. One now does.

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

Added for the SDP track:

- `python -m src.sdp.fetch_preprints manifest` walks 13 listing pages and records **1,157 preprints across 43 states and 168 provider classes**, of which **1,149 (99.3%) parse cleanly**.
- `python -m pytest tests -q` passes **87 tests**, the 67 synthetic ones unchanged, confirming the real-data work did not disturb the finance track.
- The identifier parser is tested against real published strings only. None is invented, and the malformed cases are malformed in CMS's data.
- Four User-Agent strings were tested against the live site to establish that the 403 was about the string's shape and not about automation, before choosing one.
- The `/media/*` share was measured (7 files, 0.6%) before deciding to honour the robots rule, rather than deciding first and measuring after.

Still unverified: not every public amount or inferred version relationship has been manually checked against its source PDF. Source acquisition/extraction was not rerun for the audit repairs. Finance certification, variance/anomaly execution, dashboards and AI remain unimplemented; anomaly thresholds remain untested against generated histories.

## Current audit repair (2026-09-30)

- Shared `src/sdp/resolution.py` resolves numeric amendments before checking amount availability. Latest missing amounts remain null. Version ties/unknown review types are ambiguous. Suffixes remain in family keys. These are explicit filename inferences, not verified legal lineage.
- BI export retains missing amounts, lineage status, candidate identifiers and source provenance. Optional/missing readiness produces null assessments instead of a crash.
- Caps moved to `sdp_state_caps.csv`, one row per state. The measure is an archive document-cap subtotal with unresolved overlap, not unique exposure.
- Readiness requires an explicit CLI start year and shares resolution with BI. Existing 2020 assessments were reused, not refetched. Known/unknown counts travel with projected subtotals.
- Claim finalization now rejects market/plan mismatches as CONFLICTING_EXPOSURE. DQ_CLAIM_POPULATION_MATCH v2 blocks them; existing KPI filters exclude their dollars.
- Pinned direct Python dependencies, offline regression tests and a GitHub Actions workflow added. Raw manifest/PDF tests are optional integration checks. A small hand-authored publication test proves missing extraction rows remain in output without requiring downloaded files.
- Derived release 0.6.0: 1,061 groups, 329 missing/unresolved amounts; 2024 known projected subtotal $92.71B. Prior $98.8B and cross-year state ranking claims withdrawn. Original archive remains unchanged.

Verification: `python -m pytest -q` → 164 passed, 10 skipped (optional local CMS inputs); offline CI command `python -m pytest -m "not integration" -q` → 164 passed, 10 deselected. The synthetic fixture still intentionally fails on its three planted defects; this is expected control behavior, not a test failure.

## Next steps

1. Review and merge the audit repair branch after CI. No dashboard, AI layer or deployment was added.
2. Manually verify arrangement family links and amendment order against source documents, especially ambiguous/renamed families. Filename order alone cannot certify legal supersession.
3. Resolve overlap between cap documents before publishing a unique exposure total. Preserve the distinction between projections, document ceilings and actuals.
4. Finance release certification and manifests are still required before the synthetic KPI views become certified outputs. Then separately scope dashboard work, variance/anomaly logic and AI.

RTK.md remains absent from the checked workspace; no content has been assumed.

Final audit verification: clean tracked-file snapshot also passed 164 tests with 10 optional integration skips; dependency check found no conflicts. Independent review found no critical/important defects and separately passed all 14 audit regressions.

Live recovery check: queued a clean job while the worker was stopped, restarted it, observed one successful attempt, repeated submission with the same key, and reran the migration. Job ID and stored results were unchanged.
