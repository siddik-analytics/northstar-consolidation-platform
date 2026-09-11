# Phase 6B assets

Renders of the report in Power BI Desktop 2.157.1354.0, captured by `PrintWindow` from
Desktop's own window (never the screen) and cropped to the 1280×720 canvas by the copper
mark at the page's origin. Taken by `python -m src.powerbi.report.native_qa` on the report build id and
model definition digest recorded in `data/phase06b_native_qa.json`; `P6B-20…25` accept that
record only while both are the ones on disk. None of these is published to the README — they are for the
owner's visual review.

## `final/` — the report as it stands

| file | page | what to look at |
|---|---|---|
| `01_executive_overview.png` | 01 Executive Overview | the three tiers: four first-tier KPIs with variance and favourability word, six second-tier on the copper wash, the year so far, the full-year outlook, the unit that needs attention (the red bars), cash and leverage against the dashed limit |
| `02_pnl_performance.png` | 02 P&L Performance | the governed statement with `[Variance %]` reading EBIT (32.8%); the six key lines as favourability bars; the account detail from `[Account Amount]` |
| `03_business_units_entities.png` | 03 Business Units & Entities | units summing to the Group; share of Group and share of unit; Services green, the other four red |
| `05_cash_flow_liquidity.png` | 05 Cash Flow & Liquidity | Group-level page with the period slicer alone; closed months only |
| `06_ebitda_bridge.png` | 06 EBITDA & Variance Bridge | three EBITDA definitions kept apart; the add-back step in copper; the four governed scenarios by month |
| `07_debt_covenants.png` | 07 Debt & Covenants | *Indicative* at the August close; every test date Compliant; the dashed copper limit |
| `09_consolidation_controls.png` | 09 Consolidation & Controls | the layer bridge from `[Layer EBITDA]`/`[Layer Net Income]`, entries by year, the control environment read from the registers — Phase 6A 68/68, Phase 6B from its own register |

Re-taken in Phase 6B.1 after the two corrections: the Consolidation & Controls page now
carries the period and basis slicers and the bridge titled *Year to date consolidation
bridge — Aug 2026*; the P&L account detail is the full caption → sub-caption → account
hierarchy.

## `final/` — evidence

| file | shows |
|---|---|
| `01_executive_overview_unit_selected.png` | the Executive Overview with *Industrial Services* chosen in the unit slicer: Revenue 84.1, Adjusted EBITDA 4.6 (favourable), FTE 1,051.7; Group cash, net debt and leverage unchanged, as their captions say |
| `01_executive_overview_cutoff.png` | the revenue-by-month visual alone: the navy Actual line ends at August, budget and forecast carry on to December (`P6B-23` measures the last navy pixel against the position of August) |
| `02_pnl_performance_expanded.png` | Phase 6B.1: the account detail with *Revenue* expanded — Product revenue, Service revenue, Project revenue, Other revenue, Revenue deductions, Intercompany revenue, in statement order, each once (P6B-D-06 closed) |

## `../phase-06b-1/` — the hierarchy lab

| file | shows |
|---|---|
| `hierarchy_lab_is_bs.png` | a lab project (not the report) with four single-level matrices: both statements' level-1 and level-2 captions as Desktop sorts them by the governed keys — statement order, each caption once, the reused labels qualified |

## Earlier in the phase

| folder / file | what it was |
|---|---|
| `stop-331814d/` | the first renders at the `331814d` stop, before Phase 6A.3: the unit chart showing the Group total for every unit, the variance matrix at 2,713.9%, the literal Excel formats |
| `desktop_P6B-D-02_unsupported_table_name.png` | Desktop's refusal of the table name `Measures` at the first native open (Phase 6A.2) |
