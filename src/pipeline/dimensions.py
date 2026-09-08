"""
Conformed dimensions, built from the approved Phase 1 configuration.

Every dimension carries three things beyond its attributes:

    the source natural key   what the source system called it
    the conformed key        what the platform calls it
    provenance               which configuration file it came from, and its effective dates

Nothing is invented here and no hierarchy is flattened away: `dim_entity` keeps its parent,
`dim_cost_center` keeps its department and business unit, and `dim_account` keeps the full
caption hierarchy from the group chart.  A reporting layer may flatten them; a conformed
dimension may not.
"""

from __future__ import annotations

import duckdb

from .config import CONFIG, LAYER_DIR, writing_artefacts

#: Every dimension, the configuration it is built from, and its natural key.
DIMENSION_SOURCES = {
    "dim_entity": ("config/entities/entity_master.csv", "entity_code"),
    "dim_business_unit": ("config/dimensions/business_unit.csv", "bu_code"),
    "dim_department": ("config/dimensions/department.csv", "department_code"),
    "dim_account": ("config/coa/group_coa.csv", "group_account"),
    "dim_source_account": ("config/coa/source_coa_*.csv", "erp_system + source_account"),
    "dim_cost_center": ("data/reference/cost_centres.csv", "entity_code + cost_center_code"),
    "dim_currency": ("config/anchors/anchor_fx_rates.csv", "currency_code"),
    "dim_scenario": ("config/dimensions/scenario_version.csv", "scenario_code"),
    "dim_version": ("config/dimensions/scenario_version.csv", "version_code"),
    "dim_intercompany_partner": ("config/entities/entity_master.csv", "partner_entity_code"),
    "dim_consolidation_layer": ("config/dimensions/consolidation_layer.csv", "layer_id"),
    "dim_date": ("derived from the period spine", "period_key"),
}


def _csv(path: str) -> str:
    return f"read_csv('{(CONFIG.parent / path).as_posix()}', all_varchar=true, header=true)"


def build(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Create every conformed dimension. Returns row counts."""
    statements = {
        # ---------------------------------------------------------------- entity
        "dim_entity": f"""
            SELECT
                entity_code,
                entity_name, short_name, legal_form, country_code, country_name, region,
                functional_currency, erp_system, erp_company_code,
                primary_business_unit AS bu_code,
                parent_entity_code,
                CAST(ownership_pct AS DOUBLE) AS ownership_pct,
                CAST(nci_pct AS DOUBLE) AS nci_pct,
                consolidation_method, entity_type,
                CAST(consolidation_effective_from AS DATE) AS effective_from,
                TRY_CAST(nullif(consolidation_effective_to, '') AS DATE) AS effective_to,
                TRY_CAST(nullif(acquisition_date, '') AS DATE) AS acquisition_date,
                acquisition_type,
                is_elimination_entity = 'TRUE' AS is_elimination_entity,
                is_active = 'TRUE' AS is_active,
                CASE WHEN erp_system = 'AURORA' THEN entity_code ELSE erp_company_code END
                    AS source_entity_key,
                'config/entities/entity_master.csv' AS source_config
            FROM {_csv('config/entities/entity_master.csv')}
        """,
        # ---------------------------------------------------------- business unit
        "dim_business_unit": f"""
            SELECT bu_code, bu_name, bu_short_name, segment_type,
                   CAST(reporting_sort_order AS INTEGER) AS sort_order,
                   is_reportable_segment = 'TRUE' AS is_reportable_segment,
                   description,
                   'config/dimensions/business_unit.csv' AS source_config
            FROM {_csv('config/dimensions/business_unit.csv')}
        """,
        # ------------------------------------------------------------ department
        "dim_department": f"""
            SELECT department_code, department_name, function_group, cost_type,
                   pl_destination, is_direct = 'TRUE' AS is_direct,
                   applies_to_bu, headcount_bearing = 'TRUE' AS is_headcount_bearing,
                   'config/dimensions/department.csv' AS source_config
            FROM {_csv('config/dimensions/department.csv')}
        """,
        # --------------------------------------------------------------- account
        # The group chart is the single source of account metadata. No stage may restate
        # a caption, an EBITDA flag or a cash-flow category of its own (P3-DIM-06).
        "dim_account": f"""
            SELECT group_account, account_name, statement,
                   fs_caption_l1, fs_caption_l2, account_class,
                   normal_balance, fx_method, cash_flow_category,
                   is_intercompany = 'TRUE' AS is_intercompany,
                   is_ebitda = 'TRUE' AS is_ebitda,
                   is_ebitda_addback = 'TRUE' AS is_ebitda_addback,
                   is_statistical = 'TRUE' AS is_statistical,
                   include_in_tb_balance = 'TRUE' AS include_in_tb_balance,
                   CAST(sort_order AS INTEGER) AS sort_order,
                   CASE substr(group_account, 1, 1)
                        WHEN '1' THEN 'ASSET' WHEN '2' THEN 'LIABILITY' WHEN '3' THEN 'EQUITY'
                        WHEN '4' THEN 'REVENUE' WHEN '5' THEN 'COST_OF_SALES'
                        WHEN '6' THEN 'OPERATING_EXPENSE' WHEN '7' THEN 'BELOW_EBIT'
                        WHEN '8' THEN 'TAX' ELSE 'OTHER' END AS reporting_block,
                   CASE WHEN normal_balance = 'D' THEN 1 ELSE -1 END AS normal_sign,
                   'config/coa/group_coa.csv' AS source_config
            FROM {_csv('config/coa/group_coa.csv')}
        """,
        # -------------------------------------------------------- source account
        # The three source charts, conformed into one dimension that keeps each system's
        # own natural key. This is what makes a mapped row traceable to the chart the
        # posting actually came from.
        "dim_source_account": f"""
            SELECT erp_system, source_account, source_account_name,
                   nullif(source_account_name_local, '') AS source_account_name_local,
                   source_account_type, source_normal_balance,
                   group_account AS default_group_account,
                   mapping_type, nullif(mapping_rule, '') AS mapping_rule_narrative,
                   CAST(effective_from AS DATE) AS effective_from,
                   TRY_CAST(nullif(effective_to, '') AS DATE) AS effective_to,
                   nullif(notes, '') AS notes,
                   'config/coa/source_coa_' || lower(erp_system) || '.csv' AS source_config
            FROM (
                SELECT *, NULL AS source_account_name_local
                    FROM {_csv('config/coa/source_coa_aurora.csv')}
                UNION ALL BY NAME
                SELECT *, NULL AS source_account_name_local
                    FROM {_csv('config/coa/source_coa_sable.csv')}
                UNION ALL BY NAME
                SELECT * FROM {_csv('config/coa/source_coa_kestrel.csv')}
            )
        """,
        # ----------------------------------------------------------- cost centre
        "dim_cost_center": f"""
            SELECT entity_code, cost_center_code, cost_center_name,
                   department_code, department_name, function_group, dept_function,
                   cost_type, pl_destination, bu_code,
                   is_headcount_bearing = 'TRUE' AS is_headcount_bearing,
                   erp_system, manager_id, is_active = 'TRUE' AS is_active,
                   'data/reference/cost_centres.csv' AS source_config
            FROM {_csv('data/reference/cost_centres.csv')}
        """,
        # -------------------------------------------------------------- currency
        "dim_currency": f"""
            SELECT DISTINCT currency_code,
                   CASE currency_code WHEN 'USD' THEN 'US Dollar' WHEN 'CAD' THEN 'Canadian Dollar'
                        WHEN 'GBP' THEN 'Pound Sterling' WHEN 'EUR' THEN 'Euro' END AS currency_name,
                   currency_code = 'USD' AS is_presentation_currency,
                   'USD per 1 unit of foreign currency' AS quote_convention,
                   'config/anchors/anchor_fx_rates.csv' AS source_config
            FROM {_csv('config/anchors/anchor_fx_rates.csv')}
        """,
        # ------------------------------------------------------ scenario/version
        "dim_scenario": f"""
            SELECT code AS scenario_code, name AS scenario_name, scenario_type,
                   fx_rate_set, is_default = 'TRUE' AS is_default,
                   is_reserved = 'TRUE' AS is_reserved,
                   CAST(sort_order AS INTEGER) AS sort_order, description,
                   'config/dimensions/scenario_version.csv' AS source_config
            FROM {_csv('config/dimensions/scenario_version.csv')} WHERE "table" = 'scenario'
        """,
        "dim_version": f"""
            SELECT code AS version_code, name AS version_name,
                   parent_code AS scenario_code,
                   TRY_CAST(nullif(fiscal_year, '') AS INTEGER) AS fiscal_year,
                   scenario_type, fx_rate_set,
                   TRY_CAST(nullif(actual_months, '') AS INTEGER) AS actual_months,
                   TRY_CAST(nullif(forecast_months, '') AS INTEGER) AS forecast_months,
                   is_default = 'TRUE' AS is_default, is_locked = 'TRUE' AS is_locked,
                   is_reserved = 'TRUE' AS is_reserved,
                   nullif(approved_by, '') AS approved_by,
                   TRY_CAST(nullif(approved_date, '') AS DATE) AS approved_date,
                   CAST(sort_order AS INTEGER) AS sort_order, description,
                   'config/dimensions/scenario_version.csv' AS source_config
            FROM {_csv('config/dimensions/scenario_version.csv')} WHERE "table" = 'version'
        """,
        # ------------------------------------------------ intercompany partner
        # A partner is a real legal entity seen from the other side of a transaction. It is
        # a role, not a new population, so the dimension is a conformed view of dim_entity
        # rather than an independent list that could drift out of step with it.
        "dim_intercompany_partner": """
            SELECT entity_code AS partner_entity_code,
                   entity_name AS partner_entity_name,
                   short_name AS partner_short_name,
                   bu_code AS partner_bu_code,
                   country_code AS partner_country_code,
                   functional_currency AS partner_functional_currency,
                   erp_system AS partner_erp_system,
                   effective_from, effective_to,
                   'conformed view of dim_entity' AS source_config
            FROM dim_entity WHERE NOT is_elimination_entity
        """,
        # ------------------------------------------------------------ layer
        "dim_consolidation_layer": f"""
            SELECT CAST(layer_id AS INTEGER) AS layer_id, layer_code, layer_name,
                   CAST(layer_sequence AS INTEGER) AS layer_sequence,
                   posting_source, posted_to_entity, posted_to_entity_type,
                   in_statutory_view = 'TRUE' AS in_statutory_view,
                   in_management_view = 'TRUE' AS in_management_view,
                   must_balance_independently = 'TRUE' AS must_balance_independently,
                   CAST(created_by_phase AS INTEGER) AS created_by_phase, description,
                   'config/dimensions/consolidation_layer.csv' AS source_config
            FROM {_csv('config/dimensions/consolidation_layer.csv')}
        """,
        # ------------------------------------------------------------- calendar
        # One row per calendar month across the modelled horizon, plus the four Kestrel
        # special periods for each closed fiscal year. A special period is an accounting
        # period, not a month, and the two are kept apart here so that nothing downstream
        # can plot a thirteenth month.
        "dim_date": """
            WITH months AS (
                SELECT y AS fiscal_year, m AS accounting_period
                FROM generate_series(2023, 2026) t(y), generate_series(1, 12) u(m)
            ), specials AS (
                SELECT y AS fiscal_year, p AS accounting_period
                FROM generate_series(2023, 2025) t(y), generate_series(13, 16) u(p)
            )
            SELECT
                fiscal_year * 100 + LEAST(accounting_period, 12) AS period_key,
                fiscal_year,
                accounting_period,
                LEAST(accounting_period, 12) AS management_period,
                accounting_period > 12 AS is_adjustment_period,
                make_date(fiscal_year, LEAST(accounting_period, 12), 1) AS month_start,
                last_day(make_date(fiscal_year, LEAST(accounting_period, 12), 1)) AS month_end,
                (LEAST(accounting_period, 12) - 1) // 3 + 1 AS fiscal_quarter,
                'FY' || fiscal_year AS fiscal_year_label,
                strftime(make_date(fiscal_year, LEAST(accounting_period, 12), 1), '%Y-%m')
                    AS month_label,
                'derived from the period spine' AS source_config
            FROM (SELECT * FROM months UNION ALL SELECT * FROM specials)
            ORDER BY fiscal_year, accounting_period
        """,
    }
    counts: dict[str, int] = {}
    for name, sql in statements.items():
        con.execute(f"CREATE OR REPLACE TABLE {name} AS {sql}")
        counts[name] = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        if writing_artefacts():
            out = LAYER_DIR["conformed"] / f"{name}.parquet"
            con.execute(
                f"COPY (SELECT * FROM {name} ORDER BY ALL) TO '{out.as_posix()}' "
                f"(FORMAT PARQUET, COMPRESSION ZSTD)")
    return counts
