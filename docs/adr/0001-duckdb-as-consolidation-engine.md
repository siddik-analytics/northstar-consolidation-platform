# ADR-0001 — DuckDB as the consolidation and warehouse engine

**Status:** Accepted · **Date:** 2026-09-06 · **Phase:** 1

## Context

The consolidation engine has to perform set-based accounting logic over roughly 3.2 million
rows: mapping, translation, elimination, NCI allocation and cash flow derivation. It must be
reproducible on a laptop, source-controllable, and produce output that Excel and Power BI can
consume without a server.

## Decision

**DuckDB**, driven from Python, with SQL as the primary transformation language and Python
reserved for orchestration, generation and anything genuinely procedural. Warehouse tables
are materialised as Parquet for consumption by Excel and Power BI.

## Alternatives considered

**pandas or Polars only.** Consolidation logic is fundamentally relational — joins across
mappings, entities, partners and periods. Expressing intercompany matching or a cash flow
derivation as DataFrame operations produces code that is harder to review than the SQL it
replaces, and a controller cannot read it. Rejected on reviewability, which matters more
than performance here.

**PostgreSQL or SQL Server.** Full SQL and familiar to finance IT, but requires a server. The
project must clone and run. Rejected on reproducibility. The SQL written for DuckDB is close
enough to standard that a port would be a small piece of work if the client later wanted one,
and that portability is deliberately preserved: no DuckDB-specific syntax where standard SQL
will do.

**SQLite.** Runs anywhere, but row-oriented and weak on analytic SQL — no `QUALIFY`, limited
window function support, poor aggregate performance. Rejected on capability.

**A cloud warehouse (Snowflake, BigQuery, Fabric).** Realistic for a client of this size and
the natural production target. Rejected for this engagement because it makes the deliverable
un-runnable without credentials and a bill, which defeats reproducibility.

## Consequences

**Positive.** Single-file database, no server. Reads and writes Parquet and CSV natively, so
the Excel and Power BI handoff needs no export layer. Columnar and vectorised, so a full
rebuild over 3.2m rows finishes in well under the five-minute target. SQL is reviewable by a
finance professional, which matters when the logic being reviewed is an elimination rule.

**Negative.** Single-writer, so no concurrent pipeline runs — irrelevant for a monthly close.
Less mature tooling than an established warehouse. Not a production platform for a group that
grows past this size; the migration path is stated above and deliberately kept open.

**Neutral.** Requires `duckdb` as a Python dependency. Version is pinned.
