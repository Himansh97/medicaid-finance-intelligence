# Reporting audit fixes

Goal: repair the six findings approved in chat; preserve synthetic/public boundaries and avoid implementing later phases.

Architecture: one shared, conservative identifier-based resolution function feeds both the BI extract and period-scoped readiness totals. Missing or ambiguous latest amounts remain unknown. State cap aggregates live in a separate file with document provenance retained in the archive.

Tasks (execute inline in existing isolated audit checkout):
- [x] Add regression fixtures for numeric amendments, missing latest amounts, suffix-distinguished arrangements and ambiguous versions; watch failures; implement shared resolution and test.
- [x] Separate state caps, repair optional readiness schema, and retain unknowns in BI; test then rebuild exports.
- [x] Scope readiness to explicit rating-period start year, expose partial coverage, refresh existing assessment snapshot without claiming new source retrieval.
- [x] Add cross-market/plan claims cases, enforce population matching and verify blocked publication.
- [x] Make archive publication coverage test run offline with a small hand-authored manifest; mark raw-source integration tests separately; add dependency declarations and CI.
- [x] Regenerate derived public outputs, remove unsupported headlines, update handoff and run the complete suite plus clean-environment checks.

Decisions: filename ordering is an inference, not proof of legal supersession. Ties/unknown review types yield unresolved amounts; no arbitrary alphabetic winner. Suffixes distinguish arrangements. Year means rating-period START year, not calendar-year actual spending. No merge or production deployment is part of this repair.

Verification ledger: nine original defect counterexamples failed before fixes and passed after. Full suite: 164 passed, 10 optional integration skips. Offline suite: 164 passed, 10 deselected. Derived source archive unchanged; existing assessment snapshot reused. Final independent review: no critical/important findings; 14 regression tests independently passed. Two documentation nits corrected. Clean tracked-file snapshot: 164 passed, 10 optional integration skips. Dependency check: no broken requirements.
