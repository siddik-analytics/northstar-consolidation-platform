# Data Contract

The dimensional model for the Northstar consolidation and reporting platform. This is the
contract between the consolidation engine (Phases 3–4), the reporting marts (Phase 5), the
Excel models (Phase 6) and the Power BI semantic model (Phase 7). Anything not specified
here is not guaranteed to exist.

## 1. Architecture

```
  data/raw             Source ERP extracts, byte-for-byte as generated. Immutable.
  data/reference       Source master, planning and subledger data
  data/samples         Committed samples and the build digest
  data/faults          Injected-fault variants and their expected results
        |
  data/10_staging      stg_*  — normalised, typed, sign-corrected. Still source-shaped.
        |
  data/20_warehouse    dim_*  — conformed dimensions
                       fact_* — conformed facts, post-consolidation
        |
  data/30_marts        mart_* — reporting-shaped views for Excel and Power BI
        |
  data/90_exports      Board pack outputs, Excel refresh sources, screenshots
```

> **Amended at Phase 2.** The raw layer is `data/raw/` rather than the `data/00_raw/`
> placeholder this contract originally named, and three sibling directories were added for
> the source reference data, committed samples and fault fixtures. This is a naming and
> completeness change to match the approved Phase 2 deliverable structure; the layered
> architecture, the schemas and every guarantee in section 8 are unchanged.
> See `docs/source-data-dictionary.md`.

Storage is a single DuckDB database (`data/20_warehouse/northstar.duckdb`) with Parquet
exports for anything Power BI or Excel consumes (ADR-0001). Layer separation is by schema,
not by convention: `raw`, `staging`, `warehouse`, `mart`.

**Modelling pattern: star schema with conformed dimensions.** Facts contain keys and
measures. Dimensions contain descriptive attributes and flattened hierarchies. No
snowflaking, no parent-child hierarchies, no bridge tables. The reasons are in ADR-0010, but
the short version is that flattened hierarchies over a 188-account chart and a 15-entity
tree are cheap, and parent-child hierarchies in Power BI are neither cheap nor pleasant to
maintain.

## 2. Naming and typing conventions

| Convention | Rule |
|---|---|
| Table names | `dim_*`, `fact_*`, `stg_*`, `mart_*`, `ctl_*`; singular subject, snake_case |
| Surrogate keys | `<dim>_key`, integer, generated, never business-meaningful |
| Business keys | `<dim>_code` or `<dim>_id`, preserved from source |
| Dates | ISO `date` type; `*_date` for real dates, `period_key` (`YYYYMM` integer) for month keys |
| Amounts | `DECIMAL(18,2)` for currency. **Never floating point.** |
| Rates | `DECIMAL(18,8)` |
| Percentages | `DECIMAL(9,6)` as a decimal fraction, not a whole number |
| Booleans | Real `BOOLEAN`, not `Y`/`N` strings |
| Account codes | `VARCHAR`. Kestrel's leading zeros are significant (`CTL-DQ-10`) |
| Unknown members | Explicit `-1` "Not Applicable" rows in every dimension. **No nulls in foreign keys.** |
| Deleted rows | Never. Corrections are new effective-dated rows or reversing entries |

Money is `DECIMAL`, not `DOUBLE`, because a consolidation is judged on whether it balances
to the cent and binary floating point cannot represent `0.01`. A tolerance of $1 on a
$465m balance sheet is a design choice about materiality; a tolerance forced by float
representation error is a defect.

## 3. Dimensions

### `dim_date`
| | |
|---|---|
| **Purpose** | Single conformed calendar supporting both daily journal detail and monthly consolidation |
| **Grain** | One row per calendar day |
| **Range** | 2021-01-01 to 2028-12-31 (contiguous — required for time intelligence) |
| **Key** | `date_key` (`YYYYMMDD` integer) |
| **Source** | Generated |

Key columns: `date`, `period_key`, `fiscal_year`, `fiscal_quarter`, `fiscal_month`,
`month_name`, `month_short`, `quarter_name`, `year_month_label`, `is_month_end`,
`is_quarter_end`, `is_year_end`, `days_in_month`, `prior_year_date_key`,
`prior_month_period_key`, `is_current_period`, `is_closed_period`.

Monthly facts join on the **month-end** date key. Daily journal lines join on the actual
posting date. One contiguous date dimension serves both, which keeps Power BI time
intelligence working without a second date table.

`prior_year_date_key` is materialised rather than computed, because prior-year comparison is
the most frequently evaluated calculation in the entire model and a stored offset is faster
and unambiguous across leap years.

### `dim_entity`
| | |
|---|---|
| **Purpose** | Legal entity master, ownership tree and consolidation scope |
| **Grain** | One row per legal or virtual entity |
| **Rows** | 15 (12 operating + 3 elimination) |
| **Key** | `entity_key`; business key `entity_code` |
| **Source** | `config/entities/entity_master.csv` |

Key columns: `entity_code`, `entity_name`, `short_name`, `country_code`, `region`,
`functional_currency_code`, `erp_system`, `erp_company_code`, `primary_bu_code`,
`parent_entity_code`, `ownership_pct`, `nci_pct`, `consolidation_method`, `entity_type`,
`consolidation_effective_from`, `consolidation_effective_to`, `acquisition_date`,
`acquisition_type`, `is_elimination_entity`, `legal_hierarchy_path`,
`legal_hierarchy_level`, `has_nci`, `nci_holder`, `is_active`.

Ownership **percentages** are deliberately *not* dimension attributes. They are
period-dependent, and a dimension attribute would silently apply today's percentage to a
historical period. They live in `fact_ownership_interest` instead (see below), sourced from
the effective-dated register `config/entities/ownership_history.csv`.

`legal_hierarchy_path` is the materialised ancestor path (`NIG-100/NIG-500/NIG-510`),
flattened so the tree can be traversed without recursion at query time.

**Consolidation effective dates are enforced, not decorative.** `CTL-CON-02` blocks any
period outside an entity's window.

### `dim_business_unit`
One row per business unit (5). Source `config/dimensions/business_unit.csv`. Columns:
`bu_code`, `bu_name`, `segment_type`, `description`, `is_reportable_segment`,
`reporting_sort_order`.

Business unit is held on **both** the entity (as `primary_bu_code`) and the cost centre.
Every entity except the two corporate ones sits wholly within one business unit, but cost
centres allow a future entity to span units without restructuring the model.

### `dim_cost_center`
| | |
|---|---|
| **Purpose** | Department and cost centre master, the level at which managers hold budget |
| **Grain** | One row per entity × cost centre |
| **Rows** | ~150 (generated in Phase 2 from the department catalogue × entity applicability) |
| **Key** | `cost_center_key`; business key `entity_code` + `cost_center_code` |
| **Source** | `config/dimensions/department.csv` plus generated per-entity codes |

Key columns: `cost_center_code`, `cost_center_name`, `entity_code`, `department_code`,
`department_name`, `function_group`, `cost_type` (`DIRECT`/`INDIRECT`),
`pl_destination` (`COS`/`OPEX`), `bu_code`, `is_headcount_bearing`, `manager_name`.

`pl_destination` and `function_group` are what resolve the payroll mapping splits described
in `consolidation-design.md` §5.3. They are load-bearing attributes, not documentation.

### `dim_account`
| | |
|---|---|
| **Purpose** | Group chart of accounts with reporting hierarchy and engine behaviour flags |
| **Grain** | One row per group account |
| **Rows** | 188 |
| **Key** | `account_key`; business key `group_account` |
| **Source** | `config/coa/group_coa.csv` |

Key columns: `group_account`, `account_name`, `statement`, `fs_caption_l1`,
`fs_caption_l2`, `account_class`, `normal_balance`, `fx_method`, `cash_flow_category`,
`is_intercompany`, `is_ebitda`, `is_ebitda_addback`, `is_statistical`,
`include_in_tb_balance`, `sort_order`.

The flags are behavioural. `fx_method` drives translation; `cash_flow_category` drives the
cash flow statement; `is_ebitda` and `is_ebitda_addback` drive both EBITDA definitions;
`include_in_tb_balance` drives every balancing control. Changing an account's behaviour is a
configuration change validated in CI, not a code change.

### `dim_source_account`
| | |
|---|---|
| **Purpose** | Source chart of accounts and the mapping to the group chart — the drill-back path |
| **Grain** | One row per ERP × source account × effective period |
| **Rows** | 391 |
| **Key** | `source_account_key` |
| **Source** | `config/coa/source_coa_{aurora,sable,kestrel}.csv` |

Key columns: `erp_system`, `source_account`, `source_account_name`,
`source_account_name_local`, `source_account_type`, `source_normal_balance`,
`group_account`, `mapping_type`, `mapping_rule`, `effective_from`, `effective_to`, `notes`.

This dimension is what makes "which source accounts produced this group figure?" a query
rather than an archaeology exercise. Effective dating means a closed period always
re-computes with the mapping that was in force at the time (`CTL-MAP-07`).

### `dim_currency`
One row per currency (4 plus `N/A`). Columns: `currency_code`, `currency_name`, `symbol`,
`decimal_places`, `is_reporting_currency`, `plausible_rate_min`, `plausible_rate_max`.

The plausible-rate bounds are used by `CTL-FX-05` to reject inverted quotations on load.

### `dim_scenario` and `dim_version`
Source `config/dimensions/scenario_version.csv`.

`dim_scenario`: `ACT`, `BUD`, `FC`, `PY`. `PY` is marked `scenario_type = 'DERIVED'` and has
no stored rows — it exists so that the semantic layer can present it as a first-class
scenario while the data remains a date offset over `ACT` (ADR-0004).

`dim_version`: `ACTUAL`, `BUD_FY25_V1`, `BUD_FY26_V1`, `FC_FY26_02`, `FC_FY26_05`,
`FC_FY26_08`, `FC_FY27_P1`. Columns include `parent_scenario_code`, `fiscal_year`,
`fx_rate_set`, `actual_months`, `forecast_months`, `is_default`, `is_locked`, `approved_by`,
`approved_date`, `version_hash`.

`version_hash` is stamped when a version locks. `CTL-SCN-03` recomputes it on every build,
so a locked budget cannot be quietly edited.

### `dim_layer`
| | |
|---|---|
| **Purpose** | The five consolidation layers. Makes the statutory/management separation a filter on data rather than a convention people have to remember |
| **Grain** | One row per consolidation layer |
| **Rows** | **Exactly 5** |
| **Key** | `layer_id` (1–5); business key `layer_code` |
| **Source** | `config/dimensions/consolidation_layer.csv` — the canonical definition |

| `layer_id` | `layer_code` | `layer_name` | Posted to | `in_statutory_view` | `in_management_view` | `must_balance_independently` |
|---|---|---|---|---|---|---|
| 1 | `REPORTED` | Entity Reported | Real legal entities | TRUE | TRUE | TRUE |
| 2 | `IC_ELIM` | Intercompany Eliminations | `ELIM-IC` | TRUE | TRUE | TRUE |
| 3 | `CONSOL_ADJ` | Consolidation Adjustments | `ELIM-CON` | TRUE | TRUE | TRUE |
| 4 | `MGMT_ADJ` | Management Adjustments | `ELIM-MGT` | **FALSE** | TRUE | TRUE |
| 5 | `FX_CTA` | Translation Adjustment | Real legal entities | TRUE | TRUE | **FALSE** |

Other columns: `layer_sequence`, `posting_source`, `posted_to_entity_type`,
`created_by_phase`, `description`.

```
Statutory  = layer_id IN (1,2,3,5)
Management = layer_id IN (1,2,3,4,5)
```

**This dimension is closed.** The layer set is fixed at five; adding a sixth is a breaking
change requiring an ADR, because both reporting bases are defined by explicit layer
membership and a new layer would belong to neither until someone remembered to add it.
`CTL-CON-09` rejects any fact row carrying a `layer_id` outside the configured set, and
`tests/test_config_integrity.py` asserts that the configuration, the documented statutory and
management formulas, and every layer reference in the documentation all agree.

`layer_id 5` is the only layer that does not balance independently: it *is* the balancing
entry that makes the translated trial balance sum to zero. Balancing controls must therefore
read `must_balance_independently` rather than assume every layer self-balances.

### `dim_intercompany_partner`
A **role-playing dimension over `dim_entity`**, plus one `EXTERNAL` member and one
`NOT_APPLICABLE` member. Not a copy of the entity table — a view over it with renamed
columns, so an entity's attributes cannot drift between its two roles.

Every fact row has an `ic_partner_key`. Non-intercompany rows point at `EXTERNAL`, which
means "revenue to external customers" is a filter rather than a `NOT IN` subquery.

### `dim_customer`
| | |
|---|---|
| **Purpose** | Customer analytics on the revenue detail fact |
| **Grain** | One row per customer |
| **Rows** | ~1,200 (generated) |
| **Key** | `customer_key`; business key `customer_code` |

Columns: `customer_name`, `customer_group_code`, `customer_group_name`, `industry_sector`,
`country_code`, `region`, `channel`, `first_order_date`, `is_key_account`, `is_active`.

`customer_group_code` supports parent-level concentration analysis, which is the question a
board actually asks ("how much of our revenue depends on one relationship?") as opposed to
the one a naive model answers ("how much comes from this billing entity?").

### `dim_product_service`
~250 rows. Columns: `product_code`, `product_name`, `product_family`, `product_line`,
`bu_code`, `revenue_type` (`PRODUCT`/`SERVICE`/`PROJECT`/`PARTS`),
`recognition_method` (`POINT_IN_TIME`/`OVER_TIME`), `is_aftermarket`, `standard_margin_pct`.

### `dim_adjustment`
| | |
|---|---|
| **Purpose** | Metadata for every consolidation and management adjustment — the audit trail |
| **Grain** | One row per adjustment |
| **Key** | `adjustment_key`; business key `adjustment_id` |

Columns: `adjustment_id`, `adjustment_type`, `layer_code`, `description`, `rationale`,
`prepared_by`, `prepared_date`, `approved_by`, `approved_date`, `is_recurring`,
`is_reversing`, `reversal_period_key`, `effective_from_period`, `effective_to_period`,
`supporting_reference`.

Adjustment **amounts** live in `fact_financials`; only metadata lives here. That way an
adjustment aggregates naturally with everything else instead of needing to be unioned in.

### `fact_ownership_interest`
| | |
|---|---|
| **Purpose** | The ownership and non-controlling interest percentage in force for each entity in each period |
| **Grain** | entity × period |
| **Rows** | ~800 |
| **Key** | `entity_key`, `period_key` |
| **Source** | Generated by expanding the effective-date ranges in `config/entities/ownership_history.csv` across periods |

Columns: `group_ownership_pct`, `nci_pct`, `consolidation_method`, `change_event`,
`is_first_period`, `is_final_period`.

Strictly this is a periodic-snapshot fact rather than a transaction fact, and it holds
percentages rather than additive measures. It is modelled as a fact anyway because it is
**period-dependent**, and the alternative — an ownership attribute on `dim_entity` — would
silently apply today's percentage to a historical period.

Populated for **every** entity and period, not only where NCI exists; wholly owned entities
carry 100/0. A control that only runs where NCI exists cannot detect an NCI appearing where
it should not (`CTL-CON-10`).

### Supporting dimensions
| Dimension | Grain | Purpose |
|---|---|---|
| `dim_geography` | Country | Country, region, sub-region for geographic reporting |
| `dim_erp_system` | ERP | Source system attributes and conventions |
| `dim_asset_class` | Asset class | Capex and depreciation analysis; useful life; finance-lease flag |
| `dim_debt_instrument` | Instrument | Facility, currency, rate basis, margin, maturity, covenant applicability |
| `dim_job_family` | Job family | Headcount analysis by role band |
| `dim_control` | Control | The control register as a queryable dimension |

## 4. Facts

### `fact_financials` — the core fact
| | |
|---|---|
| **Purpose** | Every financial and statistical amount, all scenarios, all consolidation layers |
| **Grain** | entity × account × cost centre × ic partner × period × scenario × version × layer |
| **Grain note** | `related_entity_key` and `adjustment_key` are **attributes of a layer-3/4 row, not grain components** — they are functionally determined by the other keys and never split a row |
| **Estimated rows** | ~1.1m (Actual ~420k; Budget ~180k; Forecast versions ~380k; eliminations and adjustments ~120k) |
| **Source** | Consolidation engine (Phase 4) |

| Column | Type | Notes |
|---|---|---|
| `entity_key` | int | |
| `account_key` | int | |
| `cost_center_key` | int | |
| `ic_partner_key` | int | `EXTERNAL` where not intercompany |
| `period_key` | int | `YYYYMM` |
| `date_key` | int | Month-end, for time intelligence |
| `scenario_key` | int | |
| `version_key` | int | |
| `layer_id` | int | 1–5, from `dim_layer`. Never null (`CTL-CON-09`) |
| `currency_key` | int | The entity's functional currency |
| `adjustment_key` | int | Populated for layers 3 and 4 only |
| `related_entity_key` | int | The subsidiary an adjustment **relates to**, where `entity_key` is a virtual entity. Populated for layers 3 and 4; `NOT_APPLICABLE` otherwise |
| `amount_local` | decimal(18,2) | Functional currency |
| `amount_usd` | decimal(18,2) | Translated per the FX policy |
| `amount_usd_cc` | decimal(18,2) | Constant currency, at budget rates |
| `quantity` | decimal(18,4) | Statistical accounts only |
| `source_system` | varchar | Provenance |
| `load_batch_id` | varchar | Provenance |

Three amount columns rather than one: see `consolidation-design.md` §6.5. Storing the
constant-currency amount costs one column and removes a rate join from every variance
visual in the platform.

**Partitioned by `period_key`.** Almost every query filters on period; partitioning there
is the single highest-value physical decision.

### `fact_journal_line`
| | |
|---|---|
| **Purpose** | Transaction-level actuals for drill-through and audit |
| **Grain** | One row per source journal line |
| **Estimated rows** | ~1.5m across 45 months and 12 entities |
| **Source** | ERP extracts (Phase 2), normalised (Phase 3) |

Columns include `journal_id`, `line_number`, `posting_date`, `document_date`,
`document_reference`, `document_type`, `description`, `entity_key`, `source_account_key`,
`account_key`, `cost_center_key`, `ic_partner_key`, `customer_key`, `vendor_reference`,
`project_code`, `amount_local`, `amount_usd`, `created_by`, `is_adjustment_period`,
`source_period`.

Actuals only. Budget and forecast have no transactions. `is_adjustment_period` flags
Kestrel periods 13–16.

### `fact_revenue_detail`
| | |
|---|---|
| **Purpose** | Customer and product analytics, reconciled to the GL |
| **Grain** | entity × customer × product × period × scenario × version |
| **Estimated rows** | ~380k |

Measures: `revenue_local`, `revenue_usd`, `revenue_usd_cc`, `cost_of_sales_usd`,
`gross_profit_usd`, `quantity`, `order_count`, `is_intercompany`.

Reconciled to `fact_financials` revenue accounts by `CTL-REC-02`. If the two disagree, the
analytics and the accounts are telling different stories and the analytics lose.

### `fact_fx_rate`
| | |
|---|---|
| **Grain** | currency × period × rate type × rate set |
| **Rows** | ~1,500 |

Columns: `currency_key`, `period_key`, `rate_type` (`AVG`/`CLOSE`/`HIST`), `rate_set`
(`ACTUAL`/`BUDGET`/`FORECAST`), `rate_usd_per_unit`, `rate_source`, `is_locked`.

Rates are stored **only** as USD per one unit of foreign currency (`CTL-FX-05`). A separate
`fact_fx_rate_historical` holds entity- and event-specific historical rates for equity
translation, keyed on entity, account and event date.

### `fact_headcount`
Grain: entity × cost centre × job family × period × scenario × version. Measures:
`fte_opening`, `hires`, `leavers`, `transfers_in`, `transfers_out`, `fte_closing`,
`fte_average`, `contractor_fte`, `voluntary_leavers`.

A movement fact rather than a snapshot, because attrition and hiring velocity are questions
the board asks and a closing-balance-only fact cannot answer them.

### `fact_capex`
Grain: entity × cost centre × asset class × project × period × scenario × version.
Measures: `additions`, `disposals_cost`, `disposals_accumulated_depreciation`,
`depreciation`, `impairment`, `fx_movement`, `closing_net_book_value`, `commitments`.
Reconciled to the balance sheet by `CTL-REC-04`.

### `fact_debt_schedule`
Grain: instrument × period × scenario × version. Measures: `opening_principal`, `drawings`,
`scheduled_repayments`, `voluntary_prepayments`, `fx_movement`, `closing_principal`,
`average_daily_drawn`, `average_daily_undrawn`, `interest_rate`, `interest_expense`,
`commitment_fee`, `unamortised_fees`, `undrawn_commitment`.

The average balance is a **daily** average, not the mean of two month ends. Interest accrues
on the daily drawn balance and the commitment fee on the daily undrawn commitment, so the two
cannot be reconciled to the recorded charge without it (`CTL-FS-10`). The source layer
supplies it in `data/reference/revolver_utilisation.csv`, resolved with the borrowing-notice
and collections-sweep dates in `config/debt/treasury_policy.csv`.

Covenant metrics are computed from this fact and reconciled to the balance sheet
(`CTL-REC-05`). Modelling debt at instrument level rather than as one balance sheet line is
what makes "what happens when the swap matures in December 2026?" answerable.

### `fact_cta_expectation`
Grain: entity × period. A **source-layer expectation**, loaded from
`data/reference/cta_expectation.csv` and never written by the consolidation engine. Measures:
`opening_net_assets_local`, `closing_net_assets_local`, `result_local`,
`equity_movement_local`, `opening_rate`, `closing_rate`, `average_rate`,
`cta_on_opening_net_assets`, `cta_on_result`, `cta_on_equity_movements`,
`cta_movement_usd_m`, `cta_cumulative_usd_m`.

Its only purpose is to be the thing the layer-5 CTA is tested against (`CTL-FX-12`). It is
computed from source balances and the approved rate file before any translation runs, so an
engine compared to it is genuinely compared to something. It carries no group target and must
never be joined into a reporting measure.

### `fact_intercompany_matching`
Grain: entity pair × account × period × currency. A **derived control fact** produced by the
elimination engine. Measures: `seller_amount_usd`, `buyer_amount_usd`, `difference_usd`,
`match_status`, `difference_reason`, `days_outstanding`.

Materialised rather than computed on the fly so that mismatches can be **aged**
(`CTL-IC-03`). Chronic mismatches, not one-month timing noise, are what actually goes wrong.

### `fact_cash_flow`
Grain: entity × cash flow line × period × scenario × version. Derived output of the cash
flow engine. Measures: `amount_usd`, `amount_usd_cc`.

Held as its own fact because cash flow lines do not map one-to-one onto accounts — a single
account movement can split across categories, and several accounts collapse into one line.

### `fact_control_result`
Grain: control × run × entity × period. Measures: `measured_value`, `threshold_value`,
`variance`, `status` (`PASS`/`WARN`/`FAIL`), `executed_at`, `run_id`, `detail_json`.

Control results are **data**, which is what makes a controls dashboard and a control history
possible. A control that runs but is not recorded cannot be trended, and a control that
cannot be trended cannot demonstrate that the close is improving.

## 5. Relationships

```
dim_date ──┬──< fact_financials >──┬── dim_entity ──── dim_business_unit
           │                       ├── dim_account
           │                       ├── dim_cost_center
           │                       ├── dim_intercompany_partner (role-play → dim_entity)
           │                       ├── dim_scenario
           │                       ├── dim_version
           │                       ├── dim_layer
           │                       ├── dim_currency
           │                       └── dim_adjustment
           ├──< fact_journal_line >── dim_source_account, dim_entity, dim_account, ...
           ├──< fact_revenue_detail >── dim_customer, dim_product_service, dim_entity
           ├──< fact_fx_rate >── dim_currency
           ├──< fact_headcount >── dim_entity, dim_cost_center, dim_job_family
           ├──< fact_capex >── dim_entity, dim_asset_class
           ├──< fact_debt_schedule >── dim_debt_instrument
           ├──< fact_ownership_interest >── dim_entity
           ├──< fact_cash_flow >── dim_entity
           └──< fact_control_result >── dim_control, dim_entity
```

All relationships are single-direction, one-to-many, from dimension to fact. No
bidirectional filters and no many-to-many. Where a measure must cross facts — headcount
against revenue, for example — it does so through the conformed `dim_entity`,
`dim_cost_center` and `dim_date`, which is exactly what conformed dimensions are for.

## 6. Reporting hierarchies

| Hierarchy | Levels |
|---|---|
| Organisation | Group → Business Unit → Legal Entity → Department → Cost Centre |
| Account | Statement → FS Caption L1 → FS Caption L2 → Group Account |
| Geography | Region → Country → Entity |
| Time | Year → Quarter → Month |
| Legal | Topco → Subsidiary → Sub-subsidiary |
| Customer | Customer Group → Customer |
| Product | Business Unit → Product Family → Product Line → Product |

The organisation hierarchy is the one the brief requires for drilldown. It is **flattened
onto the dimensions** rather than held as a recursive structure, so `Group → BU → Entity →
Department → Cost Centre → Account Category → GL Account` is a straightforward drill path
across `dim_entity`, `dim_cost_center` and `dim_account`.

## 7. Data volume

| Table | Estimated rows | Rationale |
|---|---|---|
| `fact_journal_line` | ~1,500,000 | 12 entities × 45 months × ~2,800 lines/month. Enterprise-realistic without being gratuitous. |
| `fact_financials` | ~1,100,000 | The consolidation grain across three scenarios and five layers |
| `fact_revenue_detail` | ~380,000 | |
| `fact_headcount` | ~95,000 | |
| `fact_capex` | ~60,000 | |
| `fact_cash_flow` | ~25,000 | |
| `fact_debt_schedule` | ~2,000 | |
| `fact_fx_rate` | ~1,500 | |
| `fact_cta_expectation` | ~250 | Source-layer expectation; foreign entities only |
| `fact_ownership_interest` | ~800 | Entity × period ownership, all entities |
| All dimensions | ~2,000 | |
| **Total** | **~3.2m rows** | |

This is sized to look and behave like a real mid-market implementation: large enough that
naive queries are visibly slow and the physical design has to be right, small enough to
rebuild end to end in minutes and to fit comfortably in a Power BI import model. Volume for
its own sake would prove nothing.

Target build performance: full rebuild from raw extracts to published marts in under five
minutes on a laptop.

## 8. Contract guarantees

Downstream consumers may rely on the following. Breaking any of them is a breaking change
requiring a version bump and an ADR:

1. `fact_financials` is unique on its declared grain (`CTL-DQ-04`).
2. Every foreign key resolves; no nulls in key columns (`CTL-DQ-08`).
3. `amount_usd` is translated per the documented FX policy and never re-derived downstream.
4. `layer_id` is always populated and always one of the five values in `dim_layer`
   (`CTL-CON-09`). Statutory results are `layer_id IN (1,2,3,5)`; the management view is
   `layer_id IN (1,2,3,4,5)`. The layer set is closed — adding a sixth is a breaking change.
5. Ownership percentages come from `fact_ownership_interest` for the period, never from a
   dimension attribute. Every entity and period has exactly one row (`CTL-CON-10`).
6. Statistical accounts (`is_statistical = TRUE`) carry `quantity`, and their `amount_usd`
   is null. They are never included in a balancing test.
7. Prior year is a date offset over `ACT`; there are no stored `PY` rows.
8. `period_key` is `YYYYMM` and monthly facts join `dim_date` on the month-end date key.
9. Versions flagged `is_reserved = TRUE` (currently the Downside stress case) are excluded
   from every default reporting view (`CTL-SCN-06`).
10. No blocking control has failed for any period present in a published mart.
