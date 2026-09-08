# Non-Controlling Interest Policy

> **The earnings anchors in this document are SUPERSEDED.** The accounting treatment below —
> 100% consolidation with separate presentation, the five-account roll-forward, the loss
> allocation rule, the equity presentation and the cash-flow treatment — remains the approved
> policy and is what the engine implements. The **anchor tables** were Phase 1 top-down
> estimates made before entity-level profitability existed, and the generated ledger
> contradicted them: `NIG-510` is loss-making on its own books at the approved transfer price,
> so the minority's share of result is negative. Superseded at the Phase 4A gate by
> [ADR-0025](adr/0025-the-entity-ledger-supersedes-the-phase-1-nci-estimate.md); see
> [`nci.md`](nci.md) for the derived figures and the roll-forward as built. The tables are kept
> as written, marked, because the disagreement between them and the ledger is the point.

Complete accounting and data-model treatment of the group's single non-controlling interest.
Specified in full at Phase 1.1 so that Phase 2 source generation does not need redesign.

**Applies to:** `NIG-510` Northstar Parts UK Ltd — **80% owned by `NIG-500`, 20% held by the
founding management team** since acquisition on 1 January 2023. It is the only
non-controlling interest in the group.

---

## 1. Consolidation method — 100% consolidation with separate NCI presentation

`NIG-510` is **fully consolidated**. Every asset, liability, income and expense line is
brought in at **100%**, exactly as for a wholly owned subsidiary. The 20% not owned by the
group is then presented separately within equity and within the income statement.

This is worth stating explicitly because the intuitive but wrong alternative — consolidating
80% of each line — is a real error made in spreadsheet consolidations. Proportionate
consolidation would understate revenue, EBITDA and every balance sheet caption, and it would
break the reconciliation between the consolidated accounts and the entity trial balances.

```
Revenue, cost, assets, liabilities            → 100% consolidated (layer 1)
Intercompany with NIG-510                     → 100% eliminated (layer 2)
Ownership interest in net assets and result   → split 80/20 (layer 3)
```

**Consequence for the income statement:** all revenue and all EBITDA of `NIG-510` are group
revenue and group EBITDA. The 20% appears only below the tax line. Adjusted EBITDA, net debt
and therefore **covenant leverage are all calculated on the 100% basis** — the credit
agreement defines Consolidated EBITDA on the consolidated group, not on the group's economic
share.

## 2. Share of profit or loss

A single layer-3 entry, posted to `ELIM-CON` with `related_entity_key = NIG-510`:

```
Dr  850100  Net income attributable to non-controlling interests   (income statement)
Cr  340200  Non-controlling interests — share of result            (equity)

Amount = NIG-510 net income after tax  ×  NCI % effective for the period
```

`850100` sits **below income tax** in the income statement, in its own caption. It is not an
operating cost and never enters EBITDA — `is_ebitda = FALSE`, `account_class = NCI`.

The resulting presentation is:

| Line | Source |
|---|---|
| Net income | All income statement accounts **excluding** `850100` |
| less: attributable to non-controlling interests | `850100` |
| **Net income attributable to the group** | All income statement accounts **including** `850100` |

Only the group share flows to retained earnings (`320200` *Current year result attributable to
the group*). This is what makes `CTL-FS-05` (retained earnings roll-forward) work: retained
earnings moves by the parent share, not by total net income.

**Anchors — SUPERSEDED (ADR-0025).** Derived from the ledger the figures are
(0.197) / (0.219) / (0.266) / (0.180) / (0.180):

| USD m | FY2023A | FY2024A | FY2025A | FY2026B | FY2026F |
|---|---|---|---|---|---|
| ~~Net income attributable to NCI~~ | ~~0.18~~ | ~~0.28~~ | ~~0.36~~ | ~~0.44~~ | ~~0.40~~ |

**Losses are allocated on the same basis.** A loss-making period allocates the NCI share of
the loss to non-controlling interests even where that drives the NCI balance negative. There
is no floor at zero and no reallocation of excess losses to the group.

## 3. Balance sheet equity and roll-forward

NCI is presented **within equity**, separately from equity attributable to the group. It is
never a liability and never mezzanine.

Five accounts make the roll-forward explicit and auditable rather than a single moving
balance:

| Account | Purpose | FX method |
|---|---|---|
| `340100` | Opening balance | Derived — prior closing USD, never retranslated |
| `340200` | Share of result for the period | Monthly average (mirrors the P&L) |
| `340300` | Dividends and distributions | Rate on the declaration date |
| `340400` | Share of translation adjustment | Derived |
| `340500` | Acquisition and ownership changes | Historical |

```
Closing NCI = 340100 opening
            + 340200 share of result
            − 340300 dividends and distributions
            + 340400 share of translation adjustment
            + 340500 acquisition and ownership changes
```

**Anchors — SUPERSEDED (ADR-0025).** The roll-forward as built is in
[`nci.md`](nci.md) §5; closing NCI is 2.673 / 2.405 / 2.158 / 1.945 USD m.

| USD m | FY2023A | FY2024A | FY2025A | FY2026B | FY2026F |
|---|---|---|---|---|---|
| ~~Opening NCI~~ | ~~2.80~~ | ~~3.08~~ | ~~3.16~~ | ~~3.50~~ | ~~3.50~~ |
| ~~Share of result~~ | ~~0.18~~ | ~~0.28~~ | ~~0.36~~ | ~~0.44~~ | ~~0.40~~ |
| ~~Dividends and distributions~~ | ~~—~~ | ~~(0.15)~~ | ~~(0.20)~~ | ~~(0.25)~~ | ~~(0.25)~~ |
| ~~Share of translation adjustment~~ | ~~0.10~~ | ~~(0.05)~~ | ~~0.18~~ | ~~—~~ | ~~0.05~~ |
| ~~**Closing NCI**~~ | ~~**3.08**~~ | ~~**3.16**~~ | ~~**3.50**~~ | ~~**3.69**~~ | ~~**3.70**~~ |

NCI is 2.3% of total group equity at FY2025 as built. FY2026 Budget and Forecast both open from the
FY2025 actual close of $3.50m, consistent with the rule that alternative views of one fiscal
year share an opening balance sheet.

Enforced by `CTL-CON-11`.

## 4. Share of the translation adjustment

`NIG-510` is a GBP-functional entity, so its net assets generate a translation adjustment.
That movement is **split between group equity and NCI in proportion to ownership at the period
end**:

```
Entity CTA movement × 80%  →  330200  CTA — movement (group)
Entity CTA movement × 20%  →  340400  NCI — share of translation adjustment
```

Allocating 100% of a partially owned subsidiary's CTA movement to group equity is a common
and material error: it overstates group equity and understates NCI by the same amount, and
because both sit inside total equity the balance sheet still balances. Nothing catches it
except a control that looks for it specifically — `CTL-CON-11` and `FX-P20`.

## 5. Dividends and distributions

Distributions paid by `NIG-510` to its 20% holder are:

- debited to `340300`, reducing NCI equity;
- presented as a **financing cash outflow** in the consolidated cash flow statement
  (`CTL-CON-13`), because they are a return of capital to an owner, not an operating cost;
- translated at the rate ruling on the declaration date and not retranslated thereafter.

The 80% paid to `NIG-500` is an intercompany distribution and eliminates in full (layer 2). It
never appears in the consolidated cash flow statement.

Misclassifying the NCI distribution within operating activities overstates operating cash flow
and free cash flow. At $0.20–0.25m per year it is not material to this group, but the
classification is wrong regardless of size, and the control is cheap.

## 6. Ownership effective dating

Ownership is held as **effective-dated rows** in
[`config/entities/ownership_history.csv`](../config/entities/ownership_history.csv), not as a
static column on the entity master:

```
entity_code + effective_from → group_ownership_pct, nci_pct,
                               consolidation_method, change_event, nci_holder
```

The percentage applied when consolidating a period is the one **effective for that period**,
never the current percentage applied retrospectively. Exactly one ownership row must be
effective for each entity and period, and ownership plus NCI must equal 100%
(`CTL-CON-10`, `CTL-CON-01`).

`NIG-510` has a single row: 80/20 from 2023-01-01, open-ended. The effective-dated structure
exists so that a change is a **data event rather than a schema change**.

## 7. Acquisition and ownership changes

None are in scope (ADR-0009), but the treatment is specified now because the alternative is
discovering the gap in Phase 4.

| Event | Treatment | Account |
|---|---|---|
| **Initial acquisition of a partially owned subsidiary** | NCI recognised at the NCI share of the fair value of identifiable net assets at the acquisition date. This group applies the **partial goodwill** method — goodwill is recognised only on the group's share, so NCI carries no goodwill. | `340500` |
| **Step acquisition** (buying out part of an NCI, control retained) | An **equity transaction**, not a further business combination. No gain or loss and no goodwill remeasurement. The difference between consideration and the NCI carrying amount acquired goes to group equity. | `340500` and `310200` |
| **Partial disposal, control retained** | Also an equity transaction. NCI increases; the difference against consideration goes to group equity. | `340500` and `310200` |
| **Disposal resulting in loss of control** | Deconsolidation. Derecognise assets, liabilities and NCI; recycle the accumulated CTA relating to that operation to the income statement (`330300`); recognise any gain or loss. | `330300`, `340500` |

The **partial goodwill** choice matters and is deliberate: it means the NCI balance is
NCI% × identifiable net assets, which is directly recomputable from the balance sheet and
therefore controllable. Full goodwill would require an independent fair value of the NCI at
acquisition, which is a valuation judgement with no observable input here.

`CTL-CON-10` blocks any period where the ownership percentage applied does not match the
effective-dated register, which is what makes a future step acquisition safe to introduce.

## 8. Cash flow presentation

| Item | Presentation |
|---|---|
| `NIG-510` operating cash flows | 100% within consolidated operating activities |
| `NIG-510` capital expenditure | 100% within investing activities |
| Distributions to non-controlling interests | **Financing** outflow (`CTL-CON-13`) |
| Distributions to `NIG-500` (the 80%) | Eliminated; does not appear |
| Share of result attributable to NCI | **No cash flow line.** It is inside consolidated net income and is not a reconciling item — the cash it represents is already in operating activities. |
| Purchase or sale of an NCI without loss of control | Financing (an equity transaction) |

The row most often got wrong is the fifth. Adding back "income attributable to NCI" as a
non-cash item in operating activities is a double count: consolidated net income already
includes 100% of the subsidiary's result and 100% of its cash flows.

## 9. Statutory versus management reporting

| View | NCI treatment |
|---|---|
| **Statutory** (layers 1+2+3+5) | Full NCI presentation: `850100` on the income statement, `340100`–`340500` within equity |
| **Management** (statutory + layer 4) | Identical. NCI is a statutory allocation and is **never** adjusted in the management layer. |

Management reporting is run on the **100% consolidated basis**. Business unit and entity
performance for Aftermarket & Parts includes all of `NIG-510` — the BU leader is accountable
for the whole entity, not 80% of it. The NCI split is a shareholder matter that appears only
at group level below tax.

Two consequences to hold onto:

- **Adjusted EBITDA and covenant leverage are 100% measures.** No NCI adjustment is made, and
  none is permitted by the credit agreement.
- **Earnings-based metrics attributable to shareholders use the parent share.** Where a metric
  is stated per share or as a return to the group's owners, it uses net income attributable to
  the group.

Any management adjustment posted to layer 4 that affects `NIG-510` carries **no** automatic
NCI allocation, because layer 4 is outside the statutory result. If a normalisation needs an
NCI split for a specific analysis, it is posted as two explicit lines.

## 10. Elimination implications

**Intercompany with `NIG-510` eliminates in full at 100%**, not at 80%. The group controls the
entity, so the whole of any intercompany transaction is internal to the reporting entity.
Eliminating only the group's share would leave 20% of an internal transaction reported as
external revenue.

Affected flows (from [`config/ic/intercompany_matrix.csv`](../config/ic/intercompany_matrix.csv)):

| Flow | Description | Eliminated |
|---|---|---|
| `IC-MF-10` | Management fee, `NIG-110` → `NIG-510` | 100% |
| `IC-PR-03` | Product transfers, `NIG-200` → `NIG-510`, at cost plus 12% | 100% |
| `IC-LN-04` | GBP 4.0m working capital loan and its interest | 100% |
| `IC-EQ-11` | Investment in subsidiary, `NIG-500` → `NIG-510` | 80% against investment; 20% reclassified to NCI |

**Two places where the 20% does bite:**

1. **Investment elimination** (`IC-EQ-11`, `CTL-CON-03`). `NIG-500`'s investment eliminates
   against 80% of `NIG-510`'s share capital and pre-acquisition reserves. The remaining 20% of
   net assets is reclassified to NCI rather than eliminated.

2. **Unrealised profit in inventory** (`CTL-CON-12`, `CTL-IC-08`). Where `NIG-510` holds
   inventory bought from `NIG-200` at a 12% transfer margin, the unrealised profit is
   eliminated in **full** — but the *charge* is allocated 80/20 between the group and NCI,
   because it reduces the profit of the selling entity's group and the net assets of the
   holding entity. Bearing 100% of the adjustment in group equity understates NCI.

## 11. Data model

### Configuration
`config/entities/ownership_history.csv` — effective-dated ownership register (§6).

### Dimensions
`dim_entity` gains `has_nci` (boolean) and `nci_holder` (text). Ownership percentages
themselves are **not** on `dim_entity`, because they are period-dependent and a dimension
attribute would silently apply today's percentage to a historical period.

### New fact: `fact_ownership_interest`
| | |
|---|---|
| **Purpose** | The ownership percentage in force for each entity in each period |
| **Grain** | entity × period |
| **Key** | `entity_key`, `period_key` |
| **Columns** | `group_ownership_pct`, `nci_pct`, `consolidation_method`, `change_event`, `is_first_period`, `is_final_period` |
| **Source** | Generated from `ownership_history.csv` by expanding effective-date ranges across periods |

Expanding the register into a period-grain fact means the consolidation engine performs a
join rather than a range lookup, and it makes `CTL-CON-10` a simple equality test.

### `fact_financials` gains `related_entity_key`
Layer-3 and layer-4 entries are posted to a virtual entity (`ELIM-CON`, `ELIM-MGT`), so the
entity key identifies *where the entry sits*, not *what it relates to*.
`related_entity_key` names the subsidiary an adjustment concerns.

Without it, "which entity does this NCI allocation relate to?" and "which subsidiary does this
investment elimination belong to?" are unanswerable, and NCI cannot be reported by entity.
`EXTERNAL`/`NOT_APPLICABLE` for layer-1 rows.

### New group accounts
`340200`, `340300`, `340400`, `340500` (equity roll-forward) and `850100` (income statement
allocation). `340100` renamed to *opening balance* and `320200` to *Current year result
attributable to the group*, so that both names state the basis rather than leaving it implied.

## 12. Controls

| Control | Severity | Tests |
|---|---|---|
| `CTL-CON-01` | Blocking | Ownership + NCI = 100% for every entity |
| `CTL-CON-04` | Blocking | NCI share of income = NCI % × subsidiary net income |
| `CTL-CON-10` | Blocking | The ownership percentage applied is the one effective for the period; exactly one row is effective |
| `CTL-CON-11` | Blocking | Full equity roll-forward closes, including the share of CTA; opening = prior closing, never retranslated |
| `CTL-CON-12` | Blocking | NCI share of consolidation adjustments (unrealised profit, PPA amortisation) allocated, not borne wholly by the group |
| `CTL-CON-13` | Blocking | NCI distributions presented in financing, never operating |
| `CTL-FS-09` | Blocking | Total net income = group share + NCI share; `850100` equals the equity credit to `340200` |
| `CTL-FX-11` / `FX-P20` | Blocking | NCI share of the translation movement split correctly |

## 13. Phase 2 requirements

So that source generation does not need redesign:

1. `NIG-510` generates a **complete standalone trial balance at 100%**, in GBP, exactly like
   any other entity. Nothing in the source data is pro-rated.
2. Distributions to both holders are generated as separate transactions with a declaration
   date, so the 80% eliminates and the 20% is presented in financing.
3. `NIG-510`'s equity carries pre-acquisition reserves distinguishable from post-acquisition
   reserves, so the investment elimination can split them.
4. Intercompany inventory held by `NIG-510` at period end is identifiable, so unrealised
   profit and its 80/20 allocation can be computed.
5. `fact_ownership_interest` is generated for **every** entity and period, not only for
   `NIG-510` — wholly owned entities carry 100/0. A control that only runs where NCI exists
   cannot detect an NCI that appears where it should not.
