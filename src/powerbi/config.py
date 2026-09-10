"""
Paths and the shape of the semantic layer.

Nothing here reads data. It exists so that the star schema, the dimension conformance and the
measure layer are declared in one place, and the TMDL, the documentation and the controls are
all generated from that declaration rather than written three times and kept in step by hand.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
MARTS_DIR = DATA / "30_marts"
SEMANTIC_DIR = DATA / "35_semantic"
PBIP_DIR = ROOT / "powerbi"

DUCKDB_PATH = DATA / "20_warehouse" / "northstar.duckdb"
MANIFEST = DATA / "phase06a_manifest.json"
CONTROL_RESULTS = DATA / "phase06a_control_results.csv"
FAULT_RESULTS = DATA / "phase06a_fault_results.csv"
DAX_RESULTS = DATA / "phase06a_dax_results.csv"

PROJECT = "Northstar"
MODEL_DIR = PBIP_DIR / f"{PROJECT}.SemanticModel"
REPORT_DIR = PBIP_DIR / f"{PROJECT}.Report"

#: The table every measure lives on. It was `Measures` until Phase 6A.2: Power BI Desktop
#: reserves that name and refuses to open a project that uses it ("Unsupported Table name
#: "Measures" has been found in data model schema", defect P6B-D-02). The engine accepted it
#: over TMSL, which is why Phase 6A never saw the refusal. Measures are referenced as
#: `[Measure]`, never table-qualified, so the name is metadata and nothing in DAX reads it.
MEASURES_TABLE = "Northstar Measures"

#: Table names Power BI Desktop will not load, confirmed against Desktop 2.157 rather than
#: assumed. `P6-PBIP-02` refuses to emit any of them, case-insensitively.
RESERVED_TABLE_NAMES = frozenset({"measures"})

#: The financial concepts the Phase 6B report brief asks for, each mapped to the governed
#: measure that carries it or deferred with the reason. `P6-COV-01` fails a concept that is
#: neither: a visual may not invent a financial definition, and a brief item may not simply
#: go missing. DSO / DIO / DPO / CCC are deferred by owner decision (Phase 6A.3 §10D): each
#: needs a metric-policy choice -- ending or average balance, the denominator period, the
#: day convention, COGS or purchases for DPO -- that nobody has made.
REPORT_CONCEPTS: dict[str, str | None] = {
    "Revenue": "Revenue", "Gross margin": "Gross Margin %", "Adjusted EBITDA":
    "Management Adjusted EBITDA", "EBITDA margin": "EBITDA Margin %",
    "Statutory EBITDA": "Statutory EBITDA", "Covenant EBITDA": "Covenant EBITDA",
    "EBIT": "EBIT", "Net income": "Net Income", "Attributable to parent":
    "Net Income Attributable to Parent", "Variance": "Variance", "Variance %": "Variance %",
    "Favourability": "Variance Favourability", "Operating cash flow": "Operating Cash Flow",
    "Investing cash flow": "Investing Cash Flow", "Financing cash flow": "Financing Cash Flow",
    "FX effect on cash": "FX Effect on Cash", "Net change in cash": "Net Change in Cash",
    "Closing cash": "Closing Cash", "Total liquidity": "Total Liquidity",
    "Cash": "Cash", "Accounts receivable": "Accounts Receivable", "Inventory": "Inventory",
    "Accounts payable": "Accounts Payable", "Net working capital": "Net Working Capital",
    "PP&E": "Property Plant and Equipment", "Goodwill": "Goodwill",
    "Intangibles": "Intangible Assets", "Total assets": "Total Assets",
    "Total liabilities": "Total Liabilities", "Total equity": "Total Equity",
    "CTA": "Cumulative Translation Adjustment", "NCI equity": "Non-controlling Interest Equity",
    "Gross debt": "Gross Debt", "Covenant net debt": "Covenant Net Debt",
    "Covenant net leverage": "Covenant Net Leverage", "Covenant limit": "Covenant Limit",
    "Covenant headroom": "Covenant Headroom", "Economic leverage": "Economic Leverage",
    "Covenant status": "Covenant Status", "Opening FTE": "Opening FTE", "Hires": "Hires",
    "Exits": "Exits", "Closing FTE": "Closing FTE", "Average FTE": "Average FTE",
    "Personnel cost": "Personnel Cost", "CapEx spend": "Actual CapEx",
    "CapEx approved": "Approved CapEx", "CapEx variance": "CapEx Variance",
    "Capital projects": "Capital Projects", "Account drill amount": "Account Amount",
    "Layer EBITDA": "Layer EBITDA", "Layer net income": "Layer Net Income",
    "Revenue share of Group": "Revenue Share of Group",
    "Revenue share of unit": "Revenue Share of Unit",
    # deferred, by owner decision, pending a metric-policy choice
    "DSO": None, "DIO": None, "DPO": None, "Cash conversion cycle": None,
    "Revolver drawn": None, "Revolver available": None, "Principal by instrument": None,
}

#: The reporting close. Actual stops here; everything after it is forecast, and an Actual
#: measure must return BLANK rather than zero beyond it (Phase 5, carried forward as a rule).
REPORT_PERIOD = 202608
REPORT_FY = 2026
ACT_VERSION = "ACTUAL"
BUD_VERSION = "BUD_FY26_V1"
FC_VERSION = "FC_FY26_08"
PY_VERSION = "PY_DERIVED"

#: Tolerances. A semantic model against the mart it reads is a structural identity, so it is
#: tested at the cent. `TOL_RATIO` covers a leverage multiple carried to four decimals.
TOL_XAR_USD = 0.05
TOL_RATIO = 0.0005

#: The dimension tables the semantic model needs that the Phase 5 marts do not publish.
#: They are conformance only -- selections and relabellings of dimensions the warehouse
#: already holds -- and they are published to their own folder so that the Phase 5 marts stay
#: frozen and their manifest digest does not move.
SEMANTIC_DIMENSIONS: tuple[tuple[str, str], ...] = (
    ("dim_semantic_date", """
        SELECT period_key, fiscal_year, accounting_period, fiscal_quarter,
               month_start, month_end, fiscal_year_label,
               strftime(month_start, '%b %y') AS month_label,
               strftime(month_start, '%b %Y') AS month_label_long,
               'Q' || CAST(fiscal_quarter AS VARCHAR) AS quarter_label,
               fiscal_year_label || ' Q' || CAST(fiscal_quarter AS VARCHAR) AS fy_quarter_label,
               fiscal_year * 10 + fiscal_quarter AS quarter_key,
               period_key <= {report_period} AS is_actual_month,
               period_key = {report_period} AS is_reporting_month
        FROM dim_date WHERE accounting_period <= 12
          AND period_key BETWEEN (SELECT min(period_key) FROM mart_cash_flow)
                             AND (SELECT max(period_key) FROM mart_cash_flow)
        ORDER BY period_key"""),
    ("dim_semantic_entity", """
        SELECT entity_code, entity_name, short_name, bu_code, country_code, country_name,
               region, functional_currency, erp_system, entity_type, consolidation_method,
               ownership_pct, nci_pct, is_elimination_entity
        FROM dim_entity ORDER BY entity_code"""),
    ("dim_semantic_business_unit", """
        SELECT bu_code, bu_name, bu_short_name, segment_type, is_reportable_segment,
               sort_order FROM dim_business_unit ORDER BY sort_order"""),
    ("dim_semantic_account", """
        SELECT group_account, account_name, statement, fs_caption_l1, fs_caption_l2,
               account_class, normal_balance, cash_flow_category, is_intercompany,
               is_ebitda, is_ebitda_addback, sort_order
        FROM dim_account WHERE NOT is_statistical ORDER BY group_account"""),
    ("dim_semantic_cost_centre", """
        SELECT DISTINCT entity_code || '|' || cost_center_code AS cost_centre_key,
               cost_center_code, cost_center_name, entity_code, department_code,
               department_name, function_group, cost_type, bu_code
        FROM dim_cost_center ORDER BY 1"""),
    ("dim_semantic_layer", """
        SELECT layer_id, layer_code, layer_name, in_statutory_view, in_management_view,
               layer_sequence AS sort_order, description
        FROM dim_consolidation_layer ORDER BY layer_id"""),
    ("dim_semantic_basis", """
        SELECT 'STATUTORY' AS basis, 'Statutory' AS basis_name, 1 AS sort_order,
               'Layers 1 + 2 + 3 + 5. The reported result.' AS description
        UNION ALL
        SELECT 'MANAGEMENT', 'Management', 2,
               'Statutory plus layer 4, the approved management adjustments.'
        ORDER BY sort_order"""),
    ("dim_semantic_currency", """
        SELECT currency_code, currency_name, is_presentation_currency, quote_convention
        FROM dim_currency ORDER BY currency_code"""),
    ("dim_semantic_instrument", """
        SELECT DISTINCT instrument_id, instrument_name, instrument_type, borrower_entity,
               currency_code, rate_type, is_hedged,
               CAST(maturity_date AS DATE) AS maturity_date,
               counts_toward_covenant_debt
        FROM mart_debt ORDER BY instrument_type, instrument_id"""),
    # The corrected capital-project key (ADR-0026). 1,846 projects, 1,846 identifiers -- the
    # dimension is only expressible at all because the key was fixed at the generator; before
    # that these five columns yielded 1,846 rows for 395 identifiers and no unique key existed.
    # Asset class stays an attribute here rather than becoming a dimension of its own: it is a
    # property of the project, and a second table for it would be the same business concept
    # twice.
    ("dim_semantic_project", """
        SELECT DISTINCT project_id, project_name, asset_class, entity_code, bu_code,
               period_key AS approved_period, fiscal_year AS approved_fiscal_year
        FROM mart_capex ORDER BY project_id"""),
    # The one workforce attribute with no other home. Department reaches Headcount through
    # Cost Centre already, so a Department dimension would create a second path to the same
    # concept; job family exists only on the headcount fact.
    # The codes are abbreviations, so the names are stated rather than derived: a generic
    # transform turns ENGR into "Engr", which is not a word anyone wants on a report.
    ("dim_semantic_job_family", """
        SELECT DISTINCT job_family_code,
               CASE job_family_code
                   WHEN 'ADMIN'  THEN 'Administration'
                   WHEN 'ENGR'   THEN 'Engineering'
                   WHEN 'EXEC'   THEN 'Executive'
                   WHEN 'FIELD'  THEN 'Field service'
                   WHEN 'FIN'    THEN 'Finance'
                   WHEN 'HR'     THEN 'Human resources'
                   WHEN 'IT'     THEN 'Information technology'
                   WHEN 'PROD'   THEN 'Production'
                   WHEN 'PROJ'   THEN 'Project management'
                   WHEN 'QUAL'   THEN 'Quality'
                   WHEN 'SALES'  THEN 'Sales'
                   WHEN 'SUPPLY' THEN 'Supply chain'
                   ELSE job_family_code
               END AS job_family_name
        FROM mart_headcount ORDER BY job_family_code"""),
)

#: Every table the model loads. `source` is the Parquet stem, `folder` says which published
#: directory it comes from, `key` is the declared grain (checked by `P6-SEM-02`) and `hide`
#: lists the technical columns a report should never see.
TABLES: tuple[dict, ...] = (
    # ---------------------------------------------------------------- dimensions
    dict(name="Date", source="dim_semantic_date", folder="semantic", kind="dimension",
         key=("period_key",),
         sort={"month_label": "period_key", "month_label_long": "period_key",
               "quarter_label": "fiscal_quarter"},
         hide=("period_key", "quarter_key", "month_end"),
         description="The fiscal calendar. One date table for the whole model: every fact "
                     "joins to it on period_key, so a filter on Date filters everything."),
    dict(name="Entity", source="dim_semantic_entity", folder="semantic", kind="dimension",
         key=("entity_code",), sort={}, hide=(),
         description="Legal entities, including the three virtual elimination entities that "
                     "carry the consolidation entries."),
    dict(name="Business Unit", source="dim_semantic_business_unit", folder="semantic",
         kind="dimension", key=("bu_code",), sort={"bu_name": "sort_order"},
         hide=("sort_order",),
         description="The five reportable segments. Facts reach it through Entity rather than "
                     "directly -- an entity belongs to exactly one unit, so the segment view "
                     "is the entity view rolled up, and a second path would make every "
                     "segment total ambiguous."),
    dict(name="Account", source="dim_semantic_account", folder="semantic", kind="dimension",
         key=("group_account",), sort={"fs_caption_l2": "sort_order"}, hide=("sort_order",),
         description="The group chart of accounts, with the statement, the caption and the "
                     "attributes the consolidation drives EBITDA and the add-back policy "
                     "from."),
    dict(name="Cost Centre", source="dim_semantic_cost_centre", folder="semantic",
         kind="dimension", key=("cost_centre_key",), sort={}, hide=("cost_centre_key",),
         description="Cost centres, keyed by entity and code because the same code is reused "
                     "across entities."),
    dict(name="Consolidation Layer", source="dim_semantic_layer", folder="semantic",
         kind="dimension", key=("layer_id",), sort={"layer_name": "sort_order"},
         hide=("sort_order",),
         description="The five consolidation layers and their view membership."),
    dict(name="Reporting Basis", source="dim_semantic_basis", folder="semantic",
         kind="dimension", key=("basis",), sort={"basis_name": "sort_order"},
         hide=("sort_order",),
         description="Statutory or Management. Membership is settled upstream and carried on "
                     "every fact row; the model never infers it."),
    dict(name="Currency", source="dim_semantic_currency", folder="semantic",
         kind="dimension", key=("currency_code",), sort={}, hide=(),
         description="Transaction and functional currencies. The presentation currency is USD."),
    dict(name="Scenario", source="dim_report_scenario", folder="marts", kind="dimension",
         key=("version_code",),
         sort={"version_name": "sort_order", "scenario_name": "sort_order"},
         hide=("sort_order", "derived_from_scenario_code"),
         hierarchies={"Scenario and version": ("scenario_name", "version_name")},
         description="Scenario and version in ONE dimension, keyed by version, with a "
                     "Scenario -> Version hierarchy. A version belongs to exactly one "
                     "scenario, so these are two levels of one thing rather than two "
                     "dimensions; splitting them would snowflake the model and give a fact "
                     "two paths to the same concept. Every version the master governs is "
                     "here, including PY_DERIVED -- the derived version for Prior Year "
                     "(ADR-0027). Reserved scenarios are absent by construction: the mart "
                     "never publishes them, so Downside cannot be selected into an empty "
                     "report that looks like a real one."),
    dict(name="Measure Line", source="dim_report_measure", folder="marts", kind="dimension",
         key=("measure_code",), sort={"measure_name": "sort_order"}, hide=("sort_order",),
         description="The income statement line hierarchy, in presentation order, with the "
                     "indent level and the favourable direction that makes variance colouring "
                     "account-aware."),
    dict(name="Comparison", source="dim_report_comparison", folder="marts", kind="dimension",
         key=("comparison_code",), sort={"comparison_name": "sort_order"},
         hide=("sort_order",),
         description="The four approved comparisons: Actual vs Budget, Actual vs Forecast, "
                     "Forecast vs Budget and Actual vs Prior Year. Each names its base and "
                     "comparator versions upstream, so a report selects a comparison rather "
                     "than assembling one."),
    dict(name="Job Family", source="dim_semantic_job_family", folder="semantic",
         kind="dimension", key=("job_family_code",), sort={}, hide=(),
         description="The twelve job families. Department is deliberately NOT a dimension of "
                     "its own: Headcount reaches it through Cost Centre, and a direct "
                     "relationship as well would give one business concept two filter paths."),
    dict(name="Debt Instrument", source="dim_semantic_instrument", folder="semantic",
         kind="dimension", key=("instrument_id",), sort={}, hide=(),
         description="Debt instruments, with the covenant flag the net debt definition uses."),
    dict(name="Capital Project", source="dim_semantic_project", folder="semantic",
         kind="dimension", key=("project_id",), sort={},
         hide=("approved_period",),
         hierarchies={"Project by class": ("asset_class", "project_name", "project_id")},
         description="One row per capital project: 1,846 projects, 1,846 identifiers. The key "
                     "is the corrected business key CP-{entity}-{period}-{asset_class}-{seq} "
                     "(ADR-0026) and no surrogate is introduced to stand in for it -- a "
                     "surrogate here would hide the very thing the correction fixed. Asset "
                     "class is an attribute, not a separate dimension."),

    # ---------------------------------------------------------------- facts
    dict(name="Financials", source="mart_financial_ytd", folder="marts", kind="fact",
         key=("basis", "version_code", "entity_code", "bu_code", "measure_code",
              "period_key"),
         sort={},
         hide=("basis", "version_code", "scenario_code", "entity_code", "bu_code",
               "measure_code", "period_key", "fiscal_year", "accounting_period",
               "fiscal_quarter", "measure_name", "indent_level", "is_subtotal",
               "favourable_direction", "measure_sort"),
         description="The measure grain: month, year to date and full year for fourteen "
                     "income statement measures, on both bases and every scenario. Subtotals "
                     "are stored upstream, not derived here."),
    dict(name="Financial Detail", source="mart_financial_monthly", folder="marts",
         kind="fact",
         key=("basis", "version_code", "entity_code", "bu_code", "cost_center_code",
              "group_account", "period_key"),
         sort={},
         hide=("basis", "version_code", "scenario_code", "entity_code", "bu_code",
               "cost_center_code", "cost_centre_key", "group_account", "period_key",
               "fiscal_year", "accounting_period", "fiscal_quarter", "line"),
         calculated={
             "cost_centre_key":
                 "'Financial Detail'[entity_code] & \"|\" & "
                 "'Financial Detail'[cost_center_code]",
         },
         # The same composite in SQL, so a control can test that it resolves against the
         # dimension. A calculated column exists only inside the model, and a control that
         # cannot see it cannot prove the relationship built on it is sound.
         calculated_sql={
             "cost_centre_key": "entity_code || '|' || cost_center_code",
         },
         description="Account grain, for drill-down from any measure to the accounts behind "
                     "it. The measure layer reads Financials, not this.\n\n"
                     "Carries the model's ONLY calculated column. A cost centre is identified "
                     "by entity and code together -- codes are reused across entities -- and "
                     "Power BI relates on a single column, so the composite has to be formed "
                     "somewhere. It is formed here rather than added to the frozen Phase 5 "
                     "mart, and it is mechanical concatenation of two governed keys with no "
                     "business logic in it."),
    dict(name="Variance", source="mart_variance", folder="marts", kind="fact",
         key=("comparison_code", "basis", "entity_code", "bu_code", "measure_code",
              "period_key"),
         sort={},
         hide=("comparison_code", "basis", "entity_code", "bu_code", "measure_code",
               "period_key", "fiscal_year", "accounting_period", "sort_order",
               "comparison_name", "measure_name", "indent_level", "is_subtotal",
               "favourable_direction", "measure_sort", "base_version",
               "comparator_version"),
         description="Every approved comparison, precomputed upstream: base, comparator, "
                     "variance and favourability. The model reads these rather than deriving "
                     "a comparison in DAX."),
    dict(name="Balance Sheet", source="mart_balance_sheet", folder="marts", kind="fact",
         key=("caption", "account_class", "period_key"),
         sort={"caption": "sort_order"},
         hide=("period_key", "fiscal_year", "sort_order"),
         # The balance sheet's key is the caption and its class, and those are exactly what a
         # reader slices by -- unlike a surrogate or a period key, they are the business
         # meaning rather than the plumbing. Declared visible on purpose so `P6-SEM-12` can
         # still fail a technical key left exposed anywhere else.
         visible_key=("caption", "account_class"),
         hierarchies={"Balance sheet": ("account_class", "caption")},
         description="The consolidated balance sheet by caption and account class, in the "
                     "approved presentation order. The caption sorts by sort_order, never "
                     "alphabetically: a balance sheet in alphabetical order is not a balance "
                     "sheet."),
    dict(name="Cash Flow", source="mart_cash_flow", folder="marts", kind="fact",
         key=("period_key",), sort={},
         hide=("period_key", "fiscal_year", "accounting_period"),
         description="The consolidated cash flow and the liquidity position, monthly."),
    dict(name="Working Capital", source="mart_working_capital", folder="marts", kind="fact",
         key=("period_key",), sort={}, hide=("period_key", "fiscal_year"),
         description="Receivables, inventory, payables and the conversion cycle."),
    dict(name="Covenants", source="mart_covenants", folder="marts", kind="fact",
         key=("period_key",), sort={}, hide=("period_key", "fiscal_year"),
         description="Net leverage on a rolling twelve-month covenant EBITDA, the agreement's "
                     "limit for the fiscal year, and headroom."),
    dict(name="Debt", source="mart_debt", folder="marts", kind="fact",
         key=("instrument_id", "period_key"), sort={},
         hide=("period_key", "fiscal_year", "instrument_id", "instrument_name",
               "instrument_type", "borrower_entity", "currency_code", "rate_type",
               "is_hedged", "maturity_date", "interest_rate_basis",
               "counts_toward_covenant_debt", "covenant_reference"),
         description="Debt by instrument and month: opening and closing principal, "
                     "drawings, repayments, interest and commitment fees. Carries the "
                     "agreement's covenant flag, which is what separates covenant debt from "
                     "the balance sheet's wider borrowings."),
    dict(name="Headcount", source="mart_headcount", folder="marts", kind="fact",
         key=("entity_code", "department_code", "job_family_code", "period_key"), sort={},
         hide=("period_key", "fiscal_year", "entity_code", "entity_name", "bu_code",
               "country_code", "functional_currency", "department_code", "job_family_code"),
         description="Headcount movement and personnel cost, by entity, department and job "
                     "family."),
    dict(name="CapEx", source="mart_capex", folder="marts", kind="fact",
         key=("project_id", "period_key"), sort={},
         hide=("period_key", "fiscal_year", "project_id", "project_name", "asset_class",
               "entity_code", "entity_name", "bu_code", "bu_name"),
         description="Capital expenditure by project and month."),
    dict(name="FX", source="mart_fx", folder="marts", kind="fact",
         key=("currency_code", "period_key"), sort={},
         hide=("period_key", "fiscal_year", "currency_code"),
         description="Rates, currency exposure, constant currency and the translation "
                     "adjustment."),
    dict(name="Layer Bridge", source="mart_consolidation_bridge", folder="marts",
         kind="fact", key=("layer_id", "fiscal_year"), sort={},
         hide=("layer_id", "layer_code", "layer_name", "in_statutory_view",
               "in_management_view", "fiscal_year"),
         description="What each consolidation layer contributed, by fiscal year."),
)

#: Active relationships. Every one is single-direction many-to-one from a fact to a dimension,
#: which is the shape that has no ambiguity: filters flow one way and there is exactly one
#: path between any two tables. Anything else is in `INACTIVE_RELATIONSHIPS`, with a reason.
#:
#: `EXPECTED_PATHS` is the reachability contract `P6-PATH` holds: each reportable dimension
#: and the facts it must be able to filter along an active path. A dimension that exists but
#: reaches nothing is exactly what P6B-D-05 was, and no earlier control asked the question.
EXPECTED_PATHS: dict[str, tuple[str, ...]] = {
    "Date": ("Financials", "Financial Detail", "Variance", "Balance Sheet", "Cash Flow",
             "Working Capital", "Covenants", "Debt", "Headcount", "CapEx", "FX"),
    "Entity": ("Financials", "Financial Detail", "Variance", "Headcount", "CapEx"),
    "Business Unit": ("Financials", "Financial Detail", "Variance", "Headcount", "CapEx"),
    "Account": ("Financial Detail",),
    "Scenario": ("Financials", "Financial Detail"),
    "Reporting Basis": ("Financials", "Financial Detail", "Variance"),
    "Measure Line": ("Financials", "Variance"),
    "Comparison": ("Variance",),
    "Capital Project": ("CapEx",),
    "Job Family": ("Headcount",),
    "Debt Instrument": ("Debt",),
    "Consolidation Layer": ("Layer Bridge",),
}
RELATIONSHIPS: tuple[tuple[str, str, str, str], ...] = (
    # Business Unit reaches every fact through Entity: an entity belongs to exactly one unit.
    # This is the path the five inactive direct relationships below defer to, and until
    # Phase 6A.3 it did not exist -- Business Unit filtered nothing (P6B-D-05). Written
    # many-to-one from Entity, so the filter flows Business Unit -> Entity -> fact.
    ("Entity", "bu_code", "Business Unit", "bu_code"),
    ("Financials", "period_key", "Date", "period_key"),
    ("Financials", "entity_code", "Entity", "entity_code"),
    ("Financials", "measure_code", "Measure Line", "measure_code"),
    ("Financials", "version_code", "Scenario", "version_code"),
    ("Financials", "basis", "Reporting Basis", "basis"),

    ("Financial Detail", "period_key", "Date", "period_key"),
    ("Financial Detail", "entity_code", "Entity", "entity_code"),
    ("Financial Detail", "group_account", "Account", "group_account"),
    ("Financial Detail", "version_code", "Scenario", "version_code"),
    ("Financial Detail", "basis", "Reporting Basis", "basis"),
    ("Financial Detail", "cost_centre_key", "Cost Centre", "cost_centre_key"),

    ("Variance", "period_key", "Date", "period_key"),
    ("Variance", "entity_code", "Entity", "entity_code"),
    ("Variance", "measure_code", "Measure Line", "measure_code"),
    ("Variance", "comparison_code", "Comparison", "comparison_code"),
    ("Variance", "basis", "Reporting Basis", "basis"),

    ("Balance Sheet", "period_key", "Date", "period_key"),
    ("Cash Flow", "period_key", "Date", "period_key"),
    ("Working Capital", "period_key", "Date", "period_key"),
    ("Covenants", "period_key", "Date", "period_key"),
    ("Debt", "period_key", "Date", "period_key"),
    ("Debt", "instrument_id", "Debt Instrument", "instrument_id"),
    ("Headcount", "period_key", "Date", "period_key"),
    ("Headcount", "entity_code", "Entity", "entity_code"),
    # No Headcount -> Cost Centre relationship. `mart_headcount` carries department but no
    # cost centre at all, so the join the WIP declared could never have resolved; the real
    # engine refused it on deployment. Workforce reaches its organisational context through
    # Entity and Job Family, and department is an attribute on the headcount rows themselves.
    ("CapEx", "period_key", "Date", "period_key"),
    ("CapEx", "entity_code", "Entity", "entity_code"),
    ("CapEx", "project_id", "Capital Project", "project_id"),
    ("Headcount", "job_family_code", "Job Family", "job_family_code"),
    ("FX", "period_key", "Date", "period_key"),
    ("FX", "currency_code", "Currency", "currency_code"),
    ("Layer Bridge", "layer_id", "Consolidation Layer", "layer_id"),
)

#: Relationships deliberately left inactive, and why. An inactive relationship is a documented
#: decision. An ambiguous active one is a defect.
INACTIVE_RELATIONSHIPS: tuple[tuple[str, str, str, str, str], ...] = (
    ("Financials", "bu_code", "Business Unit", "bu_code",
     "Financials reaches Business Unit through Entity, so a second direct path would make "
     "every business unit total ambiguous. Entity is the active path because an entity "
     "belongs to exactly one unit."),
    ("Variance", "bu_code", "Business Unit", "bu_code",
     "Variance carries bu_code for its own grain, but reaches Business Unit through Entity "
     "like every other fact. Activating this would give a segment variance two filter paths "
     "and no way to tell which one a visual used."),
    ("Financial Detail", "bu_code", "Business Unit", "bu_code",
     "The account-grain fact reaches Business Unit through Entity. A direct path here would "
     "also make the drill-through from a measure to its accounts ambiguous, because the two "
     "facts would aggregate segments by different routes."),
    ("Headcount", "bu_code", "Business Unit", "bu_code",
     "Headcount reaches Business Unit through Entity. Kept inactive rather than deleted "
     "because the column is genuinely on the mart and a future report may want USERELATIONSHIP "
     "for a workforce-only segment view."),
    ("CapEx", "bu_code", "Business Unit", "bu_code",
     "Capital spend reaches Business Unit through Entity, so that capex by segment and "
     "revenue by segment are built the same way and can sit on one page without disagreeing "
     "about what a segment is."),
)
