# Staging and Conformed Data Dictionary

Every table Phase 3 produces, its grain, and what each column means. Storage is DuckDB at
`data/20_warehouse/northstar.duckdb`, with each layer also materialised as Parquet under
`data/10_staging/`. None of it is committed — the whole chain rebuilds deterministically
from the frozen source layer and the committed configuration. What **is** committed is
`data/phase03_manifest.json` (row counts and a SHA-256 per artefact), the control results,
the reconciliation and the mapping acceptance detail.

Sign convention throughout: **debit-positive**. Currency throughout: **the entity's own
functional currency**. There is no USD column — translation is Phase 4 (ADR-0005).

Money is **`DECIMAL(18,2)`** from the standardised layer onward, never `DOUBLE` (ADR-0022).
The parsed layer keeps the double it read from the file; the cast happens where the canonical
sign is applied, and every later layer inherits it. Every committed artefact is written in a
total order for the same reason: an aggregation or a serialisation that depends on which
thread finished first is not reproducible.

---

## 1. `parsed_aurora` · `parsed_sable` · `parsed_kestrel`

**Grain**: one row per line in one source extract file.
**Rows**: 525,338 · 370,906 · 184,538.

Each table holds three groups of columns.

**Lineage**

| Column | Notes |
|---|---|
| `erp_system` | `AURORA`, `SABLE`, `KESTREL` |
| `source_file` | the file name, without a path |
| `source_row_ordinal` | 1..N within the file, ordered by that ERP's own line key. Dense (`P3-ING-09`) |
| `ingest_build_id` | the deterministic build id, derived from the source digest and the configuration |

**Typed derivations** — the same names across all three systems, so the union is possible:

`source_account` (always text) · `source_account_name` · `source_entity_key` ·
`posting_date` · `fiscal_year` · `fiscal_period` · `journal_id` · `line_number` ·
`document_id` · `document_type` · `source_event_type` · `source_description` ·
`source_currency` · `native_signed_amount` · `debit_amount` · `credit_amount` ·
`source_department_key` · `source_cost_center_key` · `source_partner_key` ·
`source_customer_key` · `source_product_key` · `source_line_attributes` ·
`source_period_raw` · `source_normal_balance_declared` · `source_translated_amount` ·
`source_translated_currency`

`native_signed_amount` is still in the **source system's own convention** at this layer:
Aurora's signed amount, Kestrel's `SOLL − HABEN`, and Sable's *unsigned* natural-sign value.
Normalisation is the next layer's job.

**Native columns**, verbatim, prefixed `native_` — every column of the extract as it was
written, in its original order. `native_AMOUNT_USD_SYSTEM` and `native_DMBTR_KONZERN_EUR`
are the two source-translated fields that no calculation may read (CTL-FX-06).

---

## 2. `stg_standardised`

**Grain**: `line_uid` = `erp_system | source_file | journal_id | line_number`.
**Rows**: 1,080,782. Unique (`P3-ING-08`).

Everything from the parsed layer, plus:

| Column | Notes |
|---|---|
| `entity_code`, `bu_code`, `country_code`, `functional_currency`, `erp_company_code` | resolved through `dim_entity` on the source entity key |
| `accounting_period` | what the source posted to: 1–12, or 13–16 at Kestrel |
| `management_period` | the calendar month a reader sees: always 1–12 |
| `period_key` | `fiscal_year × 100 + management_period` |
| `special_period`, `special_period_type`, `is_adjustment_period` | the four named Kestrel types |
| `signed_local_amount` | **debit-positive**, `DECIMAL(18,2)`. Sable's sign comes from the approved chart, never from the extract's own `NORMALBALANCE` |
| `debit_local`, `credit_local` | derived from the signed amount, so all three systems present the same three fields |
| `native_debit`, `native_credit` | Kestrel's own SOLL and HABEN, kept to prove the derivation |
| `chart_normal_balance`, `chart_mapping_type`, `chart_default_group_account` | from the approved source chart |
| `account_effective_from`, `account_effective_to` | the mapping's effective dates |
| `native_dept_code` | the department segment as posted |
| `dept_code` | `coalesce(declared attribute, posted segment)` — what a rule reads |
| `cost_center_code` | native where the system carries one, otherwise resolved from entity + department |
| `native_cost_center_code`, `resolved_cost_center_code` | kept side by side so `P3-DIM-06` can compare them |
| `dept_function` | `coalesce(declared attribute, cost centre's function)` |
| `dimension_dept_function`, `native_cost_center_dept_function` | the dimension's own view, for `P3-MAP-12` |
| `partner_entity_code`, `customer_code`, `product_code` | |
| `attr_*` (20 columns) | the line-attribute string parsed into named columns: `attr_dept_function`, `attr_asset_class`, `attr_instrument_type`, `attr_partner_bu`, `attr_maturity_months`, `attr_product_group`, `attr_income_type`, `attr_presentation`, `attr_advisor_type`, `attr_expense_subtype`, `attr_cost_type`, `attr_accrual_type`, `attr_vendor_category`, `attr_tax_jurisdiction`, `attr_revaluation_flag`, `attr_reimbursable_type`, `attr_project_code`, `attr_cost_center_function`, `attr_dept_code`, `attr_special_period` |

---

## 3. `stg_mapped_enriched`

**Grain**: `line_uid`. **Rows**: 1,080,782.

Everything from the standardised layer, plus the mapping and the account metadata:

| Column | Notes |
|---|---|
| `group_account` | the mapped account. Null only on an unresolved line |
| `mapping_status` | one of the ten declared statuses; every line has exactly one |
| `mapping_rule_id` | the rule that produced the account, where one fired |
| `candidate_rule_ids` | every rule whose condition matched, in priority order |
| `matched_branch_count` | more than one is `AMBIGUOUS` |
| `chart_mapping_type_applied` | `DIRECT`, `MERGE`, `SPLIT`, `DERIVED` |
| `is_presentation_reclass`, `presentation_reclass_type` | `GKV_TO_UKV` for the German total-cost-method items |
| `group_account_name`, `statement`, `fs_caption_l1`, `fs_caption_l2`, `account_class`, `reporting_block`, `group_normal_balance`, `group_normal_sign`, `fx_method`, `cash_flow_category`, `is_intercompany`, `is_ebitda`, `is_ebitda_addback`, `is_statistical`, `include_in_tb_balance` | **all from `dim_account`.** No stage restates a caption, an EBITDA flag or a cash-flow category of its own |

---

## 4. `fact_journal_line`

**Grain**: `(erp_system, source_file, journal_id, line_number)`, condensed into `line_uid`.
Enforced, not asserted. **Rows**: 1,080,782. **Layer**: 1, and only 1.

The conformed general ledger fact. It carries the lineage block, the conformed dimension
keys, the account metadata, the period block, the three amount fields in functional currency,
and the mapping provenance. It carries `customer_code` and `product_code` as **references**;
the revenue and cost measures at customer and product grain live in `fact_revenue_detail`
(ADR-0008).

`scenario_code = 'ACT'`, `version_code = 'ACTUAL'`, `layer_id = 1` on every row.

---

## 5. `fact_trial_balance`

**Grain**: layer × scenario × version × entity × business unit × cost centre × group account
× partner × period × special-period type × currency. **Rows**: 42,081.

Built **from** `fact_journal_line`, never alongside it, so the two cannot drift
(`P3-REC-08`). Measures: `signed_local_amount`, `debit_local`, `credit_local`, `line_count`.

The source-translated columns are deliberately **absent** here (`P3-ING-12`).

---

## 6. Conformed dimensions

Every one carries its source natural key, its conformed key, and a `source_config` column
naming the file it was built from.

| Dimension | Rows | Natural key | Built from |
|---|---|---|---|
| `dim_entity` | 15 | `entity_code` | `config/entities/entity_master.csv` |
| `dim_business_unit` | 5 | `bu_code` | `config/dimensions/business_unit.csv` |
| `dim_department` | 26 | `department_code` | `config/dimensions/department.csv` |
| `dim_account` | 188 | `group_account` | `config/coa/group_coa.csv` |
| `dim_source_account` | 392 | `erp_system` + `source_account` | the three source charts |
| `dim_cost_center` | 152 | `entity_code` + `cost_center_code` | `data/reference/cost_centres.csv` |
| `dim_currency` | 4 | `currency_code` | `config/anchors/anchor_fx_rates.csv` |
| `dim_scenario` | 5 | `scenario_code` | `config/dimensions/scenario_version.csv` |
| `dim_version` | 8 | `version_code` | `config/dimensions/scenario_version.csv` |
| `dim_intercompany_partner` | 12 | `partner_entity_code` | a conformed view of `dim_entity` |
| `dim_consolidation_layer` | 5 | `layer_id` | `config/dimensions/consolidation_layer.csv` |
| `dim_date` | 60 | `fiscal_year` + `accounting_period` | the period spine |

Two notes.

`dim_intercompany_partner` is a **view of `dim_entity`**, not an independent list. A partner
is a real legal entity seen from the other side of a transaction — a role, not a population —
and an independent list would drift out of step with the entity master.

`dim_date` carries one row per calendar month **and** one per Kestrel special period per
closed year, with `accounting_period` 13–16 and `management_period` 12. A special period is
an accounting period, not a month, and keeping the two apart is what stops a thirteenth month
reaching a chart.

Hierarchies are kept, not flattened: `dim_entity` keeps its parent, `dim_cost_center` keeps
its department and business unit, `dim_account` keeps the full caption hierarchy. A reporting
layer may flatten them; a conformed dimension may not.

---

## 7. Conformed subledgers and reference tables

Typed and key-resolved, with no accounting performed on them. They are validated inputs
waiting for the phase that consumes them.

| Table | Rows | Grain | Consumed by |
|---|---|---|---|
| `ref_fx_rate` | 544 | currency × period × rate type × rate set | Phase 4 translation |
| `ref_fx_rate_historical` | 36 | entity × account × event | Phase 4 equity translation (FX-P03) |
| `ref_ownership` | 11 | entity × effective period | Phase 4 NCI and investment elimination |
| `ref_investment_register` | 11 | investment event | Phase 4 investment elimination |
| `ref_investment_rollforward` | 463 | parent × subsidiary × period | Phase 4 investment elimination |
| `ref_debt_schedule` | 595 | instrument × period | Phase 5 covenant reporting |
| `ref_revolver_utilisation` | 44 | period | Phase 5 covenant reporting (ADR-0018) |
| `ref_cta_expectation` | 243 | foreign entity × period | **a control input only** — Phase 5's translation engine is tested against it (CTL-FX-12, ADR-0017). It must never be joined into a reporting measure |
| `ref_ic_inventory_holding` | 470 | FIFO layer × holding period | Phase 4 unrealised profit elimination |
| `ref_fixed_asset` | 1,846 | asset | Phase 4 fixed-asset roll-forward |
| `fact_capex_project` | 1,846 | project × period | Phase 5 capital reporting |
| `fact_headcount` | 20,349 | entity × cost centre × job family × period | Phase 5 per-head metrics |
| `fact_revenue_detail` | 50,045 | entity × period × customer × product × account | reconciled to the mapped GL **here** (ADR-0008) |
| `fact_plan` | 26,124 | version × entity × cost centre × account × period | Phase 5 variance reporting |
| `ref_customer` / `ref_product` | 998 / 226 | customer / product | Phase 5 |

`fact_plan` resolves every row to a version in `dim_version` and carries
`version_is_default`, `version_is_locked` and `version_is_reserved`. The reserved Downside
shell has **no rows** (CTL-SCN-06), and Prior Year is **not materialised** — it is derived by
date offset from Actual (ADR-0004).

---

## 8. Staging control tables

| Table | Rows | Purpose |
|---|---|---|
| `map_rules` | 127 | the rule set as loaded, with effective dates and active flag |
| `map_rule_hits` | one per matching rule per line | which rules matched which line |
| `map_resolution` | one per line with a match | the winner, the branch count, the candidate list |
| `map_exceptions` | **0** on the clean baseline | the investigation file, also written to `data/10_staging/exceptions/mapping_exceptions.csv` |
| `map_acceptance` | 1,080,782 | the grading against the oracle, with `agrees` and `classifiable_at_source` |
| `stg_group_adjustment` | **0 by design** | where the consolidation engine will raise a top-side entry. `P3-ADJ-01` fails the build if ingestion writes to it |
| `rpt_group_account_coverage` | 188 | CTL-MAP-06: which group accounts got nothing, and whether that is expected |
| `rec_*` (5 tables) | | the reconciliations, exported to `data/phase03_reconciliation.csv` |

---

## 9. Validation views

Named so they cannot be mistaken for financial statements. Views, not facts, so nothing can
join to them by accident.

| View | What it is |
|---|---|
| `vw_layer1_pl_measures` | external and intercompany revenue, cost of sales, operating expense, below-EBIT and tax, by entity and period, **in local currency** |
| `vw_validation_pl_usd` | the same at approved monthly **average** rates, for comparison with the source-layer targets only |
| `vw_validation_gross_margin_usd` | revenue, cost of sales, gross profit and margin by business unit |
| `vw_validation_bs_usd` | cumulative balances at approved **closing** rates |
| `vw_validation_bs_usd_oracle` | the same built from the oracle's group account, so a mapping variance can be separated from a source variance |

The year-end close and Kestrel's statutory close are excluded from every result measure: the
close reverses the whole income statement into equity, so including it would net every P&L
measure to nil. This is the same treatment the Phase 2 source controls apply.

---

## 10. Committed artefacts

| File | What it proves |
|---|---|
| `data/phase03_manifest.json` | build id, frozen source digest, every row count, the mapping acceptance result, a SHA-256 per artefact |
| `data/phase03_control_results.csv` | all 61 controls with measured value, threshold, status and defect reference |
| `data/phase03_reconciliation.csv` | the group, balance sheet and business-unit reconciliations |
| `data/phase03_mapping_acceptance.csv` | every mapping disagreement, grouped, with the attributes the line carried |
| `data/phase03_fault_results.csv` | each injected fault, the control family that caught it, and the outcome |
