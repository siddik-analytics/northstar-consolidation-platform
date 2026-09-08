# Phase 4 — Upstream Defects Found

Phase 4 must not repair upstream data inside the consolidation engine. Where it finds a
genuine defect in the frozen Phase 3.1 layer, it stops, documents it, and reports it. This
file is that record.

> **Both defects are now CLOSED.** They were corrected at the generation layer in the
> approved Phase 3.2 pass and the source layer was regenerated from the corrected code; no
> generated artefact was edited by hand and the consolidation engine carries no override.
> `docs/phases/phase-03-2-report.md` records the corrections, their financial effect and the
> regression against the Phase 4 engines. The analysis below is left as it was written, when
> both were open, because it is the evidence the corrections were made against.

---

## P3-D-05 — the opening translation rate registered for NIG-510 is the wrong month's close

**Status:** CLOSED in Phase 3.2 (SX-008). Originally raised as OPEN; the analysis below is as written then.

**Where.** `data/reference/fx_rates_historical.csv`, one row:

```
NIG-510, ACQ_OPENING_BS, ACQUISITION_DATE, 2023-01-01, GBP, 1.23412025, "closing spot 202301"
```

**What it is.** `ACQ_OPENING_BS` is the rate an entity's opening balance sheet is stated at —
the translation base every subsequent closing-rate revaluation is measured from (FX-P16). For
NIG-510 it is recorded as the **31 January 2023** closing rate. It should be the **FY2022
closing anchor, 1.2083**.

**Why that is the right value.** NIG-510's consolidation effective date is **2023-01-01** — the
first day of the modelled window. Its opening balance sheet is therefore the FY2022 closing
position, exactly like every other entity that opens at the start of the window, and its base
rate is the same FY2022 closing anchor those entities use. `NIG-320`, also GBP and also opening
at the start of the window, correctly carries 1.2083 in the same file.

The two genuine intra-window acquisitions are **not** affected and are correctly registered:

| Entity | Effective date | Registered base | Correct? |
|---|---|---|---|
| `NIG-220` Halden Valve | 2023-04-01 | 1.07468897 = 202304 close | ✅ an acquisition inside the window; the acquisition-month close is the base |
| `NIG-410` Vector Systems | 2024-07-01 | 1.04133215 = 202407 close | ✅ same |
| `NIG-510` Parts UK | **2023-01-01** | 1.23412025 = 202301 close | ❌ opens at the start of the window; should be the FY2022 anchor, 1.2083 |

**Independent corroboration.** `data/reference/cta_expectation.csv` — the acceptance oracle
this phase is graded against, produced in Phase 2.2 from the source ledgers and the approved
rate file — uses **1.2083** as NIG-510's opening rate for 202301, and the FY2023 group CTA
anchor was derived from it. The register and the oracle disagree, and the anchors follow the
oracle.

**Why it is an upstream defect and not a Phase 4 defect.** The rate is an input to
translation, published as frozen Phase 2 reference data. The consolidation engine implements
FX-P16 by reading it. An engine that substituted a different rate because it preferred one
would be repairing source data inside the consolidation, which is exactly what the phase brief
prohibits.

**Affected population.** One entity-period: NIG-510, 202301. The rate is the base for every
later revaluation of that entity's opening position, so the effect persists as a level shift
rather than reversing.

**Financial effect.** NIG-510's opening net assets of GBP 5,603,191 are translated at 1.23412
instead of 1.2083 — **2.14% too high**:

| | |
|---|---|
| Opening net assets, local | GBP 5,603,191 |
| At the registered rate (1.23412) | USD 6,914,996 |
| At the correct rate (1.2083) | USD 6,770,336 |
| **Difference** | **USD 144,660** |
| CTA movement, 202301, engine | USD (0.000415)m |
| CTA movement, 202301, oracle | USD 0.144261m |
| **Unexplained difference against the oracle** | **USD 0.144676m** |

It is 0.0026% of FY2023 consolidated total assets and 2.7% of the FY2023 group CTA movement.
It does not move revenue, EBITDA or net income: it is a translation-base difference inside
equity, offset between NCI, group CTA and the translated opening net assets.

**Proposed correction.** Change the single row to `1.2083`, with `basis` restated as
`FY2022 closing anchor` to match `NIG-320`, and regenerate. Every other entity-period already
agrees with the oracle to within USD 1, so nothing else is expected to move; the FY2023 group
CTA anchor was derived on this basis and will not change.

**How Phase 4 behaves in the meantime.** The engine reads the registered rate. `P4-FX-04`
reports the resulting disagreement with the oracle as a `SOURCE_FINDING` naming this defect,
its entity, its period and its amount — so the difference is explained and attributed rather
than absorbed into a tolerance. Every other entity-period agrees.

---

## P3-D-06 — the investment in NIG-510 is in the register but not in any ledger

**Status:** CLOSED in Phase 3.2 (SX-009). Originally raised as OPEN; the analysis below is as written then.

**What it is.** `NIG-500`'s USD 16.9m investment in `NIG-510` Northstar Parts UK exists in
both registers and in **no ledger**:

| Source | Says |
|---|---|
| `config/entities/investment_register.csv` INV-009 | NIG-500 acquired 80% of NIG-510 on 2022-12-31 for USD 16.9m |
| `data/reference/investment_rollforward.csv` | NIG-500 / NIG-510, closing cost USD 16.9m in every period from 202301 |
| `fact_journal_line`, account `178100` | NIG-100 358.3m, NIG-200 22.0m, NIG-300 16.0m, NIG-400 38.0m — **no NIG-500 row at all** |

Layer 1 therefore carries USD 344.3m of investments at 202301 where the registers say
USD 361.2m.

**Why Phase 2 did not catch it.** `P2-INV-01` reconciles ledger investment balances to the
roll-forward by iterating over the **ledger** balances and looking each one up in the register.
An entity that appears in the register and has no ledger balance is never looked at. It is the
same control-design defect as the one Phase 3.1 found in `P2-IC-01`: a control measured over
the population that already satisfies it cannot fail.

**Why it is an upstream defect.** The investment is a posting the entity's own ledger should
carry — the parent paid USD 16.9m and holds an asset. Creating it inside the consolidation
engine would be fabricating a source balance.

**Affected population.** One parent-subsidiary relationship, every period from 202301.

**Financial effect.** USD 16.9m of investment in subsidiary, and the corresponding USD 16.9m
of consideration in the goodwill bridge for the only non-controlling interest in the group.
Because an investment in a consolidated subsidiary is eliminated in full, the effect on
consolidated **total assets is nil**; what it changes is the composition of the elimination
and of the group's opening consolidated retained earnings.

**Proposed correction.** `src/generation/series.py` builds each holder's `178100` path from
`investments_at()`; establish why the NIG-500 → NIG-510 relationship produces no balance,
correct it, and widen `P2-INV-01` to test the register's population rather than the ledger's.

**How Phase 4 behaves in the meantime.** The investment elimination is built from the
investments **layer 1 actually carries**, which is what a real consolidation eliminates. It
does not invent the missing balance. `P4-INV-01` reconciles layer-1 investments to the
register and reports this gap as a `SOURCE_FINDING` naming the relationship and the amount.
