# The consolidated financial statements

What the engine produces, how each statement is built, and what has been proved about it.

All figures USD m unless stated. Built from source layer `fd7afb8f…`, consolidation build
`78e406e139662392`.

---

## 1. Income statement

`rpt_income_statement`, 599 rows — one per period × business unit × entity, so the same
artefact serves the group total, the segment view and the entity view without a second model.

Every measure is coalesced where it is built. A `FILTER` that matches nothing yields NULL and
one NULL anywhere in a subtraction voids the whole line — an entity with cost and no revenue
silently removed its own gross profit from the group total until that was fixed.

| | FY2023 | FY2024 | FY2025 | FY2026 (8m) |
|---|---|---|---|---|
| Revenue | 328.000 | 371.400 | 412.100 | 278.981 |
| Gross profit | 91.205 | 105.291 | 119.250 | 77.082 |
| Gross margin | 27.8% | 28.3% | 28.9% | 27.6% |
| EBITDA | 28.705 | 38.891 | 51.250 | 29.202 |
| Adjusted EBITDA | 38.505 | 47.091 | 57.750 | 33.013 |
| EBIT | 13.403 | 21.470 | 32.748 | 14.174 |
| Net income | (6.992) | (1.291) | 6.780 | (2.238) |
| Attributable to non-controlling interests | (0.197) | (0.219) | (0.266) | (0.180) |
| **Net income attributable to the parent** | **(6.795)** | **(1.072)** | **7.046** | **(2.058)** |

**EBITDA** is computed from the `is_ebitda` attribute on the account, not from a list of
account numbers in code. **Adjusted EBITDA** adds the `is_ebitda_addback` accounts —
restructuring, transaction costs, integration and the ERP programme, legal settlements,
retention bonuses and the sponsor monitoring fee — which sit inside operating expenses at
layer 1 rather than being added back by a management journal
([ADR-0013](adr/0013-adjusted-ebitda-definition.md)). The add-backs run 9.8 / 8.2 / 6.5 / 3.8
as the integration programme completes.

**NCI attribution** sits below tax in account 850100 and is explicitly outside EBITDA
(`P4-NCI-05`): the credit agreement defines Consolidated EBITDA on the group, not on the
group's economic share.

The group is loss-making in FY2023 and FY2024 and turns profitable in FY2025 — an LBO carrying
229m of term debt through an integration programme, which is the intended shape of the
scenario.

`P4-PL-01` proves the statement is internally consistent: revenue less cost of sales equals
gross profit, and EBITDA less depreciation and amortisation equals EBIT.

## 2. Balance sheet

`rpt_balance_sheet`, 1,296 rows — one per caption × class × month.

> **Assets = Liabilities + Equity in all 48 consolidated months, with a residual of exactly
> 0.00.** No balancing account, no residual reserve, no forced caption. (`P4-BS-01`)

At 31 December 2025:

| Assets | | Liabilities and equity | |
|---|---|---|---|
| Cash and cash equivalents | 22.000 | Accounts payable | 40.103 |
| Accounts receivable, net | 65.484 | Contract liabilities | 6.678 |
| Contract assets | 8.901 | Accrued liabilities | 22.665 |
| Inventory, net | 40.090 | Income taxes payable | 2.473 |
| Prepaid and other current | 8.242 | Current portion of debt | 21.736 |
| Property, plant and equipment, net | 95.200 | Operating lease liabilities | 24.500 |
| Operating lease right-of-use assets | 24.500 | Long-term debt | 229.496 |
| **Goodwill** | **140.697** | Deferred tax liabilities | 20.397 |
| **Intangible assets, net** | **52.476** | Other long-term liabilities | 4.000 |
| Investments in subsidiaries | **—** | | **372.048** |
| Intercompany balances | **—** | Contributed capital | 168.600 |
| Other non-current assets | 7.800 | Retained earnings | (57.832) |
| | | Cumulative translation adjustment | 0.283 |
| | | Non-controlling interests | 2.158 |
| | | Result for the period | (19.869) |
| | | | **93.340** |
| **Total assets** | **465.390** | **Total liabilities and equity** | **465.390** |

Four captions are the consolidation's own work and would not exist in any entity's books:

* **Goodwill 140.697** — derived from eleven acquisition bridges, never plugged, every posting
  naming its acquisition (`P4-PPA-01`, `P4-PPA-04`). See
  [`investment-and-ppa.md`](investment-and-ppa.md).
* **Intangible assets, net 52.476** — acquired customer relationships and technology at fair
  value less accumulated amortisation, from 18 tranches.
* **Investments in subsidiaries — nil** and **Intercompany balances — nil.** Both eliminate
  completely. They are presented rather than suppressed, because a caption that is nil *because
  it eliminated* is evidence; a caption that is absent is not.
* **Cumulative translation adjustment 0.283** and **Non-controlling interests 2.158** — separate
  components of equity, each with its own roll-forward.

"Intercompany balances" is deliberately the caption for both the receivable and the payable
side, so the elimination is visible on both. It is presented once per account class; collapsing
it to a single row is what made the artefact non-deterministic before Phase 4A.

> **`Result for the period` is defective.** It accumulates prior years' consolidation
> adjustments rather than showing the period's result. Total equity is correct; the split
> between it and retained earnings is not. See
> [`phase-04b-engine-findings.md`](phases/phase-04b-engine-findings.md), defect **P4-D-01**.

Three controls guard presentation, and each exists because of a defect that balanced perfectly
while being wrong: `P4-BS-02` (one caption per account — an account in two captions is counted
twice and the statement still balances), `P4-BS-03` (no account without a caption — it
disappears from the statement while staying in the fact), `P4-BS-05` (the result appears exactly
once — excluding the close counted every closed year twice, and the balance sheet was out by the
whole of prior years' earnings).

## 3. Cash flow

`rpt_cash_flow`, 48 rows. Derived from balance sheet movements rather than modelled separately
([ADR-0006](adr/0006-cash-flow-derived-indirect.md)):

```
0 = cash + every other balance sheet account + every income statement account
⇒ cash movement = −(other balance sheet movements) − (result)
```

The statement therefore ties **by construction**, provided every non-cash balance sheet account
lands in exactly one cash flow category and the whole income statement lands in operating. That
proviso is what `P4-CF-03` tests — a mis-categorised account still ties while reporting the
wrong line.

> **Opening cash + operating + investing + financing + FX effect on cash = closing cash, with a
> difference of exactly 0.00 in all 48 periods.** Closing cash ties to the consolidated balance
> sheet at exactly 0.00 in all 48 periods. (`P4-CF-01`, `P4-CF-02`)

| | FY2023 | FY2024 | FY2025 | FY2026 (8m) |
|---|---|---|---|---|
| Net income attributable to parent | (6.795) | (1.072) | 7.046 | (2.058) |
| Non-cash and other | (2.280) | 18.111 | 13.255 | 8.335 |
| Working capital | (50.404) | (1.406) | 1.013 | (12.845) |
| FX on non-cash balances | (2.062) | (2.506) | 4.816 | (0.911) |
| Translation on the year-end close (USD) | 0.08 | 0.03 | 0.03 | — |
| **Operating cash flow** | **(61.541)** | **13.128** | **26.130** | **(7.478)** |
| **Investing cash flow** | **(313.616)** | **(47.909)** | **(13.019)** | **(1.956)** |
| **Financing cash flow** | **390.057** | **34.981** | **(6.355)** | **1.961** |
| **FX effect on cash** | **0.100** | **(0.199)** | **0.244** | **0.053** |
| Closing cash | 15.000 | 15.000 | 22.000 | 14.580 |

FY2023 is the year the platform was funded and the acquisitions paid for: 313.6m invested
against 390.1m raised, and 50.4m absorbed into working capital as the group started trading.

**Cash is never the residual.** The net change in cash is measured from the cash accounts
themselves and the categories are proved to partition the balance sheet. There is no
"other movement" line and no FX plug.

### The two defects found in Phase 4A, and why neither was closed with a plug

**The translation accounts were inside the operating bucket.** Accounts `330100`–`330300` and
`340400` carry `cash_flow_category = 'OP_NONCASH'` in the approved chart. Excluding them from
financing alone left them inside operating and counted the translation twice. They are now
mapped to a synthetic `CTA` bucket inside the statement so they leave every category, and the
non-cash reconciling item is derived as `−CTA movement − FX effect on cash`.

**The year-end close was stranded.** The close is excluded from both sides of the statement,
because including it would put a whole year's earnings into a balance sheet bucket in December.
Its two sides do not quite cancel: in local currency the close balances to the cent, but
translated, its income statement legs carry each month's average rate and its retained-earnings
leg does not. The trial balance absorbs that difference into CTA — which is why layers 1 and 5
still sum to zero and the balance sheet still balances — but dropping both sides stranded it,
and the statement was short by exactly that amount in the three Decembers that have a close:
**0.08, 0.03 and 0.03 USD**.

It is now a presented line, `close_translation_usd`, **computed from the close entry itself**
and not derived as the difference between the two sides of the statement. That distinction is
the whole point: a statement that ties because one line is whatever makes it tie is not a
statement that ties. An interim 0.10 USD tolerance carried for this residual was **removed**
once the residual was explained.

### FX effect on cash is not CTA

| | FY2023 | FY2024 | FY2025 |
|---|---|---|---|
| FX effect on **cash** | 0.100 | (0.199) | 0.244 |
| FX on **non-cash** balances (operating, non-cash) | (2.062) | (2.506) | 4.816 |

The first is the retranslation of foreign-currency cash. The second is the retranslation of
everything else, which is a non-cash reconciling item and not a working capital swing. Routing
the second through the first would make the statement tie while reporting an implausible
exchange effect on a mostly-USD cash balance; `P4-FX-08` is the control that objects.

## 4. Statutory and management

`rpt_basis_comparison` states seven headline measures on both bases for four years, with the
difference and the layer-4 total that must explain it. **All 28 rows are explained by layer 4
exactly** (`P4-BAS-01`), and the statutory basis contains zero layer-4 rows (`P4-LAY-03`).

Layer 4 is currently empty, so the two bases are numerically identical. That is disclosed by
`P4-BAS-02` rather than presented as a proof, and the empirical proof of separation comes from
fixture `F4-MGT-LEAK`. See [`management-adjustments.md`](management-adjustments.md).
