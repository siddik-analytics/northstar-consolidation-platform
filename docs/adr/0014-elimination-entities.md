# ADR-0014 — Eliminations posted to dedicated virtual entities

**Status:** Accepted · **Date:** 2026-09-06 · **Phase:** 1

## Context

Elimination and consolidation entries have to be posted somewhere. Three common choices: net
them against the entities involved, post them all to the parent, or post them to a virtual
entity that exists only in the consolidation.

## Decision

**Three virtual entities**, each carrying one class of entry:

| Entity | Layer | Contents |
|---|---|---|
| `ELIM-IC` | 2 | Intercompany eliminations |
| `ELIM-CON` | 3 | Investment elimination, PPA, NCI allocation, unrealised profit in inventory |
| `ELIM-MGT` | 4 | Management adjustments (management view only) |

All are `entity_type = 'ELIMINATION'`, `is_elimination_entity = TRUE`, functional currency
USD, and never receive source ERP data. Entries within each must balance
(`CTL-IC-06`).

## Alternatives considered

**Net eliminations against the participating entities.** The consolidated total is right and no
extra entities are needed. It destroys entity-level reporting: `NIG-200`'s revenue would be
reduced by intercompany sales it genuinely made, so the entity P&L would no longer agree to its
own trial balance, and a BU leader reviewing their numbers would find figures that match
nothing they can see in their ERP. Rejected.

**Post everything to the parent, `NIG-100`.** Keeps the entity count down. Makes Topco's
standalone result meaningless — it would carry the group's eliminations mixed with its own
treasury activity, and Topco does have real activity: external debt, the swap, intercompany
lending. Rejected.

**One combined elimination entity.** Simpler than three. It merges intercompany eliminations,
consolidation adjustments and management normalisations into one bucket, which defeats the
layer model in ADR-0003 — the whole point of which is that these three are different kinds of
thing with different audiences and different statutory treatment. Rejected.

## Consequences

**Positive.** Entity-level reported figures always agree to that entity's own trial balance,
which is what makes them credible to the people who own them. Each class of consolidation entry
is separately visible and separately reportable, so the `CTL-REC-01` reconciliation falls out
naturally. `ELIM-MGT` can be excluded from the statutory view by a simple entity or layer
filter.

**Negative.** `dim_entity` contains rows that are not legal entities, so any report listing
"entities" must filter them out. Handled by `entity_type`, and the operating-entity count is
asserted at 12 in `tests/test_config_integrity.py`. Elimination entities also need explicit
handling in the ownership tree — they hang off `NIG-100` for hierarchy completeness but are
excluded from ownership arithmetic.

**Note.** Layer 5 (`FX_CTA`) is deliberately **not** posted to a virtual entity. CTA is an
attribute of a specific foreign operation, and entity-level CTA is a genuine reporting
requirement, so the translation balancing entry is posted to the real entity it belongs to.
