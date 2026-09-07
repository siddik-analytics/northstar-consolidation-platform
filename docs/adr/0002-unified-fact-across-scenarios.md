# ADR-0002 — One unified fact table across Actual, Budget and Forecast

**Status:** Accepted · **Date:** 2026-09-06 · **Phase:** 1

## Context

The platform must support Actual vs Budget, Actual vs Forecast, Forecast vs Budget and
prior-year comparisons, drillable from Group down to GL account. The data for these
scenarios has different provenance: actuals come from three ERPs at journal level, budget
comes from a planning cycle, forecast is re-issued on a rolling basis.

The question is whether they share a fact table.

## Decision

**One fact table, `fact_financials`, holding all scenarios and versions at a common grain**,
distinguished by `scenario_key` and `version_key`.

Budget and forecast are captured at the **same grain as actual** — entity × account × cost
centre × intercompany partner × period × layer — rather than at a summarised grain.

## Alternatives considered

**Separate fact tables per scenario (`fact_gl`, `fact_budget`, `fact_forecast`).** The
conventional approach and superficially cleaner, since each table matches its source. Every
variance calculation then becomes a full outer join across tables with different grains and
different member sets, and every such join is a place where a missing budget row silently
becomes a variance equal to the whole actual. Rejected.

**Unified fact, but budget and forecast at a coarser grain** (entity × account × period, no
cost centre). Less planning effort, smaller tables. But cost centre is exactly where managers
hold budget accountability — a BU leader's first question about an overspend is *which
department*. A model that cannot answer it is not a management reporting model. Rejected.

## Consequences

**Positive.** Variance is a subtraction over one table with one grain. A variance drills to
the same cost centre and account as the actual. Power BI calculation groups work naturally
because the scenario dimension is a real dimension rather than a table selector. Adding
`FY2027 Plan` requires no schema change.

**Negative.** Budget and forecast must be generated at full grain, which is more work in
Phase 2 and produces a larger fact table (~1.1m rows rather than ~500k). Both costs are
accepted; the row count is well within DuckDB and Power BI import limits.

**Risk.** A single fact table across scenarios makes it possible to sum Actual and Budget
together by accident. Mitigated by making `scenario_key` a required filter in every reporting
mart and by defaulting the semantic model to Actual.
