# Instructions for continuing agents

Read README.md and docs/HANDOFF.md first, followed by all four design documents linked there.

## Scope

The project has two tracks, and they do not mix.

**The finance track** is a synthetic Medicaid finance warehouse: generator, schema, resolution, quality rules and KPI views. Its data is fabricated from scratch and always will be.

**The state directed payments track** is an open dataset built from real public CMS documents. It was authorized separately on 2026-09-29.

Do not treat planned components as implemented, or implement later phases without a new user request. Preserve the finance definitions. Flag conflicting requirements rather than silently changing a KPI.

## The data boundary

This replaces the original "synthetic only" rule, which was written before the SDP track existed. The boundary that protects people is unchanged; only the framing moved.

**Never, on either track:**

- No protected health information, ever.
- No beneficiary-level records, real names, addresses, dates of birth, SSNs, actual beneficiary IDs or real provider identifiers.
- No T-MSIS or TAF Research Identifiable Files, and nothing else obtained under a data use agreement. These require a ResDAC DUA and are out of scope by design, not by oversight.

**Permitted on the SDP track only:**

- Real public CMS policy documents, specifically approved state directed payment preprints, which contain aggregate payment arrangements and no beneficiary data.
- Real public aggregate files such as DQ Atlas topic exports and CMS-64 expenditure summaries.

**Never mix them.** Synthetic and real data do not share a table, a view, a published file or a directory. Real data lives under `data/raw/sdp/`, `src/sdp/` and `sql/sdp/`. Anything a reader could mistake for the other must say which it is.

## Working rules

- On the finance track, use fully synthetic records generated from scratch.
- On the SDP track, record every source: its URL, retrieval date, content hash, and what it cannot support. A figure nobody can trace back to a page is not publishable.
- Projected spending is not actual spending. Say so beside every SDP figure.
- Keep FFS medical spend, managed-care encounters, and state-to-plan capitation separate.
- Preserve explicit grains, claim revision resolution, denominator populations, time basis, and release gates.
- Documentation describes proposed design choices, not user-approved production policies or CMS-prescribed metrics.
- Update docs/HANDOFF.md after substantive work: completed artifacts, checks actually run, unresolved decisions, and next steps.
- Never claim a database, dashboard, test suite, deployment, GitHub repository, or AI integration exists without verifying it.
- Do not add credentials or generated datasets to version control.

No RTK.md was available when this foundation was created. If the user supplies it later, read it and reconcile applicable instructions before proceeding.
