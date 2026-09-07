# ADR-0008 — Customer and product detail in a separate, reconciled fact

**Status:** Accepted · **Date:** 2026-09-06 · **Phase:** 1

## Context

The brief lists Customer and Product/Service as useful reporting dimensions. The general
ledger does not carry them: an invoice line knows its customer, but an accrued audit fee, a
depreciation charge and a foreign exchange revaluation do not.

## Decision

Customer and product live on a **separate fact table, `fact_revenue_detail`**, at the grain
entity × customer × product × period × scenario × version. It is **reconciled to the GL
revenue accounts** by control `CTL-REC-02`.

`fact_financials` — the consolidation fact — carries no customer or product key.

## Alternatives considered

**Put customer and product on the GL fact.** Superficially the simplest answer to "we want to
analyse revenue by customer". It multiplies the fact's cardinality by several orders of
magnitude while leaving the keys undefined for the large majority of rows, which then need an
`N/A` member that dominates every customer-sliced total. It also creates a grain conflict: the
GL fact would be at journal-line grain for revenue and at account-balance grain for everything
else. Rejected.

**Two grains inside one fact table, distinguished by a flag.** All of the problems above plus
the certainty that someone eventually sums across both grains. Rejected.

**No customer or product analytics at all.** Removes a stated requirement and a genuinely
useful capability — customer concentration is a standing board question for a PE-backed group.
Rejected.

## Consequences

**Positive.** Each fact keeps one clean grain. The consolidation fact stays compact and fast.
Revenue analytics get proper customer and product dimensionality, including cost of sales and
gross profit at that grain, without polluting the accounting model.

**Negative.** Two facts must agree. If they diverge, the analytics and the accounts tell
different stories in the same pack, which is worse than having no analytics. `CTL-REC-02`
therefore makes divergence a **blocking** failure: revenue in the detail fact must equal
revenue on the corresponding GL accounts, per entity and period.

**Consequence for reporting.** Measures that cross the two facts — revenue per customer as a
share of group revenue, for example — must be built through the conformed `dim_entity` and
`dim_date`, not by joining the facts directly. This is a standard conformed-dimension pattern
and is documented for report authors in the data contract.
