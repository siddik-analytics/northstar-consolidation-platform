# Phase 3.2 Report — Targeted Source Correction Pass

**Status:** Complete · **Date:** 2026-09-07 · **Next gate:** resume Phase 4

Phase 4 stopped when the consolidation engine found two defects in the frozen Phase 3.1
layer. Both are corrected here, at the generation layer, with the source regenerated from the
corrected code. Scope was strictly the two defects; nothing else was touched.

Both were found by an engine that had to reproduce an independently produced expectation, and
neither was found by a source control. That is the useful part: a self-consistency check asks
whether the data agrees with itself, and both of these defects left data that agreed with
itself perfectly.

---

## 1. Summary

| | |
|---|---|
| Defects corrected | **2 — P3-D-05, P3-D-06, both CLOSED** |
| Source exceptions outstanding | **0** (nine registered, all closed) |
| Phase 2 controls | **80 of 80 pass** (was 79; `P2-FX-04` added) |
| Phase 3 controls | **62 of 62 pass**, 0 source findings |
| Mapping agreement | **100.000000%** across all lines, unchanged |
| CTA against the oracle | **243 of 243 entity-periods**, worst USD 1 (was 242 of 243) |
| Intercompany elimination | 2,355 pair-periods, all matched, unchanged |
| Headline anchors moved | **none** |
| Tests | 390 → **401** |
| Two full regenerations | identical digests and artefacts |

---

## 2. P3-D-05 — the opening translation base

**Root cause.** `src/generation/fx.py::historical_rates()` chose an entity's opening
translation base with:

```python
if pk < 202301:                      # period number, not date
    rate = FY2022 closing anchor
else:
    rate = closing rate of the acquisition month
```

An entity consolidated **on** 1 January 2023 has `pk == 202301`, which is not `< 202301`, so
it fell into the acquisition branch and was registered at the **January 2023** closing rate.

The deeper problem is that the same generator states the same opening balance sheet twice and
the two statements disagreed. `series.py::opening_bs_usd()` converts an entity's opening
balances into local currency at the **FY2022 closing anchor** whenever
`effective_from <= 2023-01-01`. `historical_rates()` then registered the base the
consolidation engine would translate those same balances back at — and used a different test.
NIG-510's opening balance sheet was therefore *stated* at 1.2083 and *registered* at 1.23412.

Nothing balanced differently. The 2.14% difference simply became CTA, which is precisely the
kind of error the CTA oracle exists to catch and no self-consistency check can.

**Correction.** The branch is expressed on the date the window opens rather than on a period
number, and matches the test `opening_bs_usd()` applies to the same balances:

```python
WINDOW_OPENS = date(2023, 1, 1)
if eff <= WINDOW_OPENS:
    rate = FY2022 closing anchor       # the balance sheet IS the FY2022 closing position
else:
    rate = closing rate of the acquisition month
```

**The two genuine intra-window acquisitions are unchanged**, and deliberately so: NIG-220
(2023-04-01) and NIG-410 (2024-07-01) open from their own acquisition-date balance sheets,
which `_build_actuals` converts at that month's closing rate, so that rate is the correct base
for them. The CTA oracle agreed with both before the correction and still does.

**Independent confirmation of 1.2083.** Four sources, none of them the row that was wrong:

| Source | Value |
|---|---|
| `_anchor_rates()[("GBP", 2022, "ACTUAL")]` closing anchor | 1.2083 |
| `NIG-320`, the other GBP entity opening at the start of the window | 1.2083 |
| `cta_expectation.csv`, NIG-510 202301 `opening_rate` | 1.2083 |
| `opening_bs_usd()`, the rate NIG-510's own opening balances were converted at | 1.2083 |

---

## 3. P3-D-06 — the investment that was in every register and no ledger

**Root cause, and it was mine.** Phase 3.1 corrected P2-D-03 by making every intercompany
balance name its counterparty, which meant the opening journal began taking its intercompany
legs from a per-counterparty **decomposition** rather than from the balance itself. The
decomposition of `178100` was written as:

```python
{("178100", sub): amt for (par, sub), amt in investments_at(open_at).items()
 if par == code and self.lb.live_at(sub, open_at)}
```

`live_at(sub, open_at)` asks whether the subsidiary is **consolidated** at the opening date.
The opening balance sheet carries what the parent **held**. Those are different questions, and
for NIG-510 — bought on 31 December 2022, consolidated from 1 January 2023 — they give
different answers. `opening_bs_usd()`, which builds the balance, applies no such filter.

So the decomposition was short by one relationship, the opening journal took `178100` only
from the decomposition, and USD 16.9m of investment disappeared. **The trial balance still
closed**, because the opening journal's plug goes to retained earnings: a missing asset simply
made the plug 16.9m smaller. No control moved.

**Correction, in two parts.**

1. The decomposition uses the same population the balance does — no `live_at` filter. A
   subsidiary bought on the closing date is paid for that day whatever date its consolidation
   begins.
2. **The general guard**: `opening_balance()` now refuses to post when a decomposition does
   not sum to the balance it decomposes, for every intercompany balance account and not only
   this one. A decomposition that is short is exactly as invisible on any other account.

```python
for account in IC_BALANCE_ACCOUNTS:
    if abs(balances.get(account, 0.0) - sum(parts for that account)) >= 0.005:
        raise AssertionError(...)
```

---

## 4. `P2-INV-01` redesigned

**What was wrong with it.** It walked the **ledger's** investment balances and looked each one
up in the roll-forward. An entity that appeared in the register and had no ledger balance was
never looked at. It is the same control-design defect Phase 3.1 found in `P2-IC-01` — a
control measured over the population that already satisfies it cannot fail — and it is the
second time that shape has cost this platform a phase.

**What it does now.** The **register is the authoritative population**. For every
relationship and period the register requires, does the parent's ledger carry that investment,
at that amount, from that date — and is there anything in the ledger the register does not
require? It reports each condition separately:

| Condition | How it is detected |
|---|---|
| missing investment | a required relationship-period with no ledger balance |
| unexpected investment | a ledger balance no register row requires |
| wrong parent / wrong subsidiary | a ledger pair the register does not name |
| wrong amount | a required relationship-period off by more than USD 1 |
| wrong effective date | a ledger balance appearing before the register says it was paid for |
| duplicate relationship | the same parent, subsidiary, date and consideration registered twice |

Measured over **463 relationship-periods**. `test_the_investment_control_detects_each_defect_class`
proves it fails on each condition rather than only that it passes on clean data.

**`P2-FX-04` added** for the other defect, on the same principle: it recomputes every opening
translation base from the rule the opening balance sheet is built with and compares it with
what was registered. The two halves of the generator can no longer disagree in silence.

---

## 5. Files changed

**Generator (4):**

| File | Change |
|---|---|
| `src/generation/fx.py` | `WINDOW_OPENS`; `historical_rates()` branches on the date, not the period number |
| `src/generation/series.py` | the opening intercompany decomposition uses the population the balance uses |
| `src/generation/journals.py` | `opening_balance()` asserts every decomposition sums to its balance |
| `src/generation/validate.py` | `P2-INV-01` redesigned around the register; `P2-FX-04` added |

**Configuration (1):** `config/controls/source_exception_register.csv` — SX-008 and SX-009,
both `CLOSED` at nil.

**Generated reference data (1):** `data/reference/fx_rates_historical.csv` — one rate and its
basis label. **`cta_expectation.csv` and `investment_rollforward.csv` regenerate
byte-identical**, which is itself evidence: the oracle and the roll-forward were right all
along, and it was the ledger and the rate register that disagreed with them.

**Tests (3):** `tests/test_phase03_2_corrections.py` (11 new); the defect-reference pattern in
two existing tests widened to `P[23]-D-nn`.

**Documentation (2):** this report; `docs/phases/phase-04-source-findings.md` marked closed.

**Not touched:** every anchor, every chart, every mapping rule, the ERP adapters, sign
normalisation, and the whole of `src/pipeline/` and `src/consol/`.

---

## 6. Financial effect — P3-D-05

The correction is confined to one entity and, through the CTA it was suppressing, to FY2023.

| USD | Before | After | Change |
|---|---|---|---|
| NIG-510 opening net assets, local | GBP 5,603,191.27 | GBP 5,603,191.27 | — |
| Opening translation base | 1.23412025 | **1.2083** | (0.02582) |
| **Translated opening equity** | 6,914,996 | **6,770,336** | **(144,660)** |
| CTA opening, FY2023 | nil | nil | — |
| NIG-510 CTA movement, FY2023 | 0.208862 | **0.353538** | +0.144676 |
| — group share (80%) | 0.167090 | **0.282830** | +0.115740 |
| — NCI share (20%) | 0.041772 | **0.070708** | +0.028936 |
| NIG-510 CTA closing, FY2023 | 0.208862 | **0.353538** | +0.144676 |
| Group CTA movement, FY2023 (all entities) | 1.351504 | **1.467244** | +0.115740 |
| NCI share of group CTA, FY2023 | 0.041772 | **0.070708** | +0.028936 |

FY2024 and FY2025 are **unchanged** — the base error was a level shift established in the
first month, and once the opening position is stated correctly every later revaluation was
already right.

**The NCI CTA share now reproduces the approved anchor exactly.** `NCI_FX FY2023A = 0.070708`
in `src/anchors/build_anchors.py`; the engine derives 0.070708. Before the correction it
derived 0.041772 against the same anchor. That is independent corroboration from a direction
the correction did not aim at.

**Consolidated equity expectation.** Group equity attributable to the parent rises by
USD 0.116m and NCI by USD 0.029m in FY2023, USD 0.145m in total — offset in full by the
lower translated opening net assets, so **consolidated total equity is unchanged**. Revenue,
gross profit, EBITDA, cash, debt and working capital are untouched.

---

## 7. Financial effect — P3-D-06

| | Before | After |
|---|---|---|
| NIG-500 investment in NIG-510 | **absent** | USD 16,900,000 |
| Group investments at cost, layer 1 | USD 434.3m | **USD 451.2m** |
| Register relationships reaching a ledger | 10 of 11 | **11 of 11** |
| Acquisition consideration, INV-009 | USD 16.9m | unchanged |
| Investment roll-forward | already carried it | unchanged, byte-identical |
| NIG-500 opening retained earnings | (9,057,683) + 16.9m understatement | **(9,057,683)** as stated |
| Expected Phase 4 investment elimination | 10 relationships | **11 relationships** |
| Layer-1 trial balance | nil in every period | **nil in every period** |
| Group cash, FY2025 | USD 22.0m | **USD 22.0m** |

The defect moved nothing outside the group's internal structure, which is exactly why it
survived: the missing asset was absorbed by the opening retained-earnings plug at the same
entity, so every total that anyone looks at was correct. What it broke was the
**relationship** — and Phase 4's investment elimination pairs an investment against the equity
it was paid for, so it would have had one side of the group's only non-controlling interest
missing.

No headline anchor moved. `tools/derive_anchor_inputs.py --check` reports that all three
derived inputs still agree with the generated data, so no anchor re-derivation was needed.

---

## 8. Regression against the partial Phase 4 engines

Re-run from `c55d441` against the corrected source. Nothing in `src/consol/` was changed.

| Engine | Before | After |
|---|---|---|
| **Ownership tree** | 12 entities, 4 second-tier, 20% effective NCI on NIG-510, no cycles, one path each | **unchanged** |
| **FX translation** | 44,489 translated rows | recomputed from corrected data |
| **CTA vs the oracle** | 242 of 243 agree, worst USD 0.144676m | **243 of 243 agree, worst USD 0.000001m** |
| **CTA — USD entities** | exactly zero | **exactly zero** |
| **CTA — group, FY2023** | 1.351504 | **1.467244** |
| **CTA — group, FY2024 / FY2025** | (2.685181) / 5.000941 | **unchanged** |
| **Intercompany matching** | 2,355 pair-periods, all MATCHED | **unchanged** |
| **Intercompany residual** | USD 39.39 across all pairs | **unchanged** |
| **Elimination legs** | 4,406, none unbalanced | **unchanged** |

The intercompany result is unchanged because neither correction touches an intercompany
relationship: the investment account is not reciprocal and is excluded from pair matching, and
the translation base moves an equity balance rather than a counterparty position. The CTA
result improves to exact agreement, which is what the corrections were for.

---

## 9. Determinism

Two complete regenerations — anchors, source, Phase 2 controls, fault fixtures, Phase 3
pipeline — produce identical output:

| Evidence | Result |
|---|---|
| Frozen source digest | `fd7afb8fd7dc8058…` on both runs |
| `fx_rates_historical.csv` | identical |
| `cta_expectation.csv` | identical, and **unchanged from before the correction** |
| `investment_rollforward.csv` | identical, and **unchanged from before the correction** |
| `phase02_control_results.csv`, `phase03_manifest.json` | identical |
| Working tree after a full rebuild | clean |

---

## 10. Source exception register

Nine entries, **all `CLOSED` at an accepted population of nil**. A closed exception is not a
deleted one: the register still names the defect, so a recurrence fails the control instead of
reappearing as an accepted finding.

| Exception | Defect | Control | Closed in |
|---|---|---|---|
| SX-001 … SX-007 | P2-D-01 … P2-D-04 | P3-MAP / P3-TB / P3-DIM / P3-REC | Phase 3.1 |
| **SX-008** | **P3-D-05** | `P2-FX-04` | **Phase 3.2** |
| **SX-009** | **P3-D-06** | `P2-INV-01` | **Phase 3.2** |

---

## 11. What this pass says about the control framework

The same control-design defect has now cost two phases: `P2-IC-01` iterated the intercompany
lines that already carried a counterparty, and `P2-INV-01` iterated the investments the ledger
already held. Both could not fail. Both were written by somebody who knew what the answer
should be and checked that the data agreed with itself.

The rule that follows is worth stating as a rule rather than as two fixes: **a control's
population comes from the authority that requires the data, never from the data itself.** The
register says which investments must exist; the flow matrix says which intercompany
relationships must exist; the policy says which translation bases must exist. A control that
starts from the ledger can only ever confirm that what is there is consistent, which is the
one thing that was never in doubt.

Both defects in this pass were found by the consolidation engine rather than by a source
control, and for the same reason: the engine has to reproduce an expectation produced
somewhere else, so it asks the data questions the data did not get to choose.
