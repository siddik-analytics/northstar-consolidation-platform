# ADR-0003 — Consolidation layers instead of storing only consolidated results

**Status:** Accepted · **Date:** 2026-09-06 · **Phase:** 1

## Context

A consolidated figure is the sum of several very different things: what the entities
reported, what was eliminated between them, what was adjusted on consolidation, and what
management normalised for its own view. The CFO's core complaint is that today none of these
can be separated — the consolidated number arrives and the workings are in someone's
spreadsheet.

Separately, management adjustments and statutory results must not contaminate each other.

## Decision

Every fact row carries a **`layer_id`**. There are **exactly five layers**, defined once in
`config/dimensions/consolidation_layer.csv` and materialised into `dim_layer`. The set is
**closed**: no sixth layer exists, and a row carrying any other value is rejected.

| `layer_id` | Code | Name | Posting source | Posted to | Statutory | Management | Balances alone |
|---|---|---|---|---|---|---|---|
| 1 | `REPORTED` | Entity Reported | Source ERP extract | Real legal entities | Yes | Yes | Yes |
| 2 | `IC_ELIM` | Intercompany Eliminations | Elimination engine | `ELIM-IC` | Yes | Yes | Yes |
| 3 | `CONSOL_ADJ` | Consolidation Adjustments | Consolidation engine | `ELIM-CON` | Yes | Yes | Yes |
| 4 | `MGMT_ADJ` | Management Adjustments | Manual, approved | `ELIM-MGT` | **No** | Yes | Yes |
| 5 | `FX_CTA` | Translation Adjustment | Translation engine | Real legal entities | Yes | Yes | **No** |

```
Statutory  = layer_id IN (1,2,3,5)
Management = layer_id IN (1,2,3,4,5)
```

Layer contents:

- **1 REPORTED** — source trial balances, sign- and locale-normalised, mapped to the group
  chart and translated to USD. The only layer originating outside the platform.
- **2 IC_ELIM** — intercompany revenue, cost of sales, management fees, royalties, interest,
  receivables, payables and loans, eliminated from matched entity pairs.
- **3 CONSOL_ADJ** — investment-in-subsidiary elimination across the full ownership tree,
  purchase price allocation and acquired intangible amortisation, NCI allocation of profit
  and equity, unrealised profit in inventory. These **change** the consolidated result.
- **4 MGMT_ADJ** — normalisations, reclassifications and pro-forma presentation entries.
  Excluded from the statutory result.
- **5 FX_CTA** — the cumulative translation adjustment, posted to the real foreign entity.

**Layer 5 is the exception in two ways, and both are deliberate.** It does not balance
independently, because it *is* the entry that makes the translated layer-1 trial balance sum
to zero; and it is posted to real entities rather than a virtual one, because CTA is an
attribute of a specific foreign operation and entity-level CTA is a genuine reporting
requirement. Balancing controls therefore read `must_balance_independently` from `dim_layer`
rather than assuming every layer self-balances.

## Alternatives considered

**Store only the consolidated result.** Smallest and simplest. Makes the source-to-consolidated
reconciliation impossible to produce without re-running the engine, which is precisely the
capability the engagement exists to deliver. Rejected outright.

**Store entity data plus a separate adjustments table, unioned at report time.** Workable, but
adjustments then need parallel handling in every query and every measure, and the union is
easy to forget. The layer approach gets the same separation with natural aggregation.

**Management adjustments inside the consolidated numbers, backed out for statutory.** How most
hand-built consolidations work. It means the statutory number is derived by subtraction from a
management number, and no one can be certain what was removed. Rejected — the direction of
derivation matters, and the audited base must be primary.

## Consequences

**Positive.** The `CTL-REC-01` reconciliation becomes a `GROUP BY layer` over one table. Any
reported figure can be decomposed into its layers in a single click. Management normalisations
can never change the statutory result — enforced by `CTL-CON-06`, not by convention.

**Negative.** More rows, and every query must be layer-aware. Mitigated by making the reporting
marts layer-aware by default so that report authors get statutory unless they ask otherwise.

**The risk this creates, and how it is closed.** Because both reporting bases are defined by
*explicit* layer membership, a row carrying an undefined or null `layer_id` belongs to
neither. It is silently excluded from the statutory result and from the management view, and
nothing reports it as missing — the statements still balance without it. `CTL-CON-09` rejects
any such row at load, and `tests/test_config_integrity.py` asserts that the configuration
file, the documented statutory and management formulas, and every layer reference across the
documentation all agree on the same five layers. Adding a sixth layer is a breaking change
requiring a new ADR.
