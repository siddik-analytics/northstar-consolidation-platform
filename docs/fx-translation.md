# FX translation, as built

How the engine translates twelve entity ledgers in four currencies into one USD group, and how
the cumulative translation adjustment is derived rather than plugged.

[`fx-cta-policy.md`](fx-cta-policy.md) is the **policy**: rules FX-P01 to FX-P19, approved in
Phase 1. This document is the **implementation**: what `src/consol/translate.py` and
`src/consol/cta.py` actually do, what was wrong before Phase 3.2, and why the corrected rule is
now enforced structurally rather than remembered.

---

## 1. Functional and reporting currency

| Entity | Functional | | Entity | Functional |
|---|---|---|---|---|
| NIG-100 Topco | USD | | NIG-320 | GBP |
| NIG-110 Shared Services | USD | | NIG-400 | USD |
| NIG-200 | USD | | NIG-410 Vector Systems | EUR |
| NIG-210 | CAD | | NIG-500 | USD |
| NIG-220 Halden Valve | EUR | | NIG-510 | GBP |
| NIG-300 | USD | | | |
| NIG-310 | CAD | | | |

The reporting currency is **USD**. Six entities are already in it; six are not, and only those
six generate a translation adjustment.

Each entity keeps its own books in its functional currency. The engine never converts a
transaction — it translates a *balance* or a *flow* at the rate the policy assigns to the
account.

## 2. The rate the engine applies is an account attribute

Translation is driven by `dim_account.fx_method`, not by a list of account numbers in code.
That is deliberate: a code list is a second chart of accounts that nobody maintains, and it
drifts. The chart says how each account translates and the engine obeys it.

| `fx_method` | Rate | Applies to | Policy |
|---|---|---|---|
| `AVG` | monthly average of the posting month | income statement | FX-P01 |
| `CLOSE` | closing spot at period end | assets and liabilities | FX-P02 |
| `HIST` | frozen at contribution or acquisition | contributed capital, APIC, share-based compensation reserve | FX-P03 |
| `ACCRUING_HISTORICAL` | the month's average | balances that build up at the rate they arose | — |
| `NONE` | not translated | statistical accounts | FX-P08 |

`P4-FX-03` proves no `HIST` account is ever translated at a closing rate. Retranslating
contributed capital would make CTA a plug rather than a residual **and the balance sheet would
still balance**, which is exactly why it needs its own control.

## 3. Balance sheet accounts translate as a movement, not a balance

A balance sheet account is a position, but `fact_financials` holds movements. So the engine
translates the **cumulative balance** at each month's closing rate and posts the **difference**
from the prior month's translated balance:

```
movement_usd(t) = balance_local(t) × close(t) − balance_local(t−1) × close(t−1)
```

which decomposes into the real activity and the translation of the opening balance:

```
                = Δbalance_local(t) × close(t)          the activity
                + balance_local(t−1) × (close(t) − close(t−1))   the translation
```

The second term is carried on the fact as `fx_revaluation_usd`. It is what makes the cash flow
able to separate the effect of exchange rates on cash from a real cash flow, and it is **not**
CTA — it is one account's share of the same arithmetic.

Two subtleties the engine handles and a naive implementation does not:

* **The dense spine starts when the entity does.** Halden Valve and Vector Systems join mid-window. A spine
  that started at 202301 would take the prior month's closing rate from a month in which the
  entity did not exist, and the first month's translation would be wrong. `entity_start`
  bounds it.
* **Opening balances are identified by their content, not by a document type.** Kestrel's
  extract carries no `source_event_type`, so opening journals are identified by
  `source_description = 'Opening balance brought forward'`. A rule that worked only for SAP
  document types 40 and 50 silently mistranslated an entire ERP's opening balance sheet.

## 4. Acquisition-date and opening balances

An entity's opening balance sheet is translated at the rate on its **consolidation effective
date** (FX-P16), registered per entity in `ref_fx_rate_historical` under
`group_account = 'ACQ_OPENING_BS'`. Retained earnings brought forward is never retranslated
(FX-P04); the current year's result in equity is the sum of the translated months (FX-P05).

`P4-FX-02` iterates the **entities**, not the rate table, so an entity with no registered
opening rate fails rather than quietly translating at whatever the join left behind.

### P3-D-05 — the defect that made this rule structural

`historical_rates()` selected the applicable rate with `period_key < 202301`. An entity whose
consolidation effective date is **1 January 2023** — the first day of the modelled window —
therefore matched nothing before the window and fell through to January's closing rate,
**1.23412**, instead of the FY2022 closing anchor, **1.2083**.

It was found by the consolidation engine, not by a source control: the opening balance sheet
still balanced, the trial balance still closed, and every Phase 2 and Phase 3 control passed.
Only the independently derived CTA expectation disagreed, for one entity, in one period —
242 of 243 entity-periods agreed and the 243rd did not.

The correction is in the generator, not in the engine
([Phase 3.2](phases/phase-03-2-report.md)):

```python
WINDOW_OPENS = date(2023, 1, 1)
...
if eff <= WINDOW_OPENS:        # was: if pk < 202301
```

The boundary is now **inclusive and expressed as a date**, so "on the first day" and "before
the window" are the same case, which is what the policy always meant. CTA agrees with the
expectation for **243 of 243** entity-periods, and the NCI share of translation reproduces the
FY2023 anchor exactly.

The general lesson is in the rule shape rather than the fix: a boundary written as `<` over an
integer period key cannot express "on the boundary", and the entity that sits exactly on it is
the one nobody tests.

## 5. CTA is derived, never plugged

CTA is the residual of the translated trial balance:

```
CTA movement(t) = − Σ over all accounts of translated movement(t)
```

Nothing chooses it. It is computed in `stg_cta_movement` for every entity-period (507 rows),
split between the group and the non-controlling interest at the entity's effective percentage,
and posted to layer 5 against accounts `330200` and `340400`.

There is **no CTA balancing account and no plug**. The evidence:

| Control | What it proves |
|---|---|
| `P4-LAY-02` | layers 1 and 5 together sum to zero in every period, to the cent |
| `P4-FX-04` | the derived CTA reproduces `ref_cta_expectation` for **243 of 243** entity-periods, worst difference **0.000001 USD m** |
| `P4-FX-05` | USD entities generate **zero** CTA — every rule gives the same answer at a rate of one |
| `P4-FX-06` | the roll-forward is continuous: each year's opening equals the prior year's closing |
| `P4-FX-07` | the NCI share is the entity's own percentage of its own movement |
| `P4-LAY-05` | no source ledger carries a CTA account — a source-layer CTA would be a plug the balance sheet would balance around |

`ref_cta_expectation` is the acceptance oracle. It was derived in Phase 2.2 from source
balances and rate movements, **before this engine existed**, and it is read by `P4-FX-04` and
by nothing that computes CTA. If the engine had used it as an input the comparison would be a
tautology.

FY2025 movement by entity, USD m — only the six non-USD entities appear:

| Entity | Opening | Movement | Closing |
|---|---|---|---|
| NIG-210 (CAD) | 0.154 | 0.069 | 0.223 |
| NIG-220 (EUR) | 0.834 | (2.853) | (2.019) |
| NIG-310 (CAD) | 0.687 | (0.517) | 0.170 |
| NIG-320 (GBP) | (0.263) | (0.378) | (0.641) |
| NIG-410 (EUR) | 0.010 | (1.086) | (1.075) |
| NIG-510 (GBP) | (0.257) | (0.295) | (0.552) |

## 6. Goodwill, intangibles and NCI

Goodwill and acquired intangibles arise in the **group's** presentation currency at the
acquisition-date rate and are not retranslated: they are group-level assets recognised on
consolidation, not balances in a foreign ledger. Their amortisation is a layer-3 posting in
USD.

The NCI's share of the translation adjustment is allocated at the entity's effective NCI
percentage and posted to `340400`, separately from the group's share. Allocating the whole
movement to group equity would overstate it and understate NCI by the same amount, and **total
equity would be unchanged** — so nothing but `P4-FX-07` would notice.

## 7. CTA is not the FX effect on cash

These are two different numbers and conflating them is a common, plausible and material error.

|  | Cumulative translation adjustment | FX effect on cash |
|---|---|---|
| What it is | the residual of translating the **whole** balance sheet | the retranslation of foreign-currency **cash balances** |
| Where it appears | equity, `330200` / `340400` | its own line in the cash flow, below financing |
| Cash effect | none | none — but it explains why cash moved without a flow |
| Scale here | (3.035) USD m cumulative | 0.100 / (0.199) / 0.244 USD m a year |

The cash flow states every line **net of its own translation**. The translation on cash becomes
`fx_effect_on_cash_usd`; the translation on everything else becomes `fx_non_cash_usd`, a
non-cash reconciling item inside operating activities — not a working capital swing, because no
cash moved there either.

Routing the whole translation movement through the cash line makes the statement tie perfectly
while reporting an implausible exchange effect on a mostly-USD cash balance. Every balancing
control still passes. `P4-FX-08` is the control that objects, and it objects specifically:
it requires both figures to be non-nil and the effect on cash to be the smaller of the two.

## 8. Fixtures

| Fixture | Injected into | Caught by |
|---|---|---|
| F4-05 equity retranslated at closing rate | `dim_account.fx_method` | `P4-FX-04` |
| F4-06 missing opening translation base | `ref_fx_rate_historical` | `P4-FX-02` |
| F4-07 opening rate 5% wrong | `ref_fx_rate_historical` | `P4-FX-04` |

F4-07 is the important one. A plausible but wrong rate translates cleanly, balances cleanly and
passes every structural control. Only the independent expectation disagrees — which is the
entire argument for having one.
