"""
The declared-key and declared-grain registry.

P6-D-01 was not a hard defect to find. `project_id` was named like a key, used like a key and
joined on like a key, and nothing ever asked whether it *was* one. The lesson is in ADR-0026:

    A declared key is a contract, not a naming convention. Its uniqueness must be proved over
    its authoritative population.

So this module states the contract for every object in the platform that has one, and
`controls.py` proves all of them with the same generic engine. Adding a keyed table without
adding it here is itself a control failure (`P7-REG-01`), which is what stops the registry
drifting away from the warehouse the way documentation does.

Each entry declares:

``key``
    The columns that must jointly identify a row.
``nulls``
    ``FORBIDDEN`` on every key column, or an explanation of the permitted nulls. A key column
    that can be null is not a key; where one is genuinely optional it must be declared, not
    discovered. (Nothing in the current population declares an exception.)
``source``
    The authority for the object's content -- what a reviewer reads to settle a dispute.
``owner``
    The phase that owns the object and would have to fix a failure here.

The registry deliberately covers the *whole* chain rather than the marts alone. P6-D-01
existed in the source, survived ingestion, survived consolidation and reached Power BI. A
framework that only checked the reporting layer would have caught it four steps too late.

Every key below was established against the real population rather than assumed from the
column names -- several turned out to need a column the obvious guess omitted, which is the
same class of mistake P6-D-01 was.
"""

from __future__ import annotations

from typing import NamedTuple


class Declared(NamedTuple):
    object: str
    kind: str                       # DIMENSION | REFERENCE | FACT | MART
    key: tuple[str, ...]
    nulls: str                      # FORBIDDEN, or the reason the `nullable` columns are null
    source: str
    owner: str
    nullable: tuple[str, ...] = ()  # key columns that may be null, named one by one
    note: str = ""


#: A key column may be null only where the attribute genuinely does not apply to the row --
#: a non-intercompany line has no partner, a consolidation entry has no cost centre. That is
#: NULL meaning "there is none", not NULL meaning "unknown", and the two are not the same
#: thing (the Phase 4C policy governs additive measures, and says nothing about attributes).
#: The permission is per column and carries a reason, because "some key column somewhere may
#: be null" is not a contract anyone can check. Uniqueness over such a key is proved with
#: NULL treated as a value, which is the semantics every join in the platform relies on.


class Reference(NamedTuple):
    """
    A foreign key that must resolve. An orphan is a different failure from a duplicate.

    ``accepted`` quarantines a known open finding at the population it was found at, the same
    way `src/pipeline/controls.py` quarantines a source finding. The control then reports
    SOURCE_FINDING at exactly that number and FAILS at any other, so a new defect of the same
    shape cannot hide inside a known one, and a silent fix upstream does not go unnoticed
    either. It is a record of an open defect, never a way to make a suite green.
    """
    child: str
    child_key: tuple[str, ...]
    parent: str
    parent_key: tuple[str, ...]
    owner: str
    accepted: int = 0
    defect: str = ""
    note: str = ""


FORBIDDEN = "FORBIDDEN"

REGISTRY: tuple[Declared, ...] = (

    # ============================================================ Phase 3 conformed dimensions
    Declared("dim_date", "DIMENSION", ("period_key", "accounting_period"), FORBIDDEN,
             "config/calendar.yml", "Phase 3",
             note="The accounting period is in the key: the calendar carries the four "
                  "adjustment periods 13-16, which share a period_key with the December they "
                  "adjust. period_key alone identifies 48 months over 60 rows."),
    Declared("dim_entity", "DIMENSION", ("entity_code",), FORBIDDEN,
             "config/masters/entities.yml", "Phase 3"),
    Declared("dim_business_unit", "DIMENSION", ("bu_code",), FORBIDDEN,
             "config/masters/business_units.yml", "Phase 3"),
    Declared("dim_account", "DIMENSION", ("group_account",), FORBIDDEN,
             "config/masters/group_chart_of_accounts.csv", "Phase 3"),
    Declared("dim_cost_center", "DIMENSION", ("entity_code", "cost_center_code"), FORBIDDEN,
             "data/reference/cost_centres.csv", "Phase 3",
             note="Cost centre codes are reused across entities, so the entity is part of the "
                  "key. This is the shape P6-D-01 turned out NOT to have."),
    Declared("dim_department", "DIMENSION", ("department_code",), FORBIDDEN,
             "config/masters/departments.yml", "Phase 3"),
    Declared("dim_currency", "DIMENSION", ("currency_code",), FORBIDDEN,
             "config/anchors/anchor_fx_rates.csv", "Phase 3"),
    Declared("dim_consolidation_layer", "DIMENSION", ("layer_id",), FORBIDDEN,
             "config/consolidation_layers.yml", "Phase 3"),
    Declared("dim_scenario", "DIMENSION", ("scenario_code",), FORBIDDEN,
             "config/masters/scenarios.yml", "Phase 3"),
    Declared("dim_version", "DIMENSION", ("version_code",), FORBIDDEN,
             "config/masters/scenarios.yml", "Phase 3"),
    Declared("dim_source_account", "DIMENSION", ("erp_system", "source_account"), FORBIDDEN,
             "config/mapping/", "Phase 3",
             note="The same account number means different things in different ERPs, so the "
                  "system is part of the key."),
    Declared("dim_intercompany_partner", "DIMENSION", ("partner_entity_code",), FORBIDDEN,
             "config/masters/entities.yml", "Phase 3"),
    Declared("dim_ownership_period", "DIMENSION", ("period_key", "entity_code"), FORBIDDEN,
             "data/reference/ownership.csv", "Phase 4",
             note="Ownership is a time series: one row per entity per month, which is what "
                  "makes a mid-year acquisition expressible."),

    # ============================================================ Phase 6A semantic dimensions
    # Conformed selections the Power BI model loads. They restate dimensions the warehouse
    # already holds, but a restatement is still an object with a key, and Power BI will fan a
    # fact out just as readily against a duplicated semantic key as against a duplicated
    # warehouse one. `P7-REG-01` flagged all twelve the moment they appeared, which is what it
    # is for.
    Declared("dim_semantic_date", "DIMENSION", ("period_key",), FORBIDDEN,
             "src/powerbi/config.py SEMANTIC_DIMENSIONS", "Phase 6A",
             note="Regular months only -- the adjustment periods that make dim_date's key "
                  "composite are filtered out here, so period_key alone identifies a row."),
    Declared("dim_semantic_entity", "DIMENSION", ("entity_code",), FORBIDDEN,
             "src/powerbi/config.py SEMANTIC_DIMENSIONS", "Phase 6A"),
    Declared("dim_semantic_business_unit", "DIMENSION", ("bu_code",), FORBIDDEN,
             "src/powerbi/config.py SEMANTIC_DIMENSIONS", "Phase 6A"),
    Declared("dim_semantic_account", "DIMENSION", ("group_account",), FORBIDDEN,
             "src/powerbi/config.py SEMANTIC_DIMENSIONS", "Phase 6A"),
    Declared("dim_semantic_cost_centre", "DIMENSION", ("cost_centre_key",), FORBIDDEN,
             "src/powerbi/config.py SEMANTIC_DIMENSIONS", "Phase 6A",
             note="The composite entity|code, formed here because Power BI relates on a "
                  "single column and a cost centre code is only unique within its entity."),
    Declared("dim_semantic_layer", "DIMENSION", ("layer_id",), FORBIDDEN,
             "src/powerbi/config.py SEMANTIC_DIMENSIONS", "Phase 6A"),
    Declared("dim_semantic_basis", "DIMENSION", ("basis",), FORBIDDEN,
             "src/powerbi/config.py SEMANTIC_DIMENSIONS", "Phase 6A"),
    Declared("dim_semantic_currency", "DIMENSION", ("currency_code",), FORBIDDEN,
             "src/powerbi/config.py SEMANTIC_DIMENSIONS", "Phase 6A"),
    Declared("dim_semantic_instrument", "DIMENSION", ("instrument_id",), FORBIDDEN,
             "src/powerbi/config.py SEMANTIC_DIMENSIONS", "Phase 6A"),
    Declared("dim_semantic_project", "DIMENSION", ("project_id",), FORBIDDEN,
             "src/powerbi/config.py SEMANTIC_DIMENSIONS", "Phase 6A",
             note="The Capital Project dimension. 1,846 projects, 1,846 identifiers -- a "
                  "dimension that could not exist before ADR-0026 corrected the key."),
    Declared("dim_semantic_job_family", "DIMENSION", ("job_family_code",), FORBIDDEN,
             "src/powerbi/config.py SEMANTIC_DIMENSIONS", "Phase 6A"),
    Declared("dim_semantic_period_basis", "DIMENSION", ("basis_code",), FORBIDDEN,
             "src/powerbi/measures.py PERIOD_BASIS_ROWS", "Phase 6A",
             note="Disconnected on purpose: read by the statement measures to choose which "
                  "governed column to aggregate, and it filters no fact."),

    # ============================================================ Phase 5 reporting dimensions
    Declared("dim_report_scenario", "DIMENSION", ("version_code",), FORBIDDEN,
             "src/marts/config.py", "Phase 5"),
    Declared("dim_report_measure", "DIMENSION", ("measure_code",), FORBIDDEN,
             "src/marts/config.py MEASURES", "Phase 5"),
    Declared("dim_report_comparison", "DIMENSION", ("comparison_code",), FORBIDDEN,
             "src/marts/config.py COMPARISONS", "Phase 5"),
    Declared("dim_report_ratio", "DIMENSION", ("ratio_code",), FORBIDDEN,
             "src/marts/config.py RATIOS", "Phase 5"),

    # ============================================================ Phase 2 source subledgers
    Declared("fact_capex_project", "FACT", ("project_id",), FORBIDDEN,
             "data/reference/capex_projects.csv", "Phase 2",
             note="THE P6-D-01 CONTRACT. project_id alone identifies a capital project. It is "
                  "built as CP-{entity}-{period}-{asset_class}-{sequence} precisely so that "
                  "this holds; before ADR-0026 the asset class was missing from the "
                  "identifier and 1,846 rows carried only 395 distinct values."),
    Declared("ref_fixed_asset", "REFERENCE", ("asset_id",), FORBIDDEN,
             "data/reference/fixed_assets.csv", "Phase 2",
             note="One row per capitalised asset, resolving to exactly one capital project."),
    Declared("fact_headcount", "FACT",
             ("entity_code", "cost_center_code", "job_family_code", "period_key"), FORBIDDEN,
             "data/reference/headcount_fact.parquet", "Phase 2"),
    Declared("fact_plan", "FACT",
             ("version_code", "entity_code", "period_key", "group_account",
              "cost_center_code"), FORBIDDEN, "data/reference/plan_fact.parquet", "Phase 2"),
    Declared("fact_revenue_detail", "FACT",
             ("entity_code", "period_key", "customer_code", "product_code", "group_account"),
             FORBIDDEN, "data/reference/revenue_detail.parquet", "Phase 2",
             note="Customer and product grain, deliberately outside the journal (ADR-0008). "
                  "The account is part of the key: one customer-product line can hit both a "
                  "product and a service revenue account in a month."),
    Declared("ref_debt_schedule", "REFERENCE", ("instrument_id", "period_key"), FORBIDDEN,
             "data/reference/debt_schedule.csv", "Phase 2"),
    Declared("ref_revolver_utilisation", "REFERENCE", ("instrument_id", "period_key"),
             FORBIDDEN, "data/reference/revolver_utilisation.csv", "Phase 2"),
    Declared("ref_fx_rate", "REFERENCE",
             ("currency_code", "period_key", "rate_set", "rate_type"), FORBIDDEN,
             "data/reference/fx_rates_monthly.csv", "Phase 2",
             note="Rate set and rate type are both in the key: budget and actual rate sets "
                  "coexist, as do average and closing."),
    Declared("ref_fx_rate_historical", "REFERENCE",
             ("entity_code", "group_account", "event_type", "event_date"), FORBIDDEN,
             "data/reference/fx_rates_historical.csv", "Phase 2"),
    Declared("ref_cta_expectation", "REFERENCE", ("entity_code", "period_key"), FORBIDDEN,
             "data/reference/cta_expectation.csv", "Phase 2"),
    Declared("ref_ic_inventory_holding", "REFERENCE",
             ("holding_period", "transaction_period", "seller_entity", "buyer_entity",
              "inventory_category"), FORBIDDEN,
             "data/reference/ic_inventory_holdings.csv", "Phase 2"),
    Declared("ref_ic_inventory_transaction", "REFERENCE", ("ic_transaction_id",), FORBIDDEN,
             "data/reference/ic_inventory_transactions.csv", "Phase 2",
             note="A transaction log: repeated shipments of the same category between the "
                  "same pair in the same month are real, so the log carries its own id."),
    Declared("ref_customer", "REFERENCE", ("customer_code",), FORBIDDEN,
             "data/reference/customers.csv", "Phase 2"),
    Declared("ref_product", "REFERENCE", ("product_code",), FORBIDDEN,
             "data/reference/products.csv", "Phase 2"),
    Declared("ref_investment_register", "REFERENCE", ("investment_id",), FORBIDDEN,
             "data/reference/investment_register.csv", "Phase 2"),
    Declared("ref_investment_rollforward", "REFERENCE",
             ("parent_entity", "subsidiary_entity", "period_key"), FORBIDDEN,
             "data/reference/investment_rollforward.csv", "Phase 2"),
    Declared("ref_ownership", "REFERENCE", ("entity_code", "effective_from"), FORBIDDEN,
             "data/reference/ownership.csv", "Phase 2",
             note="An ownership register is a slowly changing record: the effective date is "
                  "part of the key, and P4-OWN-03 separately proves the ranges do not "
                  "overlap."),
    Declared("ref_acquisition", "REFERENCE", ("acquisition_id",), FORBIDDEN,
             "config/acquisitions.yml", "Phase 4"),
    Declared("ref_ppa_intangible", "REFERENCE", ("ppa_id",), FORBIDDEN,
             "config/acquisitions.yml", "Phase 4"),
    Declared("ref_management_adjustment", "REFERENCE", ("adjustment_id",), FORBIDDEN,
             "config/management_adjustments.yml", "Phase 4"),
    Declared("ref_covenant_term", "REFERENCE", ("term_id",), FORBIDDEN,
             "config/credit_agreement.yml", "Phase 4"),
    Declared("ref_ic_side", "REFERENCE", ("group_account",), FORBIDDEN,
             "config/masters/group_chart_of_accounts.csv", "Phase 4"),
    Declared("ref_report_line", "REFERENCE", ("group_account",), FORBIDDEN,
             "src/marts/build.py", "Phase 5"),
    Declared("ref_default_version", "REFERENCE", ("scenario_code",), FORBIDDEN,
             "config/masters/scenarios.yml", "Phase 3"),

    # ============================================================ Phase 3 ledger facts
    Declared("fact_journal_line", "FACT", ("journal_id", "line_number"), FORBIDDEN,
             "data/raw/ (three ERP extracts)", "Phase 3",
             note="The source general ledger at leg grain. CTL-DQ-03 proves the same key at "
                  "ingestion, on the raw extract, before anything is conformed."),
    Declared("fact_trial_balance", "FACT",
             ("layer_id", "version_code", "entity_code", "cost_center_code", "group_account",
              "partner_entity_code", "period_key", "special_period_type"),
             "A line with no intercompany counterparty has no partner, and an ordinary "
             "posting has no special period type. Both are absences, not unknowns.",
             "src/pipeline/conform.py", "Phase 3",
             nullable=("partner_entity_code", "special_period_type"),
             note="The special period type is in the key: a regular December posting and a "
                  "period-13 adjustment share a period_key and are different rows."),
    Declared("fact_layer1_usd", "FACT",
             ("entity_code", "cost_center_code", "group_account", "partner_entity_code",
              "period_key", "translation_basis"),
             "A line with no intercompany counterparty has no partner.",
             "src/consol/translate.py", "Phase 4",
             nullable=("partner_entity_code",),
             note="The translation basis is in the key: the same balance appears translated "
                  "at the average and at the closing rate, and they are not the same row."),

    # ============================================================ Phase 4 consolidation facts
    Declared("fact_consol_journal", "FACT", ("consol_journal_id", "line_number"), FORBIDDEN,
             "src/consol/", "Phase 4",
             note="Leg grain. The journal id identifies the entry, the line number the leg "
                  "within it (ADR-0024)."),
    Declared("fact_financials", "FACT",
             ("layer_id", "version_code", "entity_code", "cost_center_code", "group_account",
              "partner_entity_code", "period_key", "process", "journal_character"),
             "Layer 1 is the translated ledger rather than the output of a consolidation "
             "process, so it carries no process. A consolidation entry is posted at entity "
             "level and has no cost centre. A line with no counterparty has no partner.",
             "src/consol/", "Phase 4",
             nullable=("process", "cost_center_code", "partner_entity_code"),
             note="Monthly consolidation grain. Process and journal character are both in the "
                  "key: one account in one month is legitimately touched by several processes "
                  "within a layer, and a year-end close leg is distinguishable from an "
                  "ordinary one because the cash flow and the P&L have to tell them apart."),

    # ============================================================ Phase 5 marts
    Declared("mart_financial_monthly", "MART",
             ("basis", "version_code", "entity_code", "bu_code", "cost_center_code",
              "group_account", "period_key"),
             "Consolidation entries reach the mart without a cost centre, because they were "
             "posted at entity level and inventing one would attribute them to a manager.",
             "src/marts/build.py", "Phase 5", nullable=("cost_center_code",)),
    Declared("mart_financial_ytd", "MART",
             ("basis", "version_code", "entity_code", "bu_code", "measure_code",
              "period_key"), FORBIDDEN, "src/marts/build.py", "Phase 5"),
    Declared("mart_variance", "MART",
             ("comparison_code", "basis", "entity_code", "bu_code", "measure_code",
              "period_key"), FORBIDDEN, "src/marts/build.py", "Phase 5"),
    Declared("mart_business_unit", "MART",
             ("basis", "version_code", "bu_code", "measure_code", "period_key"), FORBIDDEN,
             "src/marts/build.py", "Phase 5"),
    Declared("mart_entity_performance", "MART",
             ("basis", "version_code", "entity_code", "measure_code", "period_key"),
             FORBIDDEN, "src/marts/build.py", "Phase 5"),
    Declared("mart_balance_sheet", "MART", ("period_key", "account_class", "caption"),
             FORBIDDEN, "src/marts/build.py", "Phase 5",
             note="The caption spine is keyed on class as well as caption: 'Intercompany "
                  "balances' legitimately spans ASSET and LIABILITY (Phase 4A)."),
    Declared("mart_cash_flow", "MART", ("period_key",), FORBIDDEN,
             "src/marts/build.py", "Phase 5"),
    Declared("mart_working_capital", "MART", ("period_key",), FORBIDDEN,
             "src/marts/build.py", "Phase 5"),
    Declared("mart_covenants", "MART", ("period_key",), FORBIDDEN,
             "src/marts/build.py", "Phase 5"),
    Declared("mart_debt", "MART", ("period_key", "instrument_id"), FORBIDDEN,
             "src/marts/build.py", "Phase 5"),
    Declared("mart_headcount", "MART",
             ("period_key", "entity_code", "department_code", "job_family_code"), FORBIDDEN,
             "src/marts/build.py", "Phase 5"),
    Declared("mart_capex", "MART", ("period_key", "project_id"), FORBIDDEN,
             "src/marts/build.py", "Phase 5",
             note="Inherits the corrected source key. This is the grain the Power BI CapEx "
                  "fact declares, and the grain that failed before ADR-0026."),
    Declared("mart_fx", "MART", ("period_key", "currency_code"), FORBIDDEN,
             "src/marts/build.py", "Phase 5"),
    Declared("mart_management_adjustments", "MART", ("adjustment_id",), FORBIDDEN,
             "src/marts/build.py", "Phase 5"),
    Declared("mart_consolidation_bridge", "MART", ("fiscal_year", "layer_id"), FORBIDDEN,
             "src/marts/build.py", "Phase 5"),
)


REFERENCES: tuple[Reference, ...] = (
    # ------------------------------------------- the capital project traceability chain
    # Capital Project -> CapEx fact -> Fixed Asset. The chain P6-D-01 broke. These joins all
    # SUCCEEDED before the correction; they just fanned out, which is exactly why an orphan
    # check on its own would never have found the defect and the uniqueness check above is
    # what carries the weight.
    Reference("ref_fixed_asset", ("project_id",), "fact_capex_project", ("project_id",),
              "Phase 2",
              note="Every capitalised asset resolves to exactly one capital project."),
    Reference("mart_capex", ("project_id",), "fact_capex_project", ("project_id",), "Phase 5"),

    # ------------------------------------------- dimensional integrity of the source facts
    Reference("fact_capex_project", ("entity_code",), "dim_entity", ("entity_code",),
              "Phase 2"),
    Reference("fact_capex_project", ("period_key",), "dim_date", ("period_key",), "Phase 2"),
    Reference("fact_capex_project", ("bu_code",), "dim_business_unit", ("bu_code",),
              "Phase 2"),
    Reference("ref_fixed_asset", ("entity_code",), "dim_entity", ("entity_code",), "Phase 2"),
    Reference("ref_fixed_asset", ("group_account",), "dim_account", ("group_account",),
              "Phase 2"),
    Reference("fact_headcount", ("entity_code",), "dim_entity", ("entity_code",), "Phase 2"),
    Reference("fact_headcount", ("period_key",), "dim_date", ("period_key",), "Phase 2"),
    Reference("fact_plan", ("version_code",), "dim_version", ("version_code",), "Phase 2"),
    Reference("fact_plan", ("group_account",), "dim_account", ("group_account",), "Phase 2"),
    Reference("fact_revenue_detail", ("customer_code",), "ref_customer", ("customer_code",),
              "Phase 2"),
    Reference("fact_revenue_detail", ("product_code",), "ref_product", ("product_code",),
              "Phase 2"),
    Reference("ref_debt_schedule", ("borrower_entity",), "dim_entity", ("entity_code",),
              "Phase 2"),

    # ------------------------------------------- the consolidation facts
    Reference("fact_consol_journal", ("entity_code",), "dim_entity", ("entity_code",),
              "Phase 4"),
    Reference("fact_consol_journal", ("group_account",), "dim_account", ("group_account",),
              "Phase 4"),
    Reference("fact_consol_journal", ("layer_id",), "dim_consolidation_layer", ("layer_id",),
              "Phase 4"),
    Reference("fact_financials", ("entity_code",), "dim_entity", ("entity_code",), "Phase 4"),
    Reference("fact_financials", ("group_account",), "dim_account", ("group_account",),
              "Phase 4"),
    Reference("fact_financials", ("layer_id",), "dim_consolidation_layer", ("layer_id",),
              "Phase 4"),
    Reference("fact_trial_balance", ("group_account",), "dim_account", ("group_account",),
              "Phase 3"),
    Reference("fact_layer1_usd", ("group_account",), "dim_account", ("group_account",),
              "Phase 4"),

    # ------------------------------------------- the marts to their dimensions
    Reference("mart_financial_ytd", ("measure_code",), "dim_report_measure",
              ("measure_code",), "Phase 5"),
    # P7-D-01, CLOSED. Prior year is derived by shifting Actual twelve months and is stored
    # nowhere, and for that reason it had no version row -- so 12,516 mart rows joined on a
    # version code with no version behind it. PY_DERIVED is now a governed derived version in
    # the master (ADR-0027) and this resolves at zero, with no acceptance.
    Reference("mart_financial_ytd", ("version_code",), "dim_report_scenario",
              ("version_code",), "Phase 5"),
    Reference("mart_financial_ytd", ("version_code",), "dim_version", ("version_code",),
              "Phase 5"),
    Reference("mart_financial_monthly", ("version_code",), "dim_version", ("version_code",),
              "Phase 5"),
    Reference("mart_variance", ("base_version",), "dim_version", ("version_code",), "Phase 5"),
    Reference("mart_variance", ("comparator_version",), "dim_version", ("version_code",),
              "Phase 5",
              note="Nullable: a comparison whose comparator is not yet issued has none."),
    Reference("ref_default_version", ("version_code",), "dim_version", ("version_code",),
              "Phase 5"),
    Reference("dim_version", ("scenario_code",), "dim_scenario", ("scenario_code",),
              "Phase 3",
              note="Every version belongs to a scenario that exists. The compatibility of the "
                   "two beyond mere existence is P7-VER-02."),
    Reference("mart_financial_ytd", ("entity_code",), "dim_entity", ("entity_code",),
              "Phase 5"),
    Reference("mart_financial_monthly", ("group_account",), "dim_account", ("group_account",),
              "Phase 5"),
    Reference("mart_variance", ("comparison_code",), "dim_report_comparison",
              ("comparison_code",), "Phase 5"),
    Reference("mart_variance", ("measure_code",), "dim_report_measure", ("measure_code",),
              "Phase 5"),
    Reference("mart_debt", ("instrument_id",), "ref_debt_schedule", ("instrument_id",),
              "Phase 5"),
    Reference("mart_capex", ("entity_code",), "dim_entity", ("entity_code",), "Phase 5"),
    Reference("mart_headcount", ("entity_code",), "dim_entity", ("entity_code",), "Phase 5"),
    Reference("mart_fx", ("currency_code",), "dim_currency", ("currency_code",), "Phase 5"),

    # ------------------------------------------- the semantic layer back to the warehouse
    Reference("dim_semantic_entity", ("entity_code",), "dim_entity", ("entity_code",),
              "Phase 6A"),
    Reference("dim_semantic_account", ("group_account",), "dim_account", ("group_account",),
              "Phase 6A"),
    Reference("dim_semantic_project", ("project_id",), "fact_capex_project", ("project_id",),
              "Phase 6A",
              note="The Capital Project dimension resolves to the corrected source key."),
    Reference("dim_semantic_instrument", ("instrument_id",), "ref_debt_schedule",
              ("instrument_id",), "Phase 6A"),
    Reference("mart_capex", ("project_id",), "dim_semantic_project", ("project_id",),
              "Phase 6A",
              note="The CapEx fact resolves in the semantic dimension it is related to, so "
                   "no row falls to a blank member."),
    Reference("mart_consolidation_bridge", ("layer_id",), "dim_consolidation_layer",
              ("layer_id",), "Phase 5"),
)


#: Objects that hold data but legitimately have no single declared key, with the reason.
#: The escape hatch exists so `P7-REG-01` can tell "not yet declared" apart from "deliberately
#: keyless" -- the distinction P6-D-01 needed and did not have. It is currently EMPTY: every
#: keyed object in the warehouse has a key that is proved, not asserted. Anything added here
#: needs a reason a reviewer would accept, not a reason the data made convenient.
KEYLESS: dict[str, str] = {}

#: Table prefixes outside the registry's scope, and why. These are derived working sets and
#: presentation outputs whose correctness is proved by value against the facts they come from,
#: not by key: a report table is allowed to repeat a caption, and a staging table is an
#: intermediate the next step consumes whole.
OUT_OF_SCOPE: dict[str, str] = {
    "stg_": "staging intermediates, consumed whole by the next step",
    "rpt_": "presentation outputs, proved by value against fact_financials",
    "rec_": "reconciliation working sets",
    "map_": "mapping engine working sets, graded by CTL-MAP-*",
    "parsed_": "raw per-ERP parse output, before conforming",
    "anchor_": "the committed anchor targets Phase 2 generates against",
    "oracle_": "expected-result manifests used to grade the mapping engine",
    "chk_": "temporary control scratch tables",
    "vw_": "views",
}
