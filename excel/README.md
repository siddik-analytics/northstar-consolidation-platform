# Excel Deliverables

Built in Phase 6. Three workbooks, specified in `docs/reporting-design.md` §3.

| Workbook | Sheets | Audience |
|---|---|---|
| `Northstar_Management_Reporting_Pack.xlsx` | 17 | CFO — the monthly pack |
| `Northstar_Consolidation_Workbook.xlsx` | 12 | Group Financial Controller — the evidence the consolidation is right |
| `Northstar_Forecast_Model.xlsx` | 14 | FP&A — where forecasts are built |

All data acquisition is via Power Query against the published Parquet marts in
`data/30_marts/`. No workbook contains a hard-coded number that is not a labelled assumption
on its `95_Assumptions` sheet.
