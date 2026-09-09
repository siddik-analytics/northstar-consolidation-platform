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
| `dept_function` | text | `PRODUCTION`, `FIELD`, `PROJECT`, `INDIRECT_OPS`, `SGA`. Delivery functions are the ones that are billable or absorbed into a unit cost: `D200` and `D205` are `FIELD`, while `D210 Equipment & Fleet` and `D215 Field Safety & Compliance` **support** field operations and are `INDIRECT_OPS`, which is what the department master's own `cost_type` and the approved Aurora split have always said |
| `currency_code` | text | entity functional currency |
| `amount_local` | decimal | **debit positive**; every journal sums to zero |
| `ic_partner_code` | text | counterparty entity, on **every** posting to an intercompany account — the invoice, the settlement, the treasury current account, the loan and the investment in a subsidiary. Blank only on an external posting and on the year-end close, which is a position rather than a transaction with anyone |
| `customer_code` | text | sales invoices only |
| `product_code` | text | |
| `line_attributes` | text | `key=value;…` — the attributes a conditional split must read |

`line_attributes` is the load-bearing column for Phase 3. A payroll line carrying
`dept_function=PRODUCTION` must map to direct labour; the same account carrying
`dept_function=SGA` must map to operating expense.

**Every** journal type carries them — the conversion journal that establishes an opening
balance, the year-end close, and Kestrel's special-period adjustments as well as ordinary
transactions. Three of those four wrote an empty attribute string until Phase 3.1
(defect P2-D-01), and a posting to a conditional account that carries none of the fields its
rules read cannot be classified from what it contains.

The declared attribute and the cost centre the line sits in are **two views of one fact and
always agree**. A line declaring `dept_function=PRODUCTION` is posted to a cost centre whose
department carries that function; where an entity has no such department the cost is not
allocated there at all. They disagreed on 5,710 lines until Phase 3.1 (defect P2-D-02), which
cost nothing in the reported figures and everything in the dimension's ability to corroborate
the mapping.

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
`depreciation_method`. Total asset cost equals total project spend (`P2-REC-03`), and it
reconciles project by project as well as in total (`P7-CPX-07`).

`project_id` is the business key of a capital project and carries the grain that makes one
distinct:

    CP-{entity}-{period}-{asset_class}-{sequence}     e.g. CP-200-202505-PLANT-01

The asset class is in the identifier because the sequence restarts inside each class. Without
it, every class in an entity-month reissued `-01` and 1,846 projects shared 395 identifiers —
defect **P6-D-01**, corrected under [ADR-0026](adr/0026-a-declared-key-is-a-contract.md). The
uniqueness is now proved on every build rather than assumed from the format
([the key and grain framework](key-and-grain-framework.md)).

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
`counts_toward_covenant_debt`, `covenant_reference`, `average_daily_drawn`,
`average_daily_undrawn`, `movement_day`, `days_in_month`.

Instruments: the 2021 Term Loan B and the revolving facility at Topco, plus per-entity
finance leases. `covenant_reference` points at the clause in
`config/debt/credit_agreement_terms.csv` that brings each instrument into covenant debt, and
`hedge_maturity` carries the December 2026 swap expiry that the board pack has to surface.

Balances are **read from the general ledger**, not interpolated between anchored year ends, so
`opening + drawings − repayments = closing` is the ledger's own arithmetic and `P2-DBT-03`
tests the schedule against the ledger month by month. `interest_rate_basis` names the
components rather than a blended rate: the term loan is 50% swapped at 3.00% plus 425bps with
the balance floating at SOFR plus 425bps (CA-003, CA-008, CA-034); the revolver is SOFR plus
425bps on the daily drawn balance (CA-033). The four utilisation columns carry the daily
position the charge accrues on — see `revolver_utilisation.csv` at §9e.

---

## 9a. `investment_register.csv` and `investment_rollforward.csv`

`config/entities/investment_register.csv` is **configuration**: the eleven ownership events in
the group's history, each an actual transaction rather than a modelling assumption.

`investment_id`, `parent_entity`, `subsidiary_entity`, `event_date`,
`consolidation_effective_date`, `event_type`, `ownership_pct_acquired`,
`cumulative_ownership_pct`, `consideration_currency`, `consideration_local`,
`consideration_usd_m`, `carrying_currency`, `notes`.

`event_type` is one of `PLATFORM_ACQUISITION`, `ACQUISITION`, `ACQUIRED_WITH_PARENT`,
`FORMATION` or `CARVE_OUT`. `event_date` and `consolidation_effective_date` are **separate**
columns and genuinely differ: the Northstar Parts UK acquisition completed on 31 December
2022, so its investment and the resulting NCI sit in the group's opening balance sheet while
its results consolidate from 1 January 2023.

`data/reference/investment_rollforward.csv` is the generated roll-forward that Phase 4's
investment elimination consumes.

**Grain**: parent × subsidiary × period. 463 rows.

`parent_entity`, `subsidiary_entity`, `period_key`, `opening_cost_usd`, `additions_usd`,
`disposals_usd`, `closing_cost_usd`, `ownership_pct`, `nci_pct`, `carrying_currency`,
`event_type`, `investment_id`, `first_consolidated_period`.

Every ledger balance in every month reconciles to `closing_cost_usd` (`P2-INV-01`). There is
no calibration and no plug: a balance is the sum of the considerations actually paid, and it
steps on acquisition dates rather than drifting between year ends. See §3.6 of the
methodology.

---

## 9b. `cta_expectation.csv`

**Grain**: foreign entity × period. 243 rows. The **expected result** for the Phase 5
translation engine, computed from source balances and the approved rate file alone. It
replaces `translation_difference.csv`, which disclosed a residual that no longer exists
(ADR-0016 superseded by ADR-0017).

| Column | Notes |
|---|---|
| `entity_code`, `period_key`, `currency_code` | USD-functional entities generate no CTA and do not appear |
| `opening_net_assets_local`, `closing_net_assets_local` | net assets in the entity's own currency. Closing = opening + result + equity movements, exactly |
| `result_local` | the month's result in local currency |
| `equity_movement_local` | contributions and distributions dated in the month, credit-positive |
| `opening_rate`, `closing_rate`, `average_rate` | the prior closing spot, this month's closing spot, and the monthly average |
| `cta_on_opening_net_assets` | opening net assets × (closing − prior closing) |
| `cta_on_result` | result × (closing − average) |
| `cta_on_equity_movements` | equity movements × (closing − transaction rate) |
| `cta_movement_usd_m`, `cta_cumulative_usd_m` | the movement and the running balance |

Every row is reconstructible from the three balances and the three rates in it (`P2-FX-03`).
Phase 5's translation engine must reproduce this table; it is never given it.

## 9c. `layer1_equity_bridge.csv`

**Grain**: fiscal year. 3 rows. The proof that the layer-1 balance sheet closes without a plug.

| Column | Notes |
|---|---|
| `opening_equity_usd_m` | prior year's closing layer-1 equity, translated at closing rates |
| `result_for_the_year_usd_m` | local results at the monthly average rates |
| `share_based_compensation_usd_m` | equity-settled, credited to `315100` |
| `capital_contributed_usd_m` | at the rate on the contribution date |
| `equity_acquired_usd_m` | equity an entity brought with it on the date it joined the group |
| `distributions_usd_m` | to the non-controlling shareholder, at the payment-date rate |
| `cta_movement_usd_m` | the computed translation adjustment, from `cta_expectation.csv` |
| `closing_equity_rolled_usd_m`, `closing_equity_generated_usd_m` | the roll-forward, and what the ledgers actually say |
| `unexplained_usd_m` | **nil.** `P2-EQ-01` fails the build if it is not |
| `anchor_layer1_equity_target_usd_m` | derived by `targets.py` from the approved anchors |
| `variance_vs_anchor_usd_m` | **nil.** `P2-EQ-02` fails the build if it is not |

The columns are fixed and asserted: a line here that is not a transaction or the computed CTA
would be the measurement reserve returning under a new name.

## 9d. `cta_group_bridge.csv`

**Grain**: fiscal year. 3 rows. The bridge from the layer-1 CTA to the anchored consolidated
CTA roll-forward, and the statement that supersedes the provisional Phase 1 target.

| Column | Notes |
|---|---|
| `layer1_cta_movement_usd_m` | the total from `cta_expectation.csv` |
| `fx_on_goodwill_usd_m`, `fx_on_intangibles_usd_m` | retranslation of layer-3 balances that exist in no source ledger. The only estimates left in the CTA |
| `nci_share_of_cta_usd_m` | 20% of the adjustment arising in NIG-510 |
| `movement_in_unrealised_profit_usd_m` | the layer-3 elimination's movement |
| `derived_group_cta_movement_usd_m` | the sum of the above |
| `anchored_group_cta_movement_usd_m`, `derivation_variance_usd_m` | the anchor, and the variance. **Nil** (`P2-FX-02`) |
| `anchored_cta_closing_usd_m` | the closing balance the roll-forward carries |

## 9e. `revolver_utilisation.csv`

**Grain**: period. 44 rows, one per month from January 2023 to August 2026. The facility
resolved to a daily balance, which is what interest and the commitment fee accrue on.

| Column | Notes |
|---|---|
| `period_key`, `instrument_id` | `RCF-2021`, the 2021 revolving credit facility |
| `opening_drawn`, `drawings`, `repayments`, `closing_drawn` | USD. `opening + drawings − repayments = closing` to the cent (`P2-DBT-01`), chained month to month without a break. A month draws or repays, never both |
| `movement_day` | day 3 for a drawing (the borrowing-notice date, CA S2.3(a)); day 25 for a repayment (the collections sweep, treasury policy TP-009) |
| `days_in_month`, `average_daily_drawn`, `average_daily_undrawn` | the step-function average, exact rather than approximated |
| `commitment_usd`, `utilisation_pct`, `headroom_usd` | against the $60.0m commitment (CA-006) |
| `commitment_fee_accrued` | 50bps (CA-007) on the average daily undrawn, actual/365 |

The annual total of `average_daily_drawn` **is** the `RCF_AVG_DRAWN` anchor. It is derived by
`tools/derive_anchor_inputs.py`, not asserted alongside this table. See ADR-0018.

---

## 9f. `ic_inventory_transactions.csv` and `ic_inventory_holdings.csv`

Source support for the Phase 4 unrealised profit elimination. **Phase 2 does not eliminate
anything** — these datasets exist so Phase 4 can compute the elimination from evidence rather
than from an assumption.

`ic_inventory_transactions.csv` — **grain**: intercompany goods flow × period. 173 rows.

`ic_transaction_id`, `period_key`, `seller_entity`, `buyer_entity`, `product_category`,
`transfer_price_seller_local`, `seller_currency`, `seller_cost_local`,
`ic_gross_profit_seller_local`, `ic_margin_pct`, `transfer_price_buyer_local`,
`buyer_currency`, `transfer_price_usd`, `ic_gross_profit_usd`, `quantity`,
`buyer_inventory_account`.

`ic_inventory_holdings.csv` — **grain**: holding period × flow × **surviving FIFO purchase
layer**. 470 rows.

`holding_period`, `transaction_period`, `months_held`, `seller_entity`, `buyer_entity`,
`inventory_category`, `buyer_inventory_account`, `transfer_price_usd`, `seller_cost_usd`,
`ic_gross_profit_usd`, `ic_margin_pct`, `quantity_transferred`, `pct_remaining`,
`quantity_remaining`, `value_remaining_usd`, `value_remaining_buyer_local`, `buyer_currency`,
`unrealised_profit_usd`, `months_on_hand`.

One row per surviving layer rather than one per month end, so Phase 4 can eliminate at the
margin actually earned on each layer instead of at a blended rate. Goods are consumed
first-in-first-out over the flow's months-on-hand, so a closing holding is a function of
recent purchases rather than a percentage of the balance. Source inventory is carried **gross**
of unrealised profit; the anchor bridge adds PUP back to the inventory target accordingly.

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
| `data/phase02_control_results.csv` | All 79 source controls with measured value, threshold and status |
| `data/faults/expected_results.json` | The ten fault fixtures and the control each must trip |
| `data/samples/*.csv` | Extract samples from all three systems, plus a journal line sample |
| `config/generation/expected_mapping_manifest.csv` | The mapping fixture Phase 3 is graded against |
| `config/anchors/phase02_source_layer_targets.csv` | The anchor bridge: consolidated → source layer |
