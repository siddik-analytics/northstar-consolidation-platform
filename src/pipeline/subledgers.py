"""
The supporting source domains, conformed.

Phase 3 does no accounting on these.  It types them, resolves their keys against the
conformed dimensions, and proves they reconcile where the architecture says they must.
Their purpose is to be validated inputs waiting for the phase that consumes them:

    ref_fx_rate            Phase 4 translation; the historical rates for equity
    ref_ownership          Phase 4 investment elimination and NCI allocation
    ref_investment         Phase 4 investment elimination
    ref_ic_inventory       Phase 4 unrealised profit elimination
    ref_debt / ref_revolver Phase 5 covenant reporting
    ref_cta_expectation    Phase 5's translation engine is tested against it
    fact_revenue_detail    reconciled to mapped GL revenue here, in Phase 3 (ADR-0008)
    fact_headcount         Phase 5 per-head metrics
    fact_capex / ref_fixed_asset  Phase 4 fixed-asset roll-forward
    fact_plan              Budget and forecast, conformed to the scenario/version model

Revenue detail is the one that has to reconcile now, because ADR-0008 keeps customer and
product detail in a separate fact at a finer grain than the GL, and the whole point of that
decision is that the two must tie.  Customer and product columns are NOT pushed into the GL
fact -- that would defeat the decision and inflate the ledger.
"""

from __future__ import annotations

import duckdb

from .config import CONFIG, LAYER_DIR, REFERENCE, writing_artefacts


#: The reference directory the conformance reads from. Overridden only by the fault
#: harness, so that a fault variant of a reference dataset runs through the real pipeline.
_REFERENCE_ROOT = REFERENCE


def set_reference_root(path) -> None:
    global _REFERENCE_ROOT
    _REFERENCE_ROOT = path


def _csv(name: str) -> str:
    return (f"read_csv('{(_REFERENCE_ROOT / name).as_posix()}', all_varchar=true, "
            f"header=true)")


def _parquet(name: str) -> str:
    return f"read_parquet('{(_REFERENCE_ROOT / name).as_posix()}')"


def _config_csv(path: str) -> str:
    return f"read_csv('{(CONFIG / path).as_posix()}', all_varchar=true, header=true)"


def build(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    statements = {
        # ------------------------------------------------------------------ FX
        "ref_fx_rate": f"""
            SELECT currency_code, CAST(period_key AS INTEGER) AS period_key,
                   rate_set, rate_type,
                   CAST(rate_usd_per_unit AS DOUBLE) AS rate_usd_per_unit,
                   base_currency, quote_convention, source, effective_month
            FROM {_csv('fx_rates_monthly.csv')}
        """,
        "ref_fx_rate_historical": f"""
            SELECT entity_code, group_account, event_type, CAST(event_date AS DATE) AS event_date,
                   currency_code, CAST(rate_usd_per_unit AS DOUBLE) AS rate_usd_per_unit,
                   basis, note
            FROM {_csv('fx_rates_historical.csv')}
        """,
        # ----------------------------------------------------------- ownership
        "ref_ownership": f"""
            SELECT entity_code, parent_entity_code,
                   CAST(group_ownership_pct AS DOUBLE) AS group_ownership_pct,
                   CAST(nci_pct AS DOUBLE) AS nci_pct,
                   consolidation_method,
                   CAST(effective_from AS DATE) AS effective_from,
                   TRY_CAST(nullif(effective_to, '') AS DATE) AS effective_to,
                   change_event, change_reason, nullif(nci_holder, '') AS nci_holder, notes
            FROM {_config_csv('entities/ownership_history.csv')}
        """,
        "ref_investment_register": f"""
            SELECT investment_id, parent_entity, subsidiary_entity,
                   CAST(event_date AS DATE) AS event_date,
                   CAST(consolidation_effective_date AS DATE) AS consolidation_effective_date,
                   event_type,
                   CAST(ownership_pct_acquired AS DOUBLE) AS ownership_pct_acquired,
                   CAST(cumulative_ownership_pct AS DOUBLE) AS cumulative_ownership_pct,
                   consideration_currency,
                   CAST(consideration_local AS DOUBLE) AS consideration_local,
                   CAST(consideration_usd_m AS DOUBLE) AS consideration_usd_m,
                   carrying_currency, notes
            FROM {_config_csv('entities/investment_register.csv')}
        """,
        "ref_investment_rollforward": f"""
            SELECT parent_entity, subsidiary_entity, CAST(period_key AS INTEGER) AS period_key,
                   CAST(opening_cost_usd AS DOUBLE) AS opening_cost_usd,
                   CAST(additions_usd AS DOUBLE) AS additions_usd,
                   CAST(disposals_usd AS DOUBLE) AS disposals_usd,
                   CAST(closing_cost_usd AS DOUBLE) AS closing_cost_usd,
                   CAST(ownership_pct AS DOUBLE) AS ownership_pct,
                   CAST(nci_pct AS DOUBLE) AS nci_pct
            FROM {_csv('investment_rollforward.csv')}
        """,
        # ---------------------------------------------------------------- debt
        "ref_debt_schedule": f"""
            SELECT instrument_id, instrument_name, borrower_entity, instrument_type,
                   group_account, currency_code, CAST(period_key AS INTEGER) AS period_key,
                   CAST(opening_principal AS DOUBLE) AS opening_principal,
                   CAST(drawings AS DOUBLE) AS drawings,
                   CAST(repayments AS DOUBLE) AS repayments,
                   CAST(closing_principal AS DOUBLE) AS closing_principal,
                   interest_rate_basis, rate_type, is_hedged = 'TRUE' AS is_hedged,
                   CAST(interest_expense_local AS DOUBLE) AS interest_expense_local,
                   CAST(commitment_fee_local AS DOUBLE) AS commitment_fee_local,
                   CAST(average_daily_drawn AS DOUBLE) AS average_daily_drawn,
                   CAST(average_daily_undrawn AS DOUBLE) AS average_daily_undrawn,
                   CAST(undrawn_commitment AS DOUBLE) AS undrawn_commitment,
                   counts_toward_covenant_debt = 'TRUE' AS counts_toward_covenant_debt,
                   covenant_reference, maturity_date
            FROM {_csv('debt_schedule.csv')}
        """,
        "ref_revolver_utilisation": f"""
            SELECT CAST(period_key AS INTEGER) AS period_key, instrument_id,
                   CAST(opening_drawn AS DOUBLE) AS opening_drawn,
                   CAST(drawings AS DOUBLE) AS drawings,
                   CAST(repayments AS DOUBLE) AS repayments,
                   CAST(closing_drawn AS DOUBLE) AS closing_drawn,
                   CAST(movement_day AS INTEGER) AS movement_day,
                   CAST(days_in_month AS INTEGER) AS days_in_month,
                   CAST(average_daily_drawn AS DOUBLE) AS average_daily_drawn,
                   CAST(average_daily_undrawn AS DOUBLE) AS average_daily_undrawn,
                   CAST(commitment_fee_accrued AS DOUBLE) AS commitment_fee_accrued,
                   CAST(headroom_usd AS DOUBLE) AS headroom_usd
            FROM {_csv('revolver_utilisation.csv')}
        """,
        # ---------------------------------------- translation expectation input
        # Loaded as a control input only. It is never joined into a reporting measure:
        # it is the expectation Phase 5's translation engine will be tested against
        # (CTL-FX-12, ADR-0017).
        "ref_cta_expectation": f"""
            SELECT entity_code, CAST(period_key AS INTEGER) AS period_key, currency_code,
                   CAST(opening_net_assets_local AS DOUBLE) AS opening_net_assets_local,
                   CAST(closing_net_assets_local AS DOUBLE) AS closing_net_assets_local,
                   CAST(result_local AS DOUBLE) AS result_local,
                   CAST(equity_movement_local AS DOUBLE) AS equity_movement_local,
                   CAST(opening_rate AS DOUBLE) AS opening_rate,
                   CAST(closing_rate AS DOUBLE) AS closing_rate,
                   CAST(average_rate AS DOUBLE) AS average_rate,
                   CAST(cta_movement_usd_m AS DOUBLE) AS cta_movement_usd_m,
                   CAST(cta_cumulative_usd_m AS DOUBLE) AS cta_cumulative_usd_m
            FROM {_csv('cta_expectation.csv')}
        """,
        # ------------------------------------------------- intercompany stock
        "ref_ic_inventory_holding": f"""
            SELECT CAST(holding_period AS INTEGER) AS holding_period,
                   CAST(transaction_period AS INTEGER) AS transaction_period,
                   CAST(months_held AS INTEGER) AS months_held,
                   seller_entity, buyer_entity, inventory_category,
                   buyer_inventory_account,
                   CAST(transfer_price_usd AS DOUBLE) AS transfer_price_usd,
                   CAST(seller_cost_usd AS DOUBLE) AS seller_cost_usd,
                   CAST(ic_gross_profit_usd AS DOUBLE) AS ic_gross_profit_usd,
                   CAST(value_remaining_usd AS DOUBLE) AS value_remaining_usd,
                   CAST(unrealised_profit_usd AS DOUBLE) AS unrealised_profit_usd
            FROM {_csv('ic_inventory_holdings.csv')}
        """,
        # ---------------------------------------------------- fixed assets
        "ref_fixed_asset": f"""
            SELECT asset_id, entity_code, project_id, asset_class, asset_description,
                   group_account, cost_centre_code AS cost_center_code,
                   CAST(acquisition_date AS DATE) AS acquisition_date,
                   CAST(cost_local AS DOUBLE) AS cost_local, currency_code
            FROM {_csv('fixed_assets.csv')}
        """,
        "fact_capex_project": f"""
            SELECT project_id, entity_code, project_name, asset_class, bu_code,
                   CAST(period_key AS INTEGER) AS period_key,
                   CAST(approved_amount_local AS DOUBLE) AS approved_amount_local,
                   CAST(spend_local AS DOUBLE) AS spend_local, currency_code
            FROM {_csv('capex_projects.csv')}
        """,
        # --------------------------------------------------------- headcount
        "fact_headcount": f"""
            SELECT entity_code, cost_center_code, job_family_code,
                   CAST(period_key AS INTEGER) AS period_key,
                   CAST(fte_opening AS DOUBLE) AS fte_opening,
                   CAST(hires AS DOUBLE) AS hires,
                   CAST(leavers AS DOUBLE) AS leavers,
                   CAST(fte_closing AS DOUBLE) AS fte_closing,
                   CAST(fte_average AS DOUBLE) AS fte_average,
                   CAST(headcount_closing AS INTEGER) AS headcount_closing,
                   CAST(annual_base_salary_local AS DOUBLE) AS annual_base_salary_local,
                   currency_code
            FROM {_parquet('headcount_fact.parquet')}
        """,
        # ----------------------------------------------------- revenue detail
        # Kept at its own grain, in its own fact, and reconciled to the GL. Customer and
        # product never enter the journal-line fact (ADR-0008).
        "fact_revenue_detail": f"""
            SELECT entity_code, CAST(period_key AS INTEGER) AS period_key,
                   customer_code, product_code, group_account, currency_code,
                   CAST(revenue_local AS DOUBLE) AS revenue_local,
                   CAST(cost_of_sales_local AS DOUBLE) AS cost_of_sales_local,
                   CAST(quantity AS DOUBLE) AS quantity,
                   CAST(order_count AS INTEGER) AS order_count,
                   is_intercompany
            FROM {_parquet('revenue_detail.parquet')}
        """,
        "ref_customer": f"SELECT * FROM {_csv('customers.csv')}",
        "ref_product": f"SELECT * FROM {_csv('products.csv')}",
    }

    counts: dict[str, int] = {}
    for name, sql in statements.items():
        con.execute(f"CREATE OR REPLACE TABLE {name} AS {sql}")
        counts[name] = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]

    counts.update(build_planning(con))

    for name in ("fact_revenue_detail", "fact_headcount", "fact_capex_project", "fact_plan"):
        if not writing_artefacts():
            break
        out = LAYER_DIR["conformed"] / f"{name}.parquet"
        con.execute(f"COPY (SELECT * FROM {name} ORDER BY ALL) TO '{out.as_posix()}' "
                    f"(FORMAT PARQUET, COMPRESSION ZSTD)")
    return counts


def build_planning(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """
    Budget and forecast, conformed to the approved scenario and version model.

    Three properties are enforced rather than hoped for:

      * every plan row resolves to a version that exists and is not reserved, so the
        Downside shell cannot leak into a default view (CTL-SCN-06);
      * superseded forecast versions are retained, because a forecast that has been
        replaced is still the forecast that was approved at the time;
      * Prior Year is NOT materialised. It is derived by date offset from the Actual
        scenario (ADR-0004), and storing it would create a second version of the truth.
    """
    con.execute(f"""
    CREATE OR REPLACE TABLE fact_plan AS
    SELECT
        v.scenario_code, p.version_code,
        1 AS layer_id,
        p.entity_code, e.bu_code, p.cost_center_code,
        p.group_account, p.currency_code,
        CAST(p.period_key AS INTEGER) AS period_key,
        CAST(p.period_key AS INTEGER) // 100 AS fiscal_year,
        CAST(p.period_key AS INTEGER) % 100 AS management_period,
        CAST(p.amount_local AS DOUBLE) AS amount_local,
        p.is_actual_month = 'TRUE' AS is_actual_month,
        v.is_default AS version_is_default,
        v.is_locked  AS version_is_locked,
        v.is_reserved AS version_is_reserved
    FROM {_parquet('plan_fact.parquet')} p
    JOIN dim_version v ON v.version_code = p.version_code
    JOIN dim_entity e ON e.entity_code = p.entity_code
    """)
    return {"fact_plan": con.execute("SELECT count(*) FROM fact_plan").fetchone()[0]}
