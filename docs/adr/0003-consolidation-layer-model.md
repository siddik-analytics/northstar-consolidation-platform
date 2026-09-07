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

Every fact row carries a **`layer_key`**:

| Layer | Contents | Statutory | Management |
|---|---|---|---|
| 1 `REPORTED` | Entity trial balances, mapped and translated | Yes | Yes |
| 2 `IC_ELIM` | Intercompany eliminations | Yes | Yes |
| 3 `CONSOL_ADJ` | Investment elimination, PPA, NCI, unrealised profit | Yes | Yes |
| 4 `MGMT_ADJ` | Normalisations and reclassifications | **No** | Yes |
| 5 `FX_CTA` | Translation balancing entry | Yes | Yes |

```
Statutory  = L1 + L2 + L3 + L5
Management = L1 + L2 + L3 + L5 + L4
```

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

**Note.** Layer 5 (`FX_CTA`) is posted to real entities rather than a virtual one, because CTA
is an attribute of a specific foreign operation and entity-level CTA is a genuine reporting
requirement.
