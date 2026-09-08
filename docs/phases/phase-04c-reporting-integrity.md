# Phase 4C — reporting integrity and the cross-artefact control gate

Correction of the two reporting-layer defects the Phase 4B documentation pass found, and the
control family whose absence let them survive.

The accounting engine was not touched. No source generation, mapping, ownership, FX,
elimination, PPA, NCI, PUP or consolidation journal changed, and every accounting figure is
byte-identical to the frozen build.

---

## P4-D-01 — the period result in equity · **CLOSED**

### Root cause

`rpt_balance_sheet` presented `Result for the period` as the cumulative balance of every income
statement account **including the year-end close**. The reasoning was that the close reverses
each year's result into reserves, so what remains is the result not yet closed.

That is true for layer 1 and false for the group. **No entity ledger closes a consolidation
adjustment**, because consolidation adjustments do not exist in any entity's books. So three
years of PPA amortisation, unrealised profit and NCI attribution accumulated in a caption
called "the period's result":

| At 31 December 2025 | USD m |
|---|---|
| Layer 1, after its own year-end close | (0.187) |
| Layer 3, which nothing closes | 20.055 |
| **Presented as "Result for the period"** | **19.869** |
| FY2025 net income attributable to the parent | **7.046** |

Total equity was correct throughout. The defect was entirely in how one correct total was split
across two captions, which is why no balancing control could see it.

### Correction

`Result for the period` is now the **fiscal year to date on the income statement's own basis**
— every income statement account for the current fiscal year, **excluding** the close. Whatever
else the cumulative income statement contains belongs to `Retained earnings`.

The two movements are computed so that they sum, by construction, to the whole income statement
movement for the period. The split moves; the total cannot.

```sql
result_movement(t)    = ytd(t) − ytd(t−1)          -- ytd restarts each fiscal year
retained_movement(t)  = all_is(t) − result_movement(t)
```

Excluding the close is what makes the caption mean one thing in every month. Including it made
the caption a different measure in December from the one it was in November, and it could never
agree with the income statement at a year end.

### Equity at 31 December 2025, before and after

| USD m | Before | After |
|---|---|---|
| Contributed capital | (168.600) | (168.600) |
| Retained earnings | 57.832 | **84.747** |
| Cumulative translation adjustment | (0.283) | (0.283) |
| Non-controlling interests | (2.158) | (2.158) |
| Result for the period | 19.869 | **(7.046)** |
| **Total equity** | **(93.340)** | **(93.340)** |

The result caption is now a credit of 7.046 — a profit of USD 7.046m, exactly the FY2025 net
income attributable to the parent.

### Acceptance

| | |
|---|---|
| Result caption vs the fact's fiscal year to date, all 48 months | worst **0.00** |
| Result caption vs `rpt_income_statement` at each of four year ends | exact, all four |
| Retained earnings + result vs the fact's cumulative earnings | worst **0.00** |
| Assets = liabilities + equity, all 48 months | **0.00** |
| Total equity moved | **no** |

Controls `P4-XAR-06` (the split) and `P4-XAR-07` (the total). Tests in
`tests/test_phase04c_reporting_integrity.py`.

---

## P4-D-02 — the EBITDA bridge · **CLOSED**

### Root cause, in two parts

**The close was not excluded.** `mgmt.ebitda_bridges()` read `vw_statutory_fact` without the
`counts_in_result` predicate, so each fiscal year was summed *including* the close that
reverses it. Three of four years netted to approximately nil. FY2026 was right only because it
carries no close.

**A nil `FILTER` voided the arithmetic.** `covenant_ebitda_usd` contained
`sum(amount_usd) FILTER (WHERE group_account IN ('740100','740200'))`. Those accounts are never
posted to, so the aggregate was NULL, and one NULL anywhere in the expression made the whole
result NULL. Every year's Covenant EBITDA — the measure a lender tests leverage on — came back
as no number at all.

### Correction

`counts_in_result` applied, exactly as `rpt_income_statement` does it, and every aggregate
coalesced where it is built. The EBITDA definitions themselves are unchanged.

| USD m | FY2023 | FY2024 | FY2025 | FY2026 |
|---|---|---|---|---|
| Statutory EBITDA — **before** | (0.535) | (0.083) | (0.095) | 29.202 |
| Statutory EBITDA — **after** | **28.705** | **38.891** | **51.250** | **29.202** |
| Approved add-backs | 9.800 | 8.200 | 6.500 | 3.810 |
| Layer-4 effect | — | — | — | — |
| **Adjusted EBITDA** | **38.505** | **47.091** | **57.750** | **33.013** |
| Sponsor fee cap effect (CA-027) | — | — | — | — |
| Unrealised FX add-back (CA-030) | — | — | — | — |
| **Covenant EBITDA — before** | **NULL** | **NULL** | **NULL** | **NULL** |
| **Covenant EBITDA — after** | **38.505** | **47.091** | **57.750** | **33.013** |

Statutory and Adjusted EBITDA now agree with `rpt_income_statement` exactly.

**Covenant EBITDA equals Adjusted EBITDA in this window, and that is a real result rather than
a shortcut.** The sponsor monitoring fee runs at 1.0 / 1.1 / 1.2 / 0.8 USD m against the CA-027
cap of 1.5m, so the cap does not bite — but it is computed from the agreement's own term rather
than assumed away, because it would bite at a higher fee. The CA-030 unrealised foreign
exchange add-back has **no population**: accounts 740100 and 740200 are never posted to by any
entity. **No adjustment row was fabricated to make the arithmetic non-null.**

---

## P4-D-03 — the layer bridge · **found by the new controls, CLOSED**

`P4-XAR-11` failed the first time it ran, by USD 13,952,275.26 — exactly FY2025's layer-1
close. `rpt_layer_bridge` had the same close defect, in a third artefact.

Its effect was worse than a wrong total: with the close included, layer 1's year netted to
approximately nil and the bridge showed the group's net income arriving almost entirely from
the consolidation layers. That is the opposite of the truth, in the one artefact whose job is
to say where a number came from.

Corrected the same way. FY2025 now reads:

| Layer | Net income, USD m |
|---|---|
| 1 REPORTED | 14.077 |
| 2 IC_ELIM | — |
| 3 CONSOL_ADJ | (7.297) |
| 5 FX_CTA | — |
| **Total** | **6.780** |

Three artefacts, one defect, none of it visible to any accounting control. That is the case for
the family.

---

## The cross-artefact control family — 11 new controls

> **Different artefacts expressing the same financial measure must reconcile to one
> authoritative definition.**

Every control has at least one side **recomputed from `fact_financials`**, and never both sides
from the same reporting calculation. A report agreeing with itself is not evidence.

| ID | Reconciles | Against | Tolerance |
|---|---|---|---|
| `P4-XAR-01` | `rpt_income_statement`: revenue, gross profit, EBITDA, EBIT, net income, net income attributable to the parent | the fact | 0.05 |
| `P4-XAR-02` | `rpt_ebitda_bridge` statutory EBITDA | the fact | 0.05 |
| `P4-XAR-03` | `rpt_ebitda_bridge` Adjusted EBITDA | the fact + add-backs + layer 4 | 0.05 |
| `P4-XAR-04` | Covenant EBITDA: completeness and value | non-null, and the fact + capped fee + FX | 0.05 |
| `P4-XAR-05` | `rpt_balance_sheet` total assets, liabilities, equity | the fact | 0.05 |
| `P4-XAR-06` | the period result caption | the fact's fiscal year to date | 0.05 |
| `P4-XAR-07` | retained earnings + the period result | the fact's cumulative earnings | 0.05 |
| `P4-XAR-08` | the CTA caption | the fact's translation accounts | 0.05 |
| `P4-XAR-09` | the NCI caption | `rpt_nci_rollforward` closing | 0.05 |
| `P4-XAR-10` | closing cash: cash flow, balance sheet and the fact | three-way | 0.05 |
| `P4-XAR-11` | `rpt_layer_bridge` net income | the fact | 0.05 |

All **BLOCKING**. A difference in a primary statement or a lender-facing measure is not an
informational warning.

`TOL_XAR_USD = 0.05` is a rounding allowance, not room for a difference: every line on each
side is already held at the cent, and each control reports the worst it actually measured. All
eleven measure **0.00**.

## The fault fixtures — 4 new, all detected by their own family

| Fixture | Injected | Detected by | Anything else? |
|---|---|---|---|
| `F4-XAR-01` | USD 5m moved between the period result and retained earnings; total equity untouched | `P4-XAR-06` | **nothing** |
| `F4-XAR-02` | statutory EBITDA recomputed including the close, income statement left correct | `P4-XAR-02` | nothing |
| `F4-XAR-03` | an empty add-back category left as NULL, voiding Covenant EBITDA | `P4-XAR-04` | nothing |
| `F4-XAR-04` | closing cash moved in the cash flow, the fact left correct | `P4-XAR-10` | `P4-CF-01`, `P4-CF-02` |

`F4-XAR-01` is the important row. It breaks the equity presentation while keeping the balance
sheet balanced, and **not one of the 61 accounting controls notices** — which is precisely what
P4-D-01 looked like for a whole phase.

These four are the deliberate exception to the harness's rule that a fault is injected into an
input and never into an output. The thing under test **is** the reporting layer: the fixtures
corrupt an artefact and leave the consolidated fact correct, so the accounting stays right
while the report goes wrong.

## The NULL policy

> **A component with no population contributes ZERO, never NULL.**

NULL means unknown or missing. An add-back category with nothing in it is not unknown — it is
zero, and saying so is a different statement from failing to compute it.

Enforced two ways. Every additive `FILTER` aggregate in `src/consol/` is coalesced where it is
built — 17 were not, and now are, across `nci.py`, `translate.py`, `statements.py` and
`controls.py`. And `test_no_additive_filter_aggregate_is_left_un_coalesced` fails the build if
one reappears.

This fault has now caused three defects in this project: gross profit and net income voided in
the income statement, an entity with cost and no revenue removing its own gross profit from the
group total, and Covenant EBITDA returning NULL in every year. It is worth a lint rule.

## Regression

| | |
|---|---|
| Phase 2 source controls | **80/80** |
| Phase 3 pipeline controls | **62/62** |
| Phase 3 fault sweep | **10/10** |
| Phase 4 consolidation controls | **72/72** (61 + 11 cross-artefact) |
| Phase 4 fault fixtures | **23/23**, 0 accidental detections |
| Tests | **436 passed** |
| Balance sheet | 0.00 in all 48 periods |
| Cash flow | ties at 0.00 in all 48; closing cash to the balance sheet 0.00 |
| CTA | **243/243** against the independent expectation |
| Intercompany | 2,355 relationship-periods, all matched |
| NCI roll-forward | unchanged |
| Source digest | `fd7afb8f…` **unchanged** |
| Consolidation build id | `78e406e139662392` **unchanged** — the engine's declared inputs did not move |
| Artefacts changed | `rpt_balance_sheet`, `rpt_ebitda_bridge`, `rpt_layer_bridge` only |
| Working tree after a full rebuild | clean |
