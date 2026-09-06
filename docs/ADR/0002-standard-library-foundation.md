# ADR 0002: Keep the V0.1 runtime dependency-free

- Status: Accepted
- Date: 2026-09-06

## Context

MoneyOS should run on an ordinary laptop, remain useful without AI, and avoid binding its
persistent core to a framework. The initial environment has Python and Docker but may lack
package-manager tools or unrestricted network access.

## Decision

V0.1 uses Python 3.11+ standard-library components for runtime and baseline tests. SQLite SQL
is explicit and application writes are concentrated in a service/repository boundary.

## Consequences

Positive:

- a fresh checkout can run and test without downloads;
- offline and low-resource use is straightforward;
- framework replacement cannot own the ledger schema;
- Python 3.14 works without waiting for downstream compatibility.

Costs:

- `argparse` presentation is more verbose than a dedicated CLI framework;
- explicit row mapping and SQL require discipline;
- runtime type/schema validation is hand-written at this stage.

This decision is intentionally reversible. Pydantic, SQLAlchemy, Typer, Polars, or other tools
may be added when a concrete version needs them, provided they remain behind the established
domain boundaries.
