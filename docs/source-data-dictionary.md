# Source Data Dictionary

Every dataset Phase 2 produces: its purpose, grain, row count, format and columns.

Regenerate everything with `python -m src.generation.build` (about 25 seconds). Bulk
artefacts are not committed; see `docs/synthetic-data-methodology.md` §8.

| Dataset | Rows | Format | Committed |
|---|---|---|---|
| Native ERP extracts (507 files) | 1,082,408 lines | CSV, per-ERP conventions | samples only |
| `journal_lines.parquet` | 1,082,408 | Parquet | sample only |
| `plan_fact.parquet` | 26,124 | Parquet | no |
| `headcount_fact.parquet` | 20,973 | Parquet | no |
| `revenue_detail.parquet` | 50,045 | Parquet | no |
| `fixed_assets.csv` | 1,755 | CSV | yes |
| `capex_projects.csv` | 1,755 | CSV | yes |
| `debt_schedule.csv` | 595 | CSV | yes |
| `employees.csv` | 3,049 | CSV | yes |
| `customers.csv` | 998 | CSV | yes |
| `products.csv` | 226 | CSV | yes |
| `cost_centres.csv` | 152 | CSV | yes |
| `fx_rates_monthly.csv` | 544 | CSV | yes |
| `fx_rates_historical.csv` | 36 | CSV | yes |
| `expected_mapping_manifest.csv` | 313 | CSV | yes |
| `phase02_source_layer_targets.csv` | 35 | CSV | yes |

---

## 1. Native ERP extracts — `data/raw/{aurora,sable,kestrel}/`

One file per entity per period. Column layouts, encodings, delimiters, sign conventions and
locale rules differ by system and are documented in
[`source-system-design.md`](source-system-design.md). Nothing here is normalised.

**Grain**: one row per journal line.
**Naming**: `<SYSTEM>_<TABLE>_<company code>_<YYYYMM>.csv`

---

## 2. `journal_lines.parquet` — the normalised mirror

The same 1,082,408 lines in one typed table, plus the **expected group account** each line
must map to. This is the fixture Phase 3 is graded against; it is *not* an input to any
source system.

| Column | Type | Notes |
|---|---|---|
| `entity_code` | text | `NIG-200` |
| `erp_system` | text | `AURORA` / `SABLE` / `KESTREL` |
| `erp_company_code` | text | as it appears in the native extract |
| `period_key` | int | `YYYYMM`, 202301–202608 |
| `journal_id` | text | unique within entity and period |
| `line_number` | int | |
| `posting_date` | date | weekday-biased within the period |
| `document_reference` | text | `INV-…`, `PI-…`, `CR-…` |
| `document_type` | text | `SI`, `CN`, `PI`, `PY`, `CR`, `PM`, `FA`, `IC`, `OB`, `CL` |
| `event_type` | text | the economic event, e.g. `SALES_INVOICE`, `PAYROLL_ACCRUAL` |
| `description` | text | |
| `source_account` | text | **as posted in the source system**; Kestrel keys keep leading zeros |
| `expected_group_account` | text | **what Phase 3's mapping must produce** |
| `cost_center_code` | text | joins `cost_centres.csv` |
| `department_code` | text | `D100` … `D950` |
| `dept_function` | text | `PRODUCTION`, `FIELD`, `PROJECT`, `INDIRECT_OPS`, `SGA` |
| `currency_code` | text | entity functional currency |
| `amount_local` | decimal | **debit positive**; every journal sums to zero |
| `ic_partner_code` | text | counterparty entity, on both legs; blank if external |
| `customer_code` | text | sales invoices only |
| `product_code` | text | |
| `line_attributes` | text | `key=value;…` — the attributes a conditional split must read |

`line_attributes` is the load-bearing column for Phase 3. A payroll line carrying
`dept_function=PRODUCTION` must map to direct labour; the same account carrying
`dept_function=SGA` must map to operating expense.

**Special rows**: `event_type = OPENING_BALANCE` establishes each entity's opening balance
sheet in its first period, so an extract is self-contained rather than movement-only.
`event_type = YEAR_END_CLOSE` closes the income statement into reserves each December — it
must be **excluded** when aggregating a year's result, or every income statement nets to nil.

---

## 3. `plan_fact.parquet` — budget and forecast

**Grain**: scenario × version × entity × period × group account × cost centre.

| Column | Notes |
|---|---|
| `scenario_code` | `BUD` / `FC` |
| `version_code` | `BUD_FY26_V1`, `FC_FY26_02`, `FC_FY26_05`, `FC_FY26_08` |
| `entity_code`, `period_key`, `cost_center_code`, `currency_code` | |
| `group_account` | account requested by the planner |
| `expected_group_account` | after any ERP substitution, so it compares to the ledger |
| `amount_local` | |
| `is_actual_month` | `TRUE` for the actual months inside a forecast version |

The two superseded forecasts were issued before the European softness and the Vector
slippage were recognised, so they sit between budget and outturn — which is what makes
forecast accuracy measurable rather than asserted. The reserved Downside scenario
(`DS_FY26_STRESS`) is deliberately **not populated** (`P2-CMP-04`).

---

## 4. `headcount_fact.parquet`

**Grain**: entity × cost centre × job family × period. Derived from the employee master's
own hire and termination dates, so it cannot disagree with it.

Columns: `fte_opening`, `hires`, `leavers`, `fte_closing`, `fte_average`,
`headcount_closing`, `annual_base_salary_local`, `currency_code`.

---

## 5. `employees.csv`

**Grain**: one row per employee. 3,049 people across twelve entities.

`employee_id`, `entity_code`, `cost_center_code`, `department_code`, `bu_code`,
`country_code`, `currency_code`, `job_family_code`, `job_family_name`,
`employment_status`, `employment_type`, `fte`, `hire_date`, `termination_date`,
`annual_base_salary_local`, `benefits_rate_pct`, `bonus_eligible`, `bonus_target_pct`.

**No names.** Each employee is an opaque identifier. Salaries are drawn from job-family
midpoints scaled by a country pay index and a normal band, so the distribution is realistic
without any individual being derivable.

---

## 6. `customers.csv` and `products.csv`

Customers carry a `customer_group_code` so parent-level concentration is analysable — the
question a board actually asks. The top 10 groups take 37.3% of FY2025 revenue and the top
25 take 53.6%, a realistic industrial concentration curve rather than a flat distribution.

`payment_terms_days` varies per customer (30/45/60/75/90), so receivables ageing is not
uniform.

Products carry `revenue_type`, `recognition_method` and `standard_margin_pct`, which is what
drives cost of sales in the revenue detail.

---

## 7. `revenue_detail.parquet`

**Grain**: entity × customer × product × period × group account.

Reconciles **exactly** to the general ledger's external revenue accounts for every entity
and period — control `P2-REC-01`, which implements ADR-0008's requirement that the detail
fact and the ledger never tell different stories.

Measures: `revenue_local`, `cost_of_sales_local`, `quantity`, `order_count`,
`is_intercompany`.

---

## 8. `capex_projects.csv` and `fixed_assets.csv`

Capital projects generate the fixed asset register: every asset carries the `project_id`
that funded it, its `asset_class`, `in_service_date`, `useful_life_years` and
`depreciation_method`. Total asset cost equals total project spend (`P2-REC-03`).

Asset classes and lives: buildings 30 years, plant 10, vehicles 6, IT 4, leasehold
improvements 8, finance lease right-of-use 6.

This is what will let Phase 4 reconcile **capex → fixed assets → depreciation → cash flow**.
Phase 2 builds the source data capable of supporting that; it does not build the
reconciliation.

---

## 9. `debt_schedule.csv`

**Grain**: instrument × period. Deliberately *not* a single balance sheet line — that is
what makes covenant leverage, economic leverage, interest forecasting, maturity analysis
and liquidity analysis possible.

`instrument_id`, `instrument_name`, `borrower_entity`, `instrument_type`, `group_account`,
`currency_code`, `period_key`, `opening_principal`, `drawings`, `repayments`,
`closing_principal`, `interest_rate_basis`, `rate_type`, `is_hedged`,
`hedge_notional_usd`, `hedge_maturity`, `maturity_date`, `interest_expense_local`,
`commitment_fee_local`, `unamortised_fees`, `undrawn_commitment`,
`counts_toward_covenant_debt`, `covenant_reference`.

Instruments: the 2021 Term Loan B and the revolving facility at Topco, plus per-entity
finance leases. `covenant_reference` points at the clause in
`config/debt/credit_agreement_terms.csv` that brings each instrument into covenant debt, and
`hedge_maturity` carries the December 2026 swap expiry that the board pack has to surface.

---

## 10. `fx_rates_monthly.csv` and `fx_rates_historical.csv`

**Grain**: currency × period × rate type × rate set.

| Column | Notes |
|---|---|
| `rate_usd_per_unit` | **always USD per one unit of foreign currency** (FX-P15) |
| `rate_set` | `ACTUAL`, `BUDGET` (flat, locked), `FORECAST` |
| `rate_type` | `AVG`, `CLOSE` |
| `base_currency`, `quote_convention`, `source`, `effective_month` | documented on every row |

The mean of the twelve monthly average rates equals the annual anchor exactly, and December's
closing spot equals the annual closing anchor exactly. Between those constraints the path is
a seeded Brownian bridge, so it has economic shape rather than being noise around a mean.

`fx_rates_historical.csv` carries the entity- and event-specific rates equity translation
needs (FX-P03/FX-P16), including the acquisition-date spots for 2023-04-01 and 2024-07-01.

Phase 2 produces rates only. **No translation is performed** — that is Phase 4.

---

## 11. `cost_centres.csv`

**Grain**: entity × cost centre. `dept_function` and `pl_destination` are load-bearing, not
documentation: they are what resolve the conditional payroll splits in all three source
charts.

---

## 12. Reproducibility and control artefacts

| File | Contents |
|---|---|
| `data/build_manifest.json` | Row counts, the investment calibration, and a SHA-256 for each of the 520 generated files |
| `data/samples/build_digest.txt` | One digest over all checksums — the reproducibility fingerprint |
| `data/phase02_control_results.csv` | All 57 source controls with measured value, threshold and status |
| `data/faults/expected_results.json` | The ten fault fixtures and the control each must trip |
| `data/samples/*.csv` | Extract samples from all three systems, plus a journal line sample |
| `config/generation/expected_mapping_manifest.csv` | The mapping fixture Phase 3 is graded against |
| `config/anchors/phase02_source_layer_targets.csv` | The anchor bridge: consolidated → source layer |
