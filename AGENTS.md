# Instructions for continuing agents

Read README.md and docs/HANDOFF.md first, followed by all four design documents linked there.

## Scope

The user authorized Phase 1 repository structure and documentation only. Do not treat planned components as implemented, or implement later phases without a new user request. Preserve the finance definitions and synthetic-only boundary. Flag conflicting requirements rather than silently changing a KPI.

## Working rules

- Use fully synthetic records generated from scratch; do not retrieve real beneficiary data or restricted TAF files.
- Keep FFS medical spend, managed-care encounters, and state-to-plan capitation separate.
- Preserve explicit grains, claim revision resolution, denominator populations, time basis, and release gates.
- Documentation describes proposed design choices, not user-approved production policies or CMS-prescribed metrics.
- Update docs/HANDOFF.md after substantive work: completed artifacts, checks actually run, unresolved decisions, and next steps.
- Never claim a database, dashboard, test suite, deployment, GitHub repository, or AI integration exists without verifying it.
- Do not add credentials or generated datasets to version control.

No RTK.md was available when this foundation was created. If the user supplies it later, read it and reconcile applicable instructions before proceeding.
