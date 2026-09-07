# FX Translation and CTA Policy

The complete foreign currency translation policy, including a deterministic CTA
roll-forward and the controls that will prove it once the consolidation engine exists.

Machine-readable policy: [`config/fx/fx_translation_policy.csv`](../config/fx/fx_translation_policy.csv)
(22 rules). Decision rationale: [ADR-0005](adr/0005-fx-translation-method.md).

**Scope.** Six of twelve operating entities have a functional currency other than USD: two
CAD (`NIG-210`, `NIG-310`), two GBP (`NIG-320`, `NIG-510`), two EUR (`NIG-220`, `NIG-410`).

---

## 1. Method and universal conventions

The group applies the **current rate method** to every foreign operation. Each entity's
functional currency is its local currency; no entity operates in a hyperinflationary economy,
so the temporal method is not in scope.

Three conventions apply everywhere and are enforced rather than assumed:

1. **Quotation direction.** Every rate is stored as **USD per one unit of foreign currency**,
   so translation is always a multiplication. Rates are validated on load against per-currency
   plausible bands (`CTL-FX-05`); an inverted EUR rate of 0.92 instead of 1.09 would understate
   a German entity by about 30% and is not visible in a summary review.
2. **Translate exactly once, from local currency.** Aurora's system-translated USD column and
   Kestrel's legacy EUR group-currency column are **ignored** (`CTL-FX-06`). Translating an
   already-translated amount produces a triangulated rate error that is close to impossible to
   find months later.
3. **Rate sets are versioned.** `ACTUAL`, `BUDGET` (locked at approval, never restated) and
   `FORECAST` (frozen at version issue).

## 2. Rate applied, by item

| # | Item | Rate | Basis |
|---|---|---|---|
| FX-P01 | **Income statement** | `AVG` | Monthly average of the **posting month** |
| FX-P02 | **Balance sheet — assets and liabilities** | `CLOSE` | Closing spot at period end |
| FX-P03 | **Equity — contributed capital, APIC, pre-acquisition reserves** | `HIST` | Rate at contribution or acquisition, frozen |
| FX-P04 | **Retained earnings — opening** | Derived | Prior period's closing USD balance; never retranslated |
| FX-P05 | **Current year result in equity** | Derived | Sum of monthly translated P&L |
| FX-P16 | **Acquisition-date opening balances** | `ACQ_DATE` | Spot rate on the consolidation effective date |
| FX-P17 | **CTA — opening** | Derived | Prior period's closing CTA |
| FX-P06 | **CTA — movement** | Derived | Computed residual for the period |
| FX-P18 | **CTA — closing** | Derived | Opening + movement + recycling |
| FX-P19 | **CTA — recycling on disposal** | `HIST` | Rate history of the disposed operation. Nil — no disposals in scope |
| FX-P20 | **NCI share of CTA movement** | Derived | NCI % of the entity's CTA movement |
| FX-P21 | **NCI result / dividends** | `AVG` / declaration-date rate | Mirrors the P&L / frozen when declared |
| FX-P07 | **NCI — opening** | Derived | Prior closing USD; never retranslated |
| FX-P08 | **Statistical accounts** | `NONE` | Not monetary, not translated |
| FX-P14 | **Cash and cash equivalents** | `CLOSE` | Movement presented separately in the cash flow |

### 2.1 Income statement — monthly average, never year-to-date average

Each month's income statement is translated at **that month's** average rate, and year-to-date
figures are the **sum of translated months**.

Applying a year-to-date average rate to a year-to-date balance gives a different — and wrong —
answer whenever activity is uneven across the year, which it always is in a business with
turnaround seasonality and project milestones. It would also make `CTL-FX-03` inexpressible,
because there would be no month-by-month identity left to test.

### 2.2 Equity — what is frozen and what is not

| Frozen at historical rates | Never retranslated (carried forward in USD) | Translated at closing |
|---|---|---|
| Common stock `310100` | Retained earnings opening `320100` | Nothing in equity |
| Additional paid-in capital `310200` | CTA opening `330100` | |
| Share-based comp reserve `315100` | NCI opening `340100` | |
| Pre-acquisition reserves | | |

The distinction matters. **Frozen** items keep the rate of their originating transaction
forever. **Carried forward** items keep whatever USD value they closed at last period. Neither
is retranslated, and if either were, CTA would stop being an arithmetic residual and become a
plug.

### 2.3 Acquisition-date balances

An acquired entity's opening balance sheet is translated at the **spot rate on its
consolidation effective date**. That translated equity becomes the frozen historical base for
FX-P03, and the entity's opening CTA is **nil** in its first consolidated period.

| Entity | Acquisition date | Currency |
|---|---|---|
| `NIG-220` Halden Valve GmbH | 2023-04-01 | EUR |
| `NIG-410` Vector Systems B.V. | 2024-07-01 | EUR |

**Goodwill and purchase-price-allocation intangibles are assets of the foreign operation.**
They are recorded in the entity's functional currency and translate at closing rates
thereafter, generating CTA like any other non-monetary asset. Holding foreign goodwill flat in
USD is a frequent error: it suppresses genuine CTA movement, and because the balance sheet
still balances, nothing else catches it. The FY2025 anchor shows $1.9m of translation movement
on goodwill alone. Enforced by `CTL-FX-10`.

## 3. The CTA roll-forward

CTA is the arithmetic consequence of translating assets and liabilities at closing rates while
equity is translated at historical and derived rates. It is **computed, never entered**.

### 3.1 Definition

```
CTA closing  =  CTA opening  (330100, prior period's closing)
             +  CTA movement (330200, computed residual for the period)
             +  CTA recycled on disposal (330300, nil while no disposal is in scope)
```

The movement itself is the residual that makes the translated trial balance sum to zero:

```
CTA movement = (assets − liabilities) at closing rates
             − (equity excluding CTA) at historical and derived rates
             − CTA opening
```

Split by owner:

```
CTA movement (group)  →  330200   ownership %   of each entity's movement
CTA movement (NCI)    →  340400   NCI %         of each entity's movement
```

### 3.2 Independent verification

The engine's CTA is compared against an expectation derived from a completely different
route — rate movements applied to balances, rather than a balancing residual:

```
Expected CTA movement ≈  opening net assets × (closing rate − prior closing rate)
                      +  current year result × (closing rate − average rate)
                      +  capital movements × (closing rate − transaction rate)
```

Variance above **0.5%** of the movement is a warning; above **2%** is blocking (`CTL-FX-04`).

This is the control that makes plugging impossible. A hand-plugged CTA balances the balance
sheet perfectly and is therefore invisible to every other control in the framework — the
statements tie, eliminations net, the trial balance is zero. Only an independent recomputation
finds it.

### 3.3 Continuity

Closing CTA of each period is the opening CTA of the next, per entity, with **no unexplained
step** (`CTL-FX-09`). A discontinuity means either that a closed period has been restated or
that the engine recomputed CTA from scratch instead of rolling it forward. Both are defects,
and both are silent without this control.

### 3.4 Group anchor roll-forward

Generated by the anchor model; the engine must land near these in Phase 4
([`config/anchors/anchor_cta_rollforward.csv`](../config/anchors/anchor_cta_rollforward.csv)).

| USD m | FY2023A | FY2024A | FY2025A | FY2026B | FY2026F |
|---|---|---|---|---|---|
| CTA — opening | (3.50) | — | (5.30) | 3.50 | 3.50 |
| CTA — movement, group | 3.50 | (5.30) | 8.80 | — | 1.00 |
| CTA — recycled on disposal | — | — | — | — | — |
| **CTA — closing (group)** | **—** | **(5.30)** | **3.50** | **3.50** | **4.50** |
| Memo: movement attributable to NCI | 0.10 | (0.05) | 0.18 | — | 0.05 |
| **Total translation movement** | **3.60** | **(5.35)** | **8.98** | **—** | **1.05** |

Decomposed by the balance it arises on:

| USD m | FY2023A | FY2024A | FY2025A | FY2026B | FY2026F |
|---|---|---|---|---|---|
| on cash and cash equivalents | 0.20 | (0.30) | 0.40 | — | 0.20 |
| on property, plant and equipment | 0.60 | (0.90) | 1.10 | — | 0.90 |
| on goodwill | 0.80 | (1.20) | 1.90 | — | 1.00 |
| on intangible assets | 0.40 | (0.70) | 0.90 | — | 0.50 |
| on working capital and other balances | 1.60 | (2.25) | 4.68 | — | (1.55) |
| **Total** | **3.60** | **(5.35)** | **8.98** | **—** | **1.05** |

The decomposition sums to the total by assertion in the anchor model, and it is what routes
the FX effect correctly through the cash flow statement (§4).

FY2026 **Budget** shows a nil movement because the budget is translated at locked budget rates
and is never restated (FX-P09) — there is no rate change within the budget to generate one.
Budget and Forecast both open from the FY2025 actual close of $3.50m.

### 3.5 Status of the anchor CTA

At Phase 1 the CTA movement is an **economic input** to the anchor model, estimated from rate
movements on foreign net assets. In Phase 4 it becomes a **computed output** of the translation
engine, and `CTL-FX-04` compares the two.

This is correct sequencing — a translation engine cannot run before entity-level data exists —
but the distinction is stated plainly: the anchor CTA is a **target, not a proof**. The policy
above is fully specified and binding on Phase 4 regardless.

## 4. FX in the cash flow statement

The translation effect appears in **two places**, and conflating them was a real defect
corrected in Phase 1:

| Component | Presentation | FY2025 anchor |
|---|---|---|
| Translation on foreign-currency **cash** | "Effect of exchange rate changes on cash and cash equivalents", below financing | $0.40m |
| Translation on **all other** foreign-currency balances | Non-cash reconciling item **within operating activities** | $4.68m |

The second component is what accounting standards describe as "changes in operating assets and
liabilities, net of the effect of foreign currency translation". It is not a working capital
movement — no cash moved — and it must be excluded from the working capital lines or those
lines report swings that never happened.

Routing the whole CTA movement through the cash line makes the statement **still tie** while
reporting an implausible FX effect on cash — $5.08m on a $22m cash balance that is mostly USD.
Every balancing control passed; only plausibility review caught it. `CTL-FX-11` now tests the
split explicitly.

Translation effects on PP&E, goodwill and intangibles do not appear in the cash flow statement
at all. They are non-cash movements in non-current assets, already excluded from investing
because investing shows **cash** capital expenditure.

## 5. Scenario rate sets and constant currency

| Rate set | Scenario | Behaviour |
|---|---|---|
| `ACTUAL` | Actual | Actual monthly average and closing rates |
| `BUDGET` | Budget | Locked at approval. **Never restated** (`CTL-FX-07`) |
| `FORECAST` | Forecast | Actual rates for closed months, forwards for open months, frozen at version issue |

The budget is never retranslated because restating it destroys accountability: a manager
cannot be held to a target that moved after it was agreed. FX is isolated instead through the
constant-currency view.

**Constant currency** (`amount_usd_cc`) holds actual local amounts translated at **budget**
rates, stored as a third amount column rather than computed at query time.

```
FX impact = amount_usd − amount_usd_cc
```

FY2026 demonstrates why this is not optional. The budget was locked at EUR 1.0900 / GBP 1.2900;
the forecast assumes EUR 1.1600 / GBP 1.3450. On a constant-currency basis revenue is **$16.9m
behind budget**, but reported revenue is only $10.8m behind — translation flatters the
shortfall by $6.1m, more than half of it. Reporting the variance without separating that would
credit management with performance FX delivered.

## 6. Intercompany translation

| Rule | Treatment |
|---|---|
| FX-P12 | Both sides of an intercompany **balance** translate at the same closing rate, so a single-currency pair eliminates exactly |
| FX-P13 | Seller income and buyer expense translate at the same **monthly average** rate, so the P&L elimination nets to nil in USD as well as in local currency |

Where the two entities record a balance in **different** currencies — the GBP-denominated
`NIG-320` receivable against EUR-functional `NIG-410`, or the EUR and GBP intercompany loans
from a USD-functional `NIG-100` — a residual arises. That residual is a **genuine FX gain or
loss**, posted to `740100`, not absorbed into the elimination. The design must not "fix" it:
the lender really does carry a translation exposure on a EUR 24m loan.

Timing differences are different again. If one side records in March and the other in April,
the elimination does not net, and that is a **cut-off finding** reported by `CTL-IC-02`, not
noise to be absorbed into a tolerance.

## 7. Control summary

| Control | Severity | Tests |
|---|---|---|
| `CTL-FX-01` | Blocking | Rate completeness for every currency, period, type and rate set |
| `CTL-FX-02` | Warning | Rate reasonableness — within 10% month on month |
| `CTL-FX-03` | Blocking | Sum of monthly translated P&L = movement in the current-year result |
| `CTL-FX-04` | Blocking | CTA agrees with the independent expectation (0.5% warn / 2% block) |
| `CTL-FX-05` | Blocking | Quotation direction — USD per unit, within plausible bands |
| `CTL-FX-06` | Blocking | Source-system translated columns never read |
| `CTL-FX-07` | Blocking | Budget rates frozen once locked |
| `CTL-FX-08` | Warning | Constant currency reconciles to the FX line in the bridges |
| `CTL-FX-09` | Blocking | CTA roll-forward closes and is continuous across periods |
| `CTL-FX-10` | Blocking | Acquisition-date translation base; foreign goodwill translated, not held flat |
| `CTL-FX-11` | Blocking | Cash flow FX effect split correctly between cash and non-cash |
| `CTL-TB-03` | Blocking | Translated trial balance sums to zero once CTA is posted |
| `CTL-CON-11` | Blocking | NCI share of the CTA movement allocated correctly |

## 8. Phase 2 requirements

1. A **monthly** rate series for every currency and rate set, calibrated so the
   revenue-weighted monthly average reproduces the annual anchor within 10 basis points.
2. **Acquisition-date spot rates** for 2023-04-01 and 2024-07-01 (EUR).
3. **Historical rates** for every equity contribution event, keyed on entity, account and date.
4. Rates stored **only** as USD per unit — the generator must not emit an inverted pair.
5. Budget rates emitted as a distinct, locked rate set, not derived from actuals.
6. Forecast rates emitted per forecast version, with actual rates for that version's closed
   months.
