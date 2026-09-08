# Non-controlling interests, as built

How `src/consol/nci.py` attributes the minority's share, and the governance case behind the
figure it now attributes.

[`nci-policy.md`](nci-policy.md) is the approved treatment. This document records the
implementation and the decision that superseded the Phase 1 earnings estimate.

---

## 1. The only non-controlling interest in the group

**Northstar Parts UK Ltd. (NIG-510)** is 80% owned by Northstar Aftermarket Solutions
(NIG-500) and 20% by its founding management, who retained their stake when the platform
acquired the business. Every other subsidiary is wholly owned.

It is a second-tier holding: Topco → NIG-500 → NIG-510. The group's effective interest is the
product down the chain — 100% × 80% = 80% — and the effective NCI is 20%. A flat register would
consolidate NIG-510 directly under Topco and give it its direct percentage, which happens to be
the same number here and would not be if NIG-500 were itself partly owned.

## 2. Full consolidation, separate presentation

NIG-510 is consolidated at **100%**. Every line of its revenue, cost, assets and liabilities
enters the group in full. The minority's interest is not a deduction from those lines; it is a
separate attribution of the result and a separate component of equity.

```
Consolidated net income                    100% of every subsidiary
  less: attributable to non-controlling interests     20% of NIG-510
  = net income attributable to the parent
```

Both figures appear in `rpt_income_statement`: `net_income_usd` before attribution and
`net_income_parent_usd` after it.

## 3. The five NCI accounts

Held separately so that the roll-forward is auditable rather than a moving balance:

| Account | |
|---|---|
| 340100 | opening balance |
| 340200 | share of result for the period |
| 340300 | dividends and distributions |
| 340400 | share of the translation adjustment |
| 340500 | acquisitions and ownership changes |

Closing is **derived** from the five, never held as a sixth balance. `P4-NCI-04` requires
opening + result + distributions + CTA share + ownership movements = closing, every year.

## 4. What the minority's share is calculated on

```
NCI share = ( NIG-510's own consolidated result
            + the layer-3 adjustments attributable to NIG-510 )
            × the effective NCI percentage for the period
```

The base is **layer 3 and not layer 2**, and that is the substantive design decision here.

An intercompany elimination removes a matched pair — the seller's revenue and the buyer's
cost — and changes group profit by **nothing**. Attributing the buyer's half to the buyer
without the seller's half to the seller hands NIG-510 its purchases for free. When the base
included layer 2, NIG-510's own result of USD (0.78)m became **+4.71m** and the attributed NCI
came out five times the anchor, in the wrong direction. Restricting the base to layer 3 — the
consolidation adjustments that genuinely belong to the subsidiary, principally unrealised
profit on goods it holds — is the correction.

`P4-NCI-02` proves the percentage used is the entity's own effective percentage from the
ownership register, never a group total and never a percentage applied twice down a chain.
`P4-NCI-03` proves the attribution happens exactly once per entity per period.

## 5. The roll-forward

USD, as built:

| | FY2023 | FY2024 | FY2025 | FY2026 |
|---|---|---|---|---|
| Opening | — | 2,673,319.01 | 2,404,986.94 | 2,158,051.93 |
| Share of result | (197,388.52) | (218,965.71) | (265,948.96) | (179,967.66) |
| Distributions | — | (30,000.00) | (40,000.00) | (50,000.00) |
| Share of translation | 70,707.53 | (19,366.36) | 59,013.95 | 16,923.23 |
| Recognised at acquisition | 2,800,000.00 | — | — | — |
| **Closing** | **2,673,319.01** | **2,404,986.94** | **2,158,051.93** | **1,945,007.50** |

The minority's interest declines because NIG-510 is loss-making
and distributes cash to its minority shareholders; the translation share moves with sterling.

## 6. Presentation

**Income statement.** The attribution sits below tax, in account 850100, and is explicitly
**not** in EBITDA. `P4-NCI-05` enforces that: the credit agreement defines Consolidated EBITDA
on the group, not on the group's economic share, so covenant leverage is calculated on the 100%
basis. Netting the minority's share into EBITDA would understate the covenant metric and would
be very difficult to spot.

**Balance sheet.** Non-controlling interests are a separate component of equity, inside total
equity, not a liability and not mezzanine. USD 2.158m at 31 December 2025.

**Cash flow.** Distributions to non-controlling shareholders are a **financing** outflow. The
attribution of result is not a cash flow at all and appears in neither the operating nor the
financing section.

**Interaction with the investment elimination.** ACQ-009 recognises the minority's share of
NIG-510's net assets at acquisition — USD 2.8m — inside the goodwill bridge, where it is added
to consideration before deducting the fair value of identifiable net assets. That is the same
2.8m that opens the roll-forward. If NCI at acquisition were omitted from the bridge, goodwill
would be understated by exactly the minority's share of the fair-value uplift, and the balance
sheet would still balance.

## 7. P3-D-07 — a governance case worth reading

**The disagreement.** Phase 1 anchored the minority's share of result at **0.18 / 0.28 / 0.36**
USD m for FY2023-25. Derived from the generated ledger the same figure is **(0.197) / (0.219) /
(0.266)** — the opposite sign.

**The cause.** The Phase 1 figure was a top-down estimate: 20% of a plausible profit for
NIG-510, made before any entity-level profit and loss existed to take 20% of. When Phase 2
generated the ledgers, NIG-510 turned out to be loss-making on its own books. It buys from
NIG-200 at the approved transfer price and sells at a **12.6%** gross margin, which does not
cover its own operating cost:

| USD m | FY2023 | FY2024 | FY2025 |
|---|---|---|---|
| External revenue | 17.500 | 19.500 | 22.300 |
| Cost of sales | 15.303 | 17.296 | 19.681 |
| — of which purchased from NIG-200 | 4.826 | 5.719 | 6.555 |
| Gross margin | 12.6% | 11.3% | 11.7% |
| Result after tax | (0.775) | (0.883) | (1.145) |

`config/anchors/anchor_by_entity.csv` anchors NIG-510's **external revenue** — 17.500 / 19.500
/ 22.300 — which the ledger reproduces exactly. Its *profitability* was never anchored, never
calibrated and never tested. The 42% gross margin the Aftermarket business unit carries is a
business-unit figure shared between NIG-500 and NIG-510, and the transfer price leaves NIG-510
barely above breakeven before overheads.

**Why the engine reported it instead of fixing it.** Two approved inputs disagreed. Scaling the
attribution to the anchor would have produced the expected number and destroyed the only
evidence that they disagreed. The engine reported the difference and Phase 4 stopped.

**The decision.** The owner ruled that the **generated entity ledger and the approved
transfer-pricing economics are the authority** and that the Phase 1 estimate is superseded
([ADR-0025](adr/0025-the-entity-ledger-supersedes-the-phase-1-nci-estimate.md), `SX-010`).

**Why the transfer price was not changed.** It would have been the other way to close the gap,
and it was rejected for a specific reason: the transfer price is an approved input to source
generation with its own economics. Moving it to fit a superseded estimate would silently
restate every intercompany margin, the unrealised profit provision, the Aftermarket business
unit's gross margin and NIG-200's revenue — a large, opaque change to the substance of the
model made in order to preserve a number that was itself never derived from anything. The
weaker input was the one that had never been calibrated, and that is the one that gave way.

**What replaced it.** `NCI_INCOME` is now **derived**, not transcribed, by
`tools/derive_nci_anchor.py` from the engine's own attribution, with a `--check` mode the test
suite runs. There is a feedback loop — the anchor feeds net income attributable to the parent,
which feeds the anchor pack — so the tool converges rather than computing once. It converged at
**iteration 1 with a difference of 0.000000**.

| USD m | FY2023A | FY2024A | FY2025A | FY2026B | FY2026F |
|---|---|---|---|---|---|
| Superseded Phase 1 estimate | 0.180 | 0.280 | 0.360 | — | — |
| Derived from the ledger | (0.197389) | (0.218966) | (0.265949) | (0.179968) | (0.179968) |

**What did not move.** NCI is an attribution below the tax line and inside equity. Consolidated
revenue, EBITDA, net income before attribution, total equity, cash and debt are unchanged. What
changed is the split of equity between the group and the minority, and the line below tax that
names it.

**The control that was missing.** Nothing compared the two figures, which is how a Phase 1
estimate survived three phases after being contradicted. `P4-NCI-01` to `P4-NCI-05` now iterate
from the ownership register's non-controlling percentages, and the derivation tool's `--check`
mode fails if the anchor and the engine drift apart again.
