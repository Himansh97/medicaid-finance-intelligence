# Schema conventions

**Status:** first implementation. The logical design is [docs/data_dictionary.md](../../docs/data_dictionary.md); this directory is its executable form.

## Engine

SQLite is the development target because it needs nothing installed and the fixture must run for any reviewer. PostgreSQL remains the deployment target named in [docs/architecture.md](../../docs/architecture.md).

The DDL stays within the intersection of both engines wherever that costs nothing. Where it does not, the difference is noted in the file and listed here:

| Concern | SQLite here | PostgreSQL equivalent |
|---|---|---|
| Money | `INTEGER` cents | `NUMERIC(18,2)` dollars |
| Surrogate keys | `INTEGER PRIMARY KEY` | `GENERATED ALWAYS AS IDENTITY` |
| Enumerations | `TEXT` plus `CHECK` | same, or a domain type |
| Foreign keys | require `PRAGMA foreign_keys = ON` | enforced by default |

`PRAGMA foreign_keys = ON` is not the default in SQLite. Every connection must set it or the references below are documentation rather than constraints.

## Money is stored in integer cents

The data dictionary specifies `DECIMAL(18,2)`. SQLite has no decimal type; a column declared `DECIMAL` stores a float, and floats cannot represent most cent values exactly. This project blocks a release when a header and its lines differ by more than $0.01 and requires cent-level agreement across financial bridges, so a representation that is approximately right would undermine the control it is meant to test.

Amounts are therefore stored as signed `INTEGER` cents in columns suffixed `_amount_cents`. Conversion to dollars happens once, at the reporting boundary. On PostgreSQL these columns become `NUMERIC(18,2)` in dollars and the suffix changes with them.

This is a storage decision, not a definition change. No KPI in [docs/kpi_dictionary.md](../../docs/kpi_dictionary.md) is affected.

## Layers

Files apply in numeric order.

| File | Contents |
|---|---|
| `001_operational.sql` | Run, batch, and quarantine entities that every other row references |
| `002_raw.sql` | Immutable landing tables; nullable fields, few constraints, duplicates permitted |
| `003_dimensions.sql` | Conformed descriptive lookups |
| `004_exposure.sql` | Eligibility spans and the member-month fact |
| `005_claims.sql` | Claim header and line versions, and the resolved finals |
| `006_financial.sql` | Signed FFS payment ledger and capitation transactions |

Raw tables accept defects on purpose. A fixture that cannot express a duplicate, an orphan, or an unmapped code cannot demonstrate that a quality rule catches one. Constraints tighten as data moves toward the curated layer, which is where the grains in the data dictionary are enforced.

## What is not here yet

No transformations, quality rules, KPI views, marts, or release logic. The curated `fact_member_month` and `fact_claim_*_final` tables are created but not populated; the resolution that fills them is the next task.
