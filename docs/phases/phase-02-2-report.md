# Phase 2.2 Report — Source-Layer Integrity Pass

> **Superseded in part by Phase 3.1.** Every architectural decision in this report stands:
> there is no measurement reserve, the CTA is derived from source balances (ADR-0017) and the
> revolver charge is priced off a daily utilisation model (ADR-0018). What has moved is the
> **value** of two of the three derived inputs. Phase 3.1 corrected four source defects, one
> of which changed the intra-year intercompany positions; cash is the residual of the balanced
> entity journals, so the group's liquidity path moved and with it the revolver drawn against
> it. Average daily drawn falls from 17.318 / 26.347 / 22.820 to **14.829 / 23.902 / 22.099**,
> and the CTA movement moves in the sixth decimal. Every figure quoted below is the Phase 2.2
> figure; the restated figures and the causal chain are in
> [`phase-03-1-report.md`](phase-03-1-report.md) §10, and the evidence that nothing else moved
> is `data/phase03_1_source_diff.json`.


**Status:** Complete · **Date:** 2026-09-07 · **Next gate:** Phase 3 approval

The two architecture issues left open at the Phase 2.1 gate, settled before the source data is
frozen. No ingestion, mapping, consolidation or reporting work was started.

---

## 1. Summary

| # | Issue raised | Outcome |
|---|---|---|
| 1 | The group reporting measurement reserve is not acceptable as a permanent source-layer design | ✅ **Removed, not relocated.** The cause was found: the Phase 2 anchor bridge derived a layer-1 target for every asset, liability and income statement line but not for equity. Deriving it, and holding contributed capital at historical rates so a translation adjustment can actually arise, closes the layer-1 balance sheet with nothing added to any ledger. The residual is nil, not small |
| 2 | The generated revolver path does not support the anchor's average-drawn assumption | ✅ **Assumption superseded, with the mechanics rebuilt.** Utilisation is resolved to a daily balance on the dates the credit agreement and treasury policy fix, and the average-drawn anchor is derived from it. The old assumption was contradicted by the facility's own roll-forward before any generated data was consulted |

**Tests: 284 → 317.** **Source controls: 69 → 77.** **Control register: 81 → 84.**
**ADRs: 16 → 18 (one superseded).** **Group accounts: 189 → 188.**

Three further defects were found because of this pass rather than being on the list, and all
three are fixed: share-based compensation left the group as cash; the sponsor equity
contribution that funded an April acquisition arrived a twelfth at a time; and `build_actuals`
was stateful, so the debt schedule disagreed with the general ledger it described.

**Two anchors were narrowly revised, both with a derivation and both quantified in §6:** the
cumulative translation adjustment, and the revolver's average drawn balance. Revenue, gross
profit, opex, EBITDA, Adjusted EBITDA, D&A, EBIT, cash, total assets, term debt, goodwill,
intangibles and every working-capital caption are **unchanged**, and no covenant is breached
in any period.

---

## 2. The measurement reserve

### 2.1 What was actually wrong

`329100 Group reporting measurement reserve` was disclosed, capped and destined to be
discarded. The reviewer's objection was that a real source ERP does not contain an account
whose purpose is to make a synthetic group reporting model reconcile. That is right, and the
investigation found the objection understated the problem: **the reserve was not the least-bad
home for an unavoidable residual. There was no residual.**

Phase 2's anchor bridge (`src/generation/targets.py`) derives, from the approved consolidated
anchors, what the sum of the source ledgers must say — the intercompany gross-up on revenue,
receivables and payables, and the exclusion of goodwill, acquired intangibles, their deferred
tax and unrealised intercompany profit. It covered **every asset, every liability and every
income statement line, and not equity.**

A balance sheet with a target for everything except equity has one free variable. A generator
will always close a free variable with whatever is left over. Phase 2.0 left it in investment
at cost, which made investment balances unexplainable. Phase 2.1 named it, capped it and
disclosed it. Both are the same defect.

Underneath that sat a second one. Contributed capital was carried at a **closing-rate USD
target recomputed every year**, so Halden Valve's share capital moved in euros whenever
EUR/USD moved. Under the closing-rate method the cumulative translation adjustment *is* the
difference between net assets at closing rates and capital at historical rates plus results at
the rates when earned. With nothing frozen at a historical rate, the entity ledgers could
generate almost no translation adjustment at all — $(0.78)m, $0.22m and $(0.35)m across three
years, against a group CTA target of $3.5m, $(5.3)m and $8.8m. The difference had nowhere to
go except the reserve.

### 2.2 What was done

**Removed**

| Removed | Where |
|---|---|
| `329100 Group reporting measurement reserve` | `config/coa/group_coa.csv` |
| `AURORA 3250 Group Reporting Measurement Reserve` | `config/coa/source_coa_aurora.csv` |
| Its row in the expected mapping manifest | `config/generation/expected_mapping_manifest.csv` |
| `SeriesBuilder.apply_measurement_reserve` | `src/generation/series.py` |
| `P2-RES-01` (reserve materiality cap), `P2-RES-02` (cash carries none of it) | `src/generation/validate.py` |
| `data/reference/translation_difference.csv` | replaced by three derived datasets |
| ADR-0016 | retired to **Superseded**, with the reason recorded |

**Added — the layer-1 equity bridge**

```
layer-1 equity = consolidated total equity
               + investment in subsidiaries, at cost
               - goodwill
               - acquired intangibles, net
               + deferred tax on the purchase price allocation
               + unrealised intercompany profit in inventory
```

Consolidation replaces each subsidiary's equity with the parent's investment in it, recognises
the goodwill and intangibles that investment bought, provides deferred tax on those
intangibles and eliminates the profit sitting in intercompany stock. Reverse those four and
the consolidated equity becomes the layer-1 equity.

The identity holds **exactly at the 31 December 2022 opening balance sheet**, before a single
generated period — $303.400m derived, $303.400m in the generated opening ledgers, difference
$0.000m. That is how it was established as the right bridge rather than a fitted one, and it
is now a published row of `config/anchors/phase02_source_layer_targets.csv`.

**Fixed — equity at source**

- **Contributed capital is a historical-rate balance** (FX-P03). `310100`, `310200` and
  `315100` are fixed amounts in each entity's own currency, struck at the rate ruling when they
  were contributed, and they move only when capital actually moves. `P2-FX-01` tests it entity
  by entity and month by month.
- **Every equity movement is a dated event**, in the new register
  `src/generation/ledger.py::EQUITY_EVENTS`: the $20.0m sponsor contribution arrives on
  1 April 2023, the day the Halden consideration was paid; distributions to the minority
  shareholder of Northstar Parts UK leave on the dates declared.
- **Share-based compensation is settled in equity.** The charge accretes in `315100` at the
  granting entity. Phase 2.1 expensed it and let the credit clear to cash — a non-cash charge
  leaving the group as cash. The reserve now stands at $1.0m, $2.2m and $3.6m, exactly the
  anchored cumulative charge. The generated charge is also now set to the anchor and the
  remaining recurring cost mix normalised around it, because the anchored contributed capital
  grows by that amount every year.
- **A distribution to the non-controlling shareholder actually leaves the group.** The anchor
  cash flow reports one; no source entity used to pay it. Only the distribution that leaves the
  group is modelled — a distribution to the parent is an intra-group transfer that eliminates
  in full and moves no reported figure.

### 2.3 The result

The layer-1 equity roll-forward now closes on its own arithmetic, published as
`data/reference/layer1_equity_bridge.csv`:

| USD m | FY2023 | FY2024 | FY2025 |
|---|---|---|---|
| Opening equity, at closing rates | 303.400 | 336.834 | 351.794 |
| Result for the year, at the rates when earned | (0.904) | 5.715 | 14.037 |
| Share-based compensation | 1.000 | 1.200 | 1.400 |
| Capital contributed, at the contribution-date rate | 20.000 | — | — |
| Equity brought in on acquisition | 11.800 | 10.900 | — |
| Distributions, at the payment-date rate | — | (0.150) | (0.200) |
| **Cumulative translation adjustment (computed)** | **1.538** | **(2.705)** | **5.062** |
| **Closing equity, rolled forward** | **336.834** | **351.794** | **372.093** |
| Closing equity, per the generated ledgers | 336.834 | 351.794 | 372.093 |
| **Unexplained** | **0.000** | **0.000** | **0.000** |
| Anchor-derived layer-1 equity target | 336.834 | 351.794 | 372.093 |
| **Variance vs the anchor** | **0.000** | **0.000** | **0.000** |

And layer-1 cash lands on the approved anchor with nothing added to any ledger:

| USD m | FY2023 | FY2024 | FY2025 |
|---|---|---|---|
| Layer-1 cash, re-derived from the journal lines | 15.000 | 15.000 | 22.000 |
| Anchor | 15.000 | 15.000 | 22.000 |
| **Variance** | **0.000** | **0.000** | **0.000** |
| Measurement reserve | **—** | **—** | **—** |

---

## 3. The CTA architecture

### 3.1 Where CTA lives

CTA belongs to **layer 5 — FX_CTA** and is produced by the translation engine from actual
source balances and the approved FX policy. Nothing in Phase 2 creates it, and no source
ledger carries a CTA account, because a local ledger has none.

What Phase 2 now produces is the **expectation** that engine will be tested against.
`data/reference/cta_expectation.csv` carries 243 rows — one per foreign entity per month:

```
CTA movement = opening net assets    x (closing rate - prior closing rate)
             + result for the period x (closing rate - average rate)
             + equity movements      x (closing rate - transaction rate)
```

Every term is a balance in the entity's own ledger or a rate in the approved rate file.
Nothing references a group target, which is the whole point: an engine compared against a
figure derived from its own output is not being tested. `P2-FX-03` recomputes every row from
the three balances and three rates it carries.

The architecture can now explain the full path end to end:

```
local entity balances   →   FX translation   →   computed CTA   →   consolidated balance sheet
(cta_expectation.csv)       (closing / average / historical, per FX-P03)      (no residual)
```

`CTL-FX-12` is added to the control register to enforce it at Phase 5, and `CTL-CON-14`
prohibits a residual or balancing account in any layer, written against the *idea* rather than
one retired account number.

### 3.2 The bridge from layer 1 to the group

```
CTA(group) = CTA(layer 1)
           + FX on goodwill + FX on acquired intangibles     (layer-3 balances)
           - the non-controlling interest's share
           - the movement in unrealised intercompany profit
```

Published as `data/reference/cta_group_bridge.csv`:

| USD m | FY2023 | FY2024 | FY2025 |
|---|---|---|---|
| Layer-1 CTA movement, from the source ledgers | 1.538 | (2.705) | 5.062 |
| FX on goodwill | 0.800 | (1.200) | 1.900 |
| FX on acquired intangibles | 0.400 | (0.700) | 0.900 |
| Less: the non-controlling interest's share | (0.071) | 0.019 | (0.059) |
| Less: movement in unrealised intercompany profit | (0.060) | (0.080) | (0.060) |
| **Derived group CTA movement** | **2.607** | **(4.666)** | **7.743** |
| Anchored group CTA movement | 2.607 | (4.666) | 7.743 |
| **Derivation variance** | **0.000** | **0.000** | **0.000** |

Goodwill and acquired intangibles are the only components still carried as estimates, because
they exist in no source ledger. Everything else is computed.

---

## 4. The CTA anchor revision

Phase 1.1 recorded that the CTA remained a *target rather than a proof* until a translation
engine existed. Phase 2 produced the entity ledgers that let the target be tested; it failed.
The independently generated source ledgers prove a different value, so the provisional target
is superseded.

### 4.1 Exact amounts

| CTA movement attributable to the group, USD m | FY2023 | FY2024 | FY2025 | FY2026F |
|---|---|---|---|---|
| Phase 1 provisional target | 3.500 | (5.300) | 8.800 | 1.000 |
| **Phase 2.2 derived** | **2.607** | **(4.666)** | **7.743** | **1.000** |
| **Change** | **(0.893)** | **0.634** | **(1.057)** | — |

| Closing CTA balance, USD m | FY2023 | FY2024 | FY2025 | FY2026F |
|---|---|---|---|---|
| Phase 1 | — | (5.300) | 3.500 | 4.500 |
| **Phase 2.2** | **(0.893)** | **(5.559)** | **2.184** | **3.184** |
| **Change** | **(0.893)** | **(0.259)** | **(1.316)** | **(1.316)** |

The minority's share of the translation movement is derived on the same basis — 20% of the
adjustment arising in NIG-510 — and moves from 0.100 / (0.050) / 0.180 to
**0.071 / (0.019) / 0.059**, so the group's non-controlling interest balance falls by $0.029m,
rises by $0.001m and falls by $0.120m.

The roll-forward still articulates exactly: opening plus movement plus recycling equals
closing, in every period, and the decomposition by balance category still sums to the total
translation movement (both asserted inside the anchor model).

### 4.2 How the balance sheet rebalances

Total equity falls by the cumulative change. Cash is fixed by treasury policy at every year
end (\$15.0m, \$15.0m, \$22.0m), so the counterpart is the **revolving credit facility** — the
only uncommitted line left in the anchor's closing identity, and the one the model already
uses to absorb the treasury sweep.

| USD m | FY2023 | FY2024 | FY2025 |
|---|---|---|---|
| Change in CTA (cumulative) | (0.893) | (0.259) | (1.316) |
| Change in non-controlling interests | (0.029) | 0.001 | (0.120) |
| Change in retained earnings — from §5, not from the CTA | (0.178) | (0.761) | (1.761) |
| **Change in total equity** | **(1.100)** | **(1.019)** | **(3.197)** |
| **Change in the revolving facility** | **+1.100** | **+1.019** | **+3.197** |
| Change in total assets | — | — | — |
| Change in cash | — | — | — |

Of the movement in the revolver, **\$0.922m, \$0.249m and \$1.448m is attributable to the CTA
revision** and the remainder to the interest revision in §5. Both are shown together because
they land on the same line.

`test_the_balance_sheet_still_balances_after_the_revision` asserts, for all five periods, that
total assets equal total liabilities and equity, and that total equity equals contributed
capital plus retained earnings plus CTA plus NCI.

---

## 5. Revolver utilisation and interest

### 5.1 The assumption was a defect, not a difference of opinion

Phase 1 priced the facility off an average drawn balance of **\$15.0m / \$12.0m / \$5.0m**.
The facility's own balance sheet roll-forward is **\$8.0m → \$15.1m → \$23.8m → \$16.3m**.

An average of \$5.0m across FY2025 requires the group to repay \$23.8m in January, hold near
nil for ten months and redraw \$16.3m in December — while its own treasury policy holds a
minimum cash balance of \$15.0m and the generated pre-facility cash position is negative in
most months of the year. No liquidity profile produces those endpoints and that average. The
defect is provable from the anchor model alone, before any generated data is consulted.

A second problem sat underneath. `RCF_RATE` was an asserted blended rate of
9.25% / 9.35% / 8.35%. Backing the \$100m swap out of the approved term-loan rates gives a
SOFR path of 4.70% / 5.20% / 4.10%, which implies a revolver margin of 455bps / 415bps /
425bps — a margin that moved every year, which no credit agreement does.

### 5.2 The methodology

**Treasury policy became shared configuration.** `config/debt/treasury_policy.csv` (11
parameters) holds the year-end minimum and target cash balances, the intra-year operating floor
and headroom, the borrowing-notice increment, the repayment block, the minimum surplus before
repaying, the two dates on which the facility moves, and the interest and fee bases. The anchor
model and the source generator both read it.

**Interest is built from its components**, each traceable to a clause:

| Component | Clause | FY2023 | FY2024 | FY2025 |
|---|---|---|---|---|
| Base rate (average SOFR fixing) | economic input | 4.70% | 5.20% | 4.10% |
| Revolver margin | CA-033 (new) | 4.25% | 4.25% | 4.25% |
| **Revolver rate** | derived | **8.95%** | **9.45%** | **8.35%** |
| Term loan margin | CA-003 | 4.25% | 4.25% | 4.25% |
| Swap: \$100m notional at 3.00% fixed | CA-008, CA-034, CA-035 (new) | | | |
| **Term loan blended rate** | derived | **8.10%** | **8.35%** | **7.80%** |
| Commitment fee on the undrawn commitment | CA-007 | 0.50% | 0.50% | 0.50% |

The derived term-loan rates reproduce the previously approved 8.10% / 8.35% / 7.80%
**exactly**, so no term-loan interest moves. The SOFR path is the one those rates always
implied, now made explicit.

**Utilisation is resolved to a daily balance.** A month-end balance cannot price a facility.
The intra-month position follows the dates already fixed in the agreement and the board policy:
a drawing is taken on the **borrowing-notice date (day 3)**, because it funds the supplier
payment run and the payroll disbursement; a repayment is made on the **collections sweep date
(day 25)**, once the month's receipts have cleared. The balance is a step function with one
step, so the average daily balance is exact rather than approximated.

`data/reference/revolver_utilisation.csv` publishes all 44 months. The debt schedule now reads
Topco's balances from the ledger instead of interpolating between year ends.

**The average-drawn anchor is derived, not asserted.** `tools/derive_anchor_inputs.py`
computes it from the utilisation model and iterates to a fixed point, because a higher drawn
balance costs interest, which reduces retained earnings, which the facility funds. It converges
in five iterations, and `--check` runs as a test so it cannot go stale. **FY2026 Budget is
deliberately not refitted** — a budget is struck before the year and is not restated by
outturn.

### 5.3 Reconciliation by year

Both identities hold to the cent:

| USD m | FY2023 | FY2024 | FY2025 | FY2026 (8m) |
|---|---|---|---|---|
| Opening drawn | 8.000 | 16.237 | 24.867 | 19.518 |
| Drawings | 25.500 | 27.500 | 37.151 | 27.000 |
| Repayments | (17.263) | (18.870) | (42.500) | (24.518) |
| **Closing drawn** | **16.237** | **24.867** | **19.518** | **22.000** |
| **Average daily drawn** | **17.318** | **26.347** | **22.820** | **15.403** |
| Average daily undrawn (of the \$60.0m commitment) | 42.682 | 33.653 | 37.180 | 44.597 |
| Applicable rate (SOFR + 425bps) | 8.95% | 9.45% | 8.35% | 7.65% |
| Interest: average daily drawn × rate | 1.550 | 2.490 | 1.905 | 1.178 |
| Commitment fee: average daily undrawn × 50bps | 0.213 | 0.168 | 0.186 | 0.223 |
| **Total facility charge supported** | **1.763** | **2.658** | **2.091** | **1.401** |
| **Recorded facility charge** | **1.763** | **2.658** | **2.091** | **1.401** |
| **Variance** | **0.0000** | **0.0000** | **(0.0000)** | **0.0000** |

Peak drawn balance across the 44 months is \$36.2m against the \$60.0m commitment; minimum
headroom is \$23.8m.

### 5.4 The average-drawn revision

| Average daily drawn, USD m | FY2023 | FY2024 | FY2025 | FY2026B | FY2026F |
|---|---|---|---|---|---|
| Phase 1 treasury forecast | 15.000 | 12.000 | 5.000 | 2.000 | 6.000 |
| **Phase 2.2 derived** | **17.318** | **26.347** | **22.820** | 2.000 | **15.403** |
| Change | +2.318 | +14.347 | +17.820 | — | +9.403 |

---

## 6. Financial anchor changes — every one, quantified

Adjusted EBITDA is untouched, so every leverage covenant's denominator is untouched.

### 6.1 Income statement (USD m)

| | FY2023 | FY2024 | FY2025 | FY2026F |
|---|---|---|---|---|
| Revenue, gross profit, opex, EBITDA, Adjusted EBITDA, D&A, EBIT | **unchanged** | **unchanged** | **unchanged** | **unchanged** |
| Interest — revolving facility, was | 1.388 | 1.122 | 0.418 | 0.477 |
| Interest — revolving facility, now | 1.550 | 2.490 | 1.905 | 1.178 |
| Commitment and agency fees, was | 0.225 | 0.240 | 0.275 | 0.270 |
| Commitment and agency fees, now | 0.213 | 0.168 | 0.186 | 0.223 |
| Interest — term loan, leases, DFF, interest income | **unchanged** | **unchanged** | **unchanged** | **unchanged** |
| **Net interest, was** | 18.284 | 20.689 | 19.647 | 18.703 |
| **Net interest, now** | **18.435** | **21.985** | **21.046** | **19.358** |
| **Change** | **+0.151** | **+1.296** | **+1.399** | **+0.654** |
| Profit before tax, was | (4.344) | 0.885 | 13.198 | 15.490 |
| **Profit before tax, now** | **(4.495)** | **(0.411)** | **11.799** | **14.836** |
| Income tax expense/(benefit), was | 0.782 | 0.487 | 3.762 | 4.260 |
| **Income tax expense/(benefit), now** | **0.809** | **(0.226)** | **3.363** | **4.080** |
| Net income, was | (5.126) | 0.398 | 9.437 | 11.231 |
| **Net income, now** | **(5.304)** | **(0.185)** | **8.437** | **10.756** |
| **Change** | **(0.178)** | **(0.583)** | **(1.000)** | **(0.474)** |

FY2024 moves from a \$0.40m profit to a \$0.19m loss. The business narrative — integration
spend against peak interest rates, a year close to break-even — is unchanged; the year now sits
just below the line rather than just above it.

**One observation, disclosed and not acted on.** The FY2024 effective tax rate anchor of 55%
was struck against a small positive profit before tax and now applies to a small loss, so the
charge presents as a \$0.23m benefit where FY2023 shows an expense on a loss. The rate is an
approved anchor, the arithmetic is internally consistent, and changing it would move net income
further for no derivable reason — so it was left alone. Phase 1's effective-rate scope decision
(OQ-05) is the right place to revisit it if the reviewer wants it revisited.

### 6.2 Balance sheet (USD m)

| | FY2023 | FY2024 | FY2025 | FY2026F |
|---|---|---|---|---|
| Cash, receivables, inventory, payables, accruals, prepaid, PP&E, right-of-use, goodwill, intangibles, deferred tax, other, **total assets**, term loan gross and net, finance and operating leases | **all unchanged** | | | |
| Revolving credit facility, was | 15.137 | 23.848 | 16.321 | 11.423 |
| **Revolving credit facility, now** | **16.237** | **24.867** | **19.518** | **15.127** |
| Total liabilities, change | +1.100 | +1.019 | +3.197 | +3.704 |
| Contributed capital | **unchanged** | **unchanged** | **unchanged** | **unchanged** |
| Retained earnings, change | (0.178) | (0.761) | (1.761) | (2.236) |
| Cumulative translation adjustment, change | (0.893) | (0.259) | (1.316) | (1.316) |
| Non-controlling interests, change | (0.029) | +0.001 | (0.120) | (0.153) |
| **Total equity, change** | **(1.100)** | **(1.019)** | **(3.197)** | **(3.704)** |
| **Total liabilities and equity, change** | **—** | **—** | **—** | **—** |

### 6.3 Cash flow (USD m)

| | FY2023 | FY2024 | FY2025 | FY2026F |
|---|---|---|---|---|
| Net income, change | (0.178) | (0.583) | (1.000) | (0.474) |
| Non-cash FX movement on working capital, change | (0.922) | +0.665 | (1.178) | (0.033) |
| **Operating cash flow, change** | **(1.100)** | **+0.081** | **(2.178)** | **(0.507)** |
| Capital expenditure, acquisitions, term loan movements, leases, financing fees, equity | **unchanged** | | | |
| Revolving facility movement, change | +1.100 | (0.081) | +2.178 | +0.507 |
| **Financing cash flow, change** | **+1.100** | **(0.081)** | **+2.178** | **+0.507** |
| **Net change in cash** | **unchanged** | **unchanged** | **unchanged** | **unchanged** |
| Free cash flow, was | 1.845 | 5.088 | 18.545 | 9.256 |
| **Free cash flow, now** | **0.744** | **5.170** | **16.367** | **8.748** |

The indirect cash flow still ties to balance sheet cash to the cent — asserted inside the
anchor model, and cash itself is unchanged in every period.

### 6.4 Leverage, coverage and covenants

| | FY2023 | FY2024 | FY2025 | FY2026B | FY2026F |
|---|---|---|---|---|---|
| Adjusted EBITDA | **unchanged** | **unchanged** | **unchanged** | **unchanged** | **unchanged** |
| Net debt, was | 211.605 | 248.117 | 231.772 | 209.900 | 225.066 |
| **Net debt, now** | **212.706** | **249.136** | **234.969** | **213.090** | **228.770** |
| Net leverage, was | 5.420x | 5.260x | 4.007x | 3.306x | 3.802x |
| **Net leverage, now** | **5.448x** | **5.281x** | **4.062x** | **3.356x** | **3.865x** |
| Covenant maximum | 6.00x | 5.50x | 5.00x | 4.50x | 4.50x |
| **Leverage headroom** | **0.552x** | **0.219x** | **0.938x** | **1.144x** | **0.635x** |
| Interest coverage, was | 2.135x | 2.280x | 2.944x | 3.621x | 3.165x |
| **Interest coverage, now** | **2.118x** | **2.146x** | **2.749x** | **3.623x** | **3.058x** |
| Covenant minimum | 2.00x | 2.00x | 2.00x | 2.00x | 2.00x |
| **Coverage headroom** | **0.118x** | **0.146x** | **0.749x** | **1.623x** | **1.058x** |
| Economic net leverage (non-covenant) | 6.012x | 5.790x | 4.486x | 3.734x | 4.296x |

**No covenant is breached in any period**, in either measure, and
`test_no_covenant_is_breached_after_the_revision` asserts it. FY2023 and FY2024 coverage
headroom is thin at 0.12x and 0.15x. That is a more realistic leveraged position than the
previous 0.14x / 0.28x and it exercises exactly the covenant reporting this platform is being
built to produce.

### 6.5 What did not change

`config/anchors/anchor_by_entity.csv`, `anchor_by_business_unit.csv`,
`anchor_addback_composition.csv`, `anchor_fx_rates.csv`, `anchor_intercompany.csv` and
`anchor_opening_balance_sheet.csv` are **byte-identical to commit `0ffe502`**. The revenue
build, the entity and BU pushdown, the add-back composition, the FX rate anchors, the
intercompany anchors and the opening balance sheet are untouched.

---

## 7. Files changed

**New — configuration (1):** `config/debt/treasury_policy.csv`.

**New — code (1):** `tools/derive_anchor_inputs.py`.

**New — reference data (4):** `cta_expectation.csv`, `layer1_equity_bridge.csv`,
`cta_group_bridge.csv`, `revolver_utilisation.csv`.

**New — documentation (3):** `docs/adr/0017-layer-1-equity-bridge-and-derived-cta.md`,
`docs/adr/0018-revolver-utilisation-and-interest.md`, this report.

**New — tests (1):** `tests/test_phase02_2_corrections.py`, 34 tests.

**Removed (1):** `data/reference/translation_difference.csv`.

**Amended — code (9):** `series.py` (measurement reserve removed; equity at historical rates;
dated equity events; `build_actuals` memoised), `ledger.py` (`EQUITY_EVENTS` register;
contributed capital no longer anchored in USD), `model.py` (share-based compensation set to the
anchor, cost mix normalised around it), `translation.py` (rewritten: CTA derivation, layer-1
equity bridge, group CTA bridge), `targets.py` (layer-1 equity and CTA bridge rows),
`bsdrivers.py` (`daily_utilisation`; treasury policy parameters), `datasets.py` (debt schedule
read from the ledger; revolver utilisation dataset), `common.py` (treasury policy loader),
`build.py` (new datasets), `validate.py` (controls replaced).

**Amended — anchor model (1):** `src/anchors/build_anchors.py` — interest decomposed into base
rate, margins, swap and fee; treasury policy and credit agreement read from configuration;
`CTA_MOVEMENT`, `NCI_FX` and `RCF_AVG_DRAWN` derived.

**Amended — configuration (4):** `group_coa.csv` (−`329100`), `source_coa_aurora.csv`
(−`3250`), `credit_agreement_terms.csv` (+CA-033, CA-034, CA-035),
`control_register.csv` (+CTL-FX-12, CTL-CON-14, CTL-FS-10). Anchor CSVs regenerated by the
model.

**Amended — documentation (9):** `fx-cta-policy.md`, `synthetic-data-methodology.md`,
`source-system-design.md`, `source-data-dictionary.md`, `control-framework.md`,
`data-contract.md`, `adr/0016-…` (retired), `adr/README.md`, `phases/roadmap.md`,
`phases/phase-02-1-report.md` (superseding notes), `README.md`, `financial-anchors.md`
(regenerated).

**Amended — tests (2):** `test_architecture_invariants.py` (FY2026 covenant position
restated), `test_phase02_1_corrections.py` (the two assertions that pinned superseded anchor
values, and the cash-tie test rewritten to read the ledger rather than the retired reserve
disclosure).

---

## 8. Controls and tests

### New controls (11)

| Control | What it proves |
|---|---|
| `P2-EQ-01` | The layer-1 equity roll-forward leaves nothing unexplained |
| `P2-EQ-02` | Layer-1 equity equals the anchor-derived target |
| `P2-EQ-03` | No measurement reserve or equivalent residual account exists — tested against the *purpose*, not one account number |
| `P2-EQ-04` | Layer-1 cash ties to the anchor with no reserve, re-derived from the journal lines |
| `P2-FX-01` | Contributed capital is constant in local currency |
| `P2-FX-02` | The anchored CTA is reproduced from source balances and FX policy |
| `P2-FX-03` | Every CTA row is derivable from source balances and rates alone |
| `P2-DBT-01` | Opening + draws − repayments = closing, chained across 44 months |
| `P2-DBT-02` | Average daily drawn × rate + commitment fee = the recorded charge |
| `P2-DBT-03` | The debt schedule agrees with the general ledger every month |
| plus the removal of `P2-RES-01` and `P2-RES-02`, which existed to bound a reserve | |

### New register entries (3)

`CTL-FX-12` CTA reproduces the source-layer expectation · `CTL-CON-14` no residual or
balancing account in any layer · `CTL-FS-10` facility charge supported by the daily drawn
balance.

### Regression

| Check | Result |
|---|---|
| Entire Phase 2 dataset regenerated | ✅ 1,080,782 journal lines, 507 native extracts, 528 files |
| Phase 1 / 1.1 / 2 / 2.1 tests rerun | ✅ all pass |
| Full test suite | ✅ **317 passed** (284 → 317) |
| Phase 2 source controls | ✅ **77 / 77 pass** (69 → 77) |
| Injected fault fixtures | ✅ **10 / 10 detected**, each by its named control |
| Deterministic regeneration | ✅ digest `34adb63e…` identical across consecutive builds |
| Source trial balances balance in native conventions | ✅ `P2-SRC-03`, re-parsed from the raw extracts in all three sign conventions, worst 0.0000 |
| No measurement reserve or equivalent residual anywhere | ✅ `P2-EQ-03`, and `test_no_account_in_any_chart_exists_to_balance_the_model` |
| CTA derivable from source balances + FX policy | ✅ `P2-FX-02`, `P2-FX-03`, variance 0.000000 |
| Revolver interest supported by the generated debt data | ✅ `P2-DBT-02`, variance 0.0000 in every year |
| Derived anchor inputs not stale | ✅ `tools/derive_anchor_inputs.py --check` runs as a test |
| Clean baseline uncontaminated by faults | ✅ fault variants confined to `data/faults/<id>/` |

**No control or tolerance was weakened.** The anchor conformity tolerances remain 0.5% on
income statement aggregates and 1.0% on balance sheet captions; the new equity, CTA and debt
controls are tighter than anything they replace — three of them at $1,000, one at the cent.

---

## 9. Carried into Phase 3

Nothing from the Phase 2.1 list remains open; all three items are closed above. Two notes for
the next phase, neither of which is a defect:

1. **`data/reference/cta_expectation.csv` is an expectation, not a fact to be loaded into the
   reporting model.** Phase 3 should stage it as a control input only. `CTL-FX-12` consumes it
   at Phase 5.
2. **The FY2024 effective tax rate anchor** now applies to a small loss (§6.1). No change was
   made. If the reviewer wants it revisited it belongs with OQ-05, not with a source-layer
   correction.

---

**Phase 2.2 is complete.** The source layer has no plugs, no residuals and no balancing
accounts; its equity closes on the transactions that happened plus a translation adjustment
computed from its own balances; and its debt is priced off the days it was actually drawn.
