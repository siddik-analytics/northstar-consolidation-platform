# ADR-0010 — Star schema, flattened hierarchies, calculation groups, PBIP/TMDL

**Status:** Accepted · **Date:** 2026-09-06 · **Phase:** 1

## Context

The semantic model must support drilldown from Group to GL account across a 181-account chart
and a 15-entity tree, deliver four scenario comparisons across eight time-intelligence
variants, and render a page in under three seconds. It must also be reviewable in version
control, because a report that only exists as a binary file is a report nobody can review.

## Decision

1. **Star schema with conformed dimensions.** Facts hold keys and measures; dimensions hold
   attributes. No snowflaking, no bridge tables, no bidirectional filters.
2. **Flattened hierarchies**, materialised as columns on the dimension, rather than
   parent-child structures.
3. **Calculation groups** for time intelligence and scenario comparison, rather than
   explicitly authored measure variants.
4. **PBIP project format with TMDL and PBIR**, so the model and the report are text.

## Alternatives considered

**Parent-child account and entity hierarchies.** Handles arbitrary depth and matches how the
chart is conceptually organised. In Power BI it requires `PATH` functions, produces ragged
hierarchies that need blank-level handling, and performs worse. The group chart is a fixed
four levels and the entity tree is three; neither needs arbitrary depth. Rejected.

**Explicit measures for every combination.** `Revenue`, `Revenue YTD`, `Revenue PY`,
`Revenue Budget`, `Revenue Var $`, `Revenue Var %`, and the same for thirty base measures —
several hundred near-identical DAX expressions, each an opportunity for a copy-paste error,
and each needing manual maintenance when a definition changes. Rejected. With calculation
groups, a new base measure inherits every variant automatically and a definition is changed
in exactly one place.

**DirectQuery against DuckDB.** Avoids a refresh step. Requires an ODBC bridge, gives up
Power BI's compression and in-memory performance, and would not meet the three-second target.
Rejected. At ~3.2m rows an import model compresses to well under a gigabyte.

**Standard `.pbix`.** The default and what most people ship. It is a binary file: no
meaningful diff, no code review, no merge. For an engagement whose central claim is
auditability, shipping the reporting layer as an unreviewable binary would be inconsistent.
Rejected.

## Consequences

**Positive.** Measures are defined once. Model changes appear as readable TMDL diffs in pull
requests. Import mode meets the performance targets. Conformed dimensions let headcount,
capex, debt and financial facts be sliced together without many-to-many relationships.

**Negative.** Calculation groups are unfamiliar to some Power BI users and interact
subtly with implicit measures — so implicit measures are disabled in the model, and all
measures are explicit. PBIP requires a reasonably current Power BI Desktop. Flattened
hierarchies must be rebuilt if the chart or entity structure gains a level, which is a
Phase 3 regeneration rather than a model redesign.

**Consequence for delivery.** The `.pbip` folder is the source of truth in git. Any published
`.pbix` is a build artefact, not a source file.
