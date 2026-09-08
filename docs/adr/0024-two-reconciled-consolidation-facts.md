# ADR-0024 — two reconciled consolidation facts, not one

**Status:** accepted, Phase 4
**Related:** [ADR-0003](0003-five-consolidation-layers.md),
[ADR-0014](0014-consolidation-entries-are-posted-to-virtual-entities.md),
[ADR-0019](0019-five-layer-ingestion-with-line-level-lineage.md)

## Context

A consolidation has to answer two different questions and they want two different shapes of
data.

*"What is consolidated revenue in March?"* wants a small fact at the reporting grain, one row
per entity, account, cost centre, partner, period, scenario, version and layer, that a
reporting tool can aggregate without knowing anything about consolidation.

*"Why did group equity move by 3.5 million?"* wants the entries themselves: the process that
produced each one, the rule it was driven by, the entities it is about, the evidence it rests
on, and both sides of every posting. A total can only be recomputed. A journal can be read.

Serving the first question from the second means scanning leg-level detail to answer a
question about a caption. Serving the second from the first means the lineage was aggregated
away and the answer is "because the total is different".

The usual compromise is to keep only the aggregate and reconstruct the explanation by hand
when someone asks — which is the state most spreadsheet consolidations are in, and the reason
the question takes a week.

## Decision

Hold both, and prove they agree.

* **`fact_consol_journal`** — every consolidation entry at leg grain. `process`, `rule_id`,
  `entity_code`, `related_entity_code`, `partner_entity_code`, `narrative` and `evidence`
  travel with the leg. Journal ids are derived from the business keys they represent
  (`journal_id()`), never from a clock or a counter, so the same entry has the same id in
  every rebuild.
* **`fact_financials`** — the monthly financial position at the consolidation grain, carrying
  `layer_id` and `journal_character`. Layer 1 comes from the translated entity ledgers;
  layers 2 to 5 come from `fact_consol_journal`.

Because layers 2 to 5 of the second are **built from** the first, they cannot disagree by
construction — and `P4-FCT-01` proves it anyway, by rebuilding the layer totals from the
journal fact and comparing. A construction that cannot fail is still worth testing: the thing
being tested is not the arithmetic, it is that nobody has since added a path that writes one
without the other.

## Consequences

* Every consolidated number is traceable to the entries that produced it, and every entry is
  traceable to the rule and the register row that required it. That is what makes the audit
  lineage a query rather than an exercise.
* The two facts are written by one orchestrator in one order, so there is no window in which
  they can be inconsistent.
* Duplication is real but bounded: the journal fact holds only consolidation entries — layer 1
  is never copied into it — so it is a few thousand rows against a few hundred thousand.
* A reporting layer never needs to know that layers exist beyond choosing a view.
  `vw_statutory_fact` and `vw_management_fact` select the layer sets at the architecture level,
  so a management normalisation cannot reach the statutory result by being filtered wrongly at
  report time.
