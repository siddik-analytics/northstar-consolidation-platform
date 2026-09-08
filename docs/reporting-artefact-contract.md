# The Phase 4 reporting artefact contract

Fifteen published artefacts. For each: what it is for, its grain, the authoritative fact it is
derived from, how it treats periods and the year-end close, its NULL policy, and the controls
that prove it.

This exists so that Phase 5's marts, and the Excel and Power BI models after them, inherit a
**settled** definition of each measure rather than re-deriving one. Two artefacts disagreed
about Adjusted EBITDA for an entire phase (P4-D-02) and the balance sheet mislabelled a
19.9m equity component (P4-D-01) precisely because nothing wrote these rules down.

---

## The three rules every artefact follows

**1. One authoritative fact.** Every artefact is derived from `fact_financials` — through
`vw_statutory_fact` (layers 1+2+3+5) or `vw_management_fact` (+4). No artefact is derived from
another artefact. Where two artefacts express the same measure, `P4-XAR-*` reconciles both to
the fact rather than to each other.

**2. The year-end close is excluded from every income statement measure.** The close reverses
each entity's own result into its reserves in December. Summing a fiscal year *with* it nets
the year to approximately nil. The predicate is `counts_in_result`, and it is the same
predicate everywhere:

```sql
counts_in_result := (statement = 'IS' AND journal_character <> 'CLOSE')
```

Balance sheet measures **include** the close, because moving the result into reserves is a
real equity movement.

**3. No population means zero, never NULL.** NULL means unknown or missing. A component whose
population is empty contributes **zero**, and every additive `FILTER` aggregate is coalesced
where it is built. A single NULL anywhere in an arithmetic expression voids the whole result,
and this has now caused three separate defects in this project. `test_no_additive_filter_aggregate_is_left_un_coalesced`
fails the build if one reappears.

---

## The facts

### `fact_financials`
| | |
|---|---|
| **Purpose** | the authoritative consolidated fact; everything else is derived from it |
| **Grain** | entity × account × cost centre × partner × period × scenario × version × **layer** |
| **Rows** | 48,202 |
| **Upstream** | layer 1 from `fact_layer1_usd`; layers 2–5 from `fact_consol_journal` |
| **Period logic** | monthly, 202301–202612 |
| **Close logic** | carries `journal_character`; the close is a row like any other and consumers exclude it |
| **NULL policy** | `amount_usd` is `DECIMAL(18,2)` and never NULL |
| **Controls** | `P4-FCT-01`, `P4-FCT-02`, `P4-LAY-01` … `P4-LAY-05` |

### `fact_consol_journal`
| | |
|---|---|
| **Purpose** | every consolidation entry, so that "why did this move" is a query |
| **Grain** | one row per leg |
| **Rows** | 6,532 legs, 3,343 entries |
| **Upstream** | the consolidation engines; layer 1 is never copied into it |
| **Close logic** | n/a — consolidation entries are never closed |
| **NULL policy** | `amount_local` may be NULL for USD-only entries; `amount_usd` never is |
| **Controls** | `P4-JNL-01`, `P4-FCT-01`, `P4-FCT-02`, `P4-PPA-04` |

## The statements

### `rpt_income_statement`
| | |
|---|---|
| **Purpose** | the consolidated income statement, and the segment and entity views of it |
| **Grain** | period × business unit × entity |
| **Rows** | 599 |
| **Upstream** | `vw_statutory_fact` |
| **Measures** | revenue, cost of sales, gross profit and margin, operating expenses, D&A, net finance, tax, NCI attribution, EBITDA, add-backs, Adjusted EBITDA, EBIT, net income, net income attributable to the parent |
| **Period logic** | monthly; annual figures are the sum of the months |
| **Close logic** | **excluded** (`counts_in_result`) |
| **NULL policy** | every measure coalesced where built |
| **Controls** | `P4-PL-01`, `P4-XAR-01` |

### `rpt_balance_sheet`
| | |
|---|---|
| **Purpose** | the consolidated balance sheet by caption |
| **Grain** | caption × account class × period |
| **Rows** | 1,296 |
| **Upstream** | `vw_statutory_fact`, balance sheet accounts plus the income statement presented inside equity |
| **Period logic** | cumulative balances from a dense caption spine resolved **once** for the whole statement |
| **Close logic** | **included** on the balance sheet side. `Result for the period` is the **fiscal year to date excluding the close**; everything else the cumulative income statement contains belongs to `Retained earnings` |
| **NULL policy** | dense spine with `coalesce(..., 0)`; a caption with no movement in a month carries its balance forward |
| **Controls** | `P4-BS-01` … `P4-BS-05`, `P4-XAR-05` … `P4-XAR-09` |

The account class is part of the caption key. `Intercompany balances` captions both the
receivables and the payables, deliberately, so the elimination is visible on both sides.

### `rpt_cash_flow`
| | |
|---|---|
| **Purpose** | the consolidated cash flow, derived from balance sheet movements (ADR-0006) |
| **Grain** | period |
| **Rows** | 48 |
| **Upstream** | `vw_statutory_fact` |
| **Period logic** | monthly movements; opening and closing cash are running sums |
| **Close logic** | **excluded from both sides**, with the translation the close carries presented as its own line, `close_translation_usd`, computed from the close entry itself |
| **NULL policy** | every bucket coalesced; the translation accounts are mapped to a synthetic `CTA` bucket so they leave every category |
| **Controls** | `P4-CF-01`, `P4-CF-02`, `P4-CF-03`, `P4-FX-08`, `P4-XAR-10` |

## The bridges and schedules

### `rpt_ebitda_bridge`
| | |
|---|---|
| **Purpose** | statutory EBITDA to Adjusted EBITDA, and separately to Covenant EBITDA |
| **Grain** | fiscal year |
| **Rows** | 4 |
| **Upstream** | `vw_statutory_fact` and `vw_management_fact` (layer 4) |
| **Close logic** | **excluded** — this is what P4-D-02 got wrong |
| **NULL policy** | every component coalesced to zero; the CA-030 add-back has **no population** in this window and is therefore **0.00**, not NULL |
| **Controls** | `P4-MGT-03`, `P4-XAR-02`, `P4-XAR-03`, `P4-XAR-04` |

### `rpt_layer_bridge`
| | |
|---|---|
| **Purpose** | what each consolidation layer contributed, for the measures a reader checks first |
| **Grain** | layer × fiscal year |
| **Rows** | 16 |
| **Close logic** | **excluded** from the income statement measures, **included** in the balance sheet movements — this is what P4-D-03 got wrong |
| **Controls** | `P4-XAR-11` |

### `rpt_basis_comparison`
| | |
|---|---|
| **Purpose** | statutory against management for seven headline measures |
| **Grain** | measure × fiscal year (28 rows) |
| **Close logic** | excluded from the flow measures; balance measures are cumulative to the year end |
| **Controls** | `P4-BAS-01`, `P4-BAS-02` |

### `rpt_goodwill_bridge` · `rpt_intangible_schedule`
| | |
|---|---|
| **Purpose** | how goodwill was arrived at, and the amortisation of what was recognised with it |
| **Grain** | acquisition (11) · tranche × period |
| **Upstream** | `ref_acquisition`, `ref_ppa_intangible`, and `ref_investment_register` for dates |
| **Close logic** | n/a |
| **Controls** | `P4-PPA-01` … `P4-PPA-04`, `P4-INT-01` … `P4-INT-04` |

### `rpt_nci_rollforward` · `rpt_cta_rollforward` · `rpt_pup_provision`
| | |
|---|---|
| **Purpose** | the three roll-forwards that explain an equity component or a provision |
| **Grain** | entity × fiscal year (NCI, CTA) · route × period (PUP) |
| **Period logic** | opening + movements = closing, tested for continuity across years |
| **Close logic** | n/a — these are consolidation constructs and nothing closes them |
| **Controls** | `P4-NCI-04`, `P4-FX-06`, `P4-PUP-01` … `P4-PUP-04`, `P4-XAR-08`, `P4-XAR-09` |

### `rpt_ic_exception`
| | |
|---|---|
| **Purpose** | every intercompany relationship-period and how its two sides compared |
| **Grain** | relationship × entity pair × period (2,355) |
| **Upstream** | `ref_ic_side` and the conformed layer, matched pair by pair |
| **Close logic** | balances net on the cumulative position; flows net on the period movement |
| **NULL policy** | a side with no counterpart survives the full outer join as `MISSING_COUNTERPART` — never dropped |
| **Controls** | `P4-IC-01` … `P4-IC-05` |

---

## For Phase 5

A mart, a workbook or a semantic model that redefines any measure above has forked the
definition, and the fork will not be visible until two reports disagree in front of the board.
The contract is:

* take measures from these artefacts, or recompute them from `fact_financials` using the same
  predicates — `counts_in_result` for income statement measures, cumulative balances for
  balance sheet measures;
* carry `layer_id`, `process`, `rule_id`, the entity keys, `period_key`, `scenario_code`,
  `version_code` and `journal_character` through, or the drill-down stops where the model does;
* coalesce every additive aggregate at the point it is built;
* add a `P4-XAR`-style control for every measure a new artefact re-expresses.
