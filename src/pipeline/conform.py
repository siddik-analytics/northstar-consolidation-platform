"""
mapped -> conformed: the finance data model the consolidation engine will consume.

Two facts and a set of validation views.  Nothing here consolidates: there is no
elimination, no translation, no adjustment layer and no consolidated statement.  Everything
produced is layer 1 -- entity as reported, in the entity's own functional currency.

`fact_journal_line` keeps the **journal-line grain**.  It is tempting to aggregate at this
point, and it would be wrong: the moment the grain is lost, a mapping cannot be traced back
to the posting that produced it, an elimination cannot be matched to its document, and a
reviewer cannot answer "why is this number here".  `fact_trial_balance` is the aggregate,
built from the fact rather than alongside it, so the two cannot disagree.

The validation views exist to prove the mapping worked.  They are **not** financial
statements: they are layer 1 only, they carry both legs of every intercompany transaction,
and they exclude nothing that consolidation would remove.  They are named accordingly.
"""

from __future__ import annotations

import duckdb

from .config import LAYER_DIR, writing_artefacts

#: The declared grain of the conformed GL fact.  Enforced, not asserted.
FACT_GRAIN = ("erp_system", "source_file", "journal_id", "line_number")


def build(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    counts: dict[str, int] = {}

    # ------------------------------------------------------------- journal line
    con.execute("""
    CREATE OR REPLACE TABLE fact_journal_line AS
    SELECT
        -- lineage: every one of these is required to get back to the extract
        line_uid,
        erp_system, source_file, source_row_ordinal, ingest_build_id,
        source_entity_key, source_account, source_account_name, source_period_raw,
        source_line_attributes, source_native_amount, source_normal_balance_declared,
        source_translated_amount, source_translated_currency,
        journal_id, document_id, document_type, line_number,
        source_event_type, source_description,
        -- conformed keys
        1 AS layer_id,
        'ACT' AS scenario_code,
        'ACTUAL' AS version_code,
        entity_code, bu_code, country_code, cost_center_code, native_dept_code AS dept_code,
        partner_entity_code, customer_code, product_code,
        group_account, group_account_name, statement, fs_caption_l1, fs_caption_l2,
        account_class, reporting_block, cash_flow_category, fx_method,
        is_intercompany, is_ebitda, is_ebitda_addback, is_statistical,
        include_in_tb_balance,
        -- period
        posting_date, fiscal_year, period_key, accounting_period, management_period,
        special_period, special_period_type, is_adjustment_period,
        -- amounts, in the entity's functional currency. There is no USD column: this is
        -- layer 1 and translation is Phase 4's work (ADR-0005).
        --
        -- DECIMAL(18,2) throughout, set at the standardised layer where the canonical
        -- sign is applied.
        functional_currency AS currency_code, source_currency,
        signed_local_amount, debit_local, credit_local,
        -- mapping provenance
        mapping_status, mapping_rule_id, chart_mapping_type_applied,
        is_presentation_reclass, presentation_reclass_type,
        -- the two views of the department function, kept side by side so that a
        -- disagreement between what the line declares and where it was posted stays
        -- visible downstream (P3-MAP-07)
        dept_function, dimension_dept_function, native_cost_center_code
    FROM stg_mapped_enriched
    """)
    counts["fact_journal_line"] = con.execute(
        "SELECT count(*) FROM fact_journal_line").fetchone()[0]

    # --------------------------------------------------------- trial balance
    # Built FROM the fact, never alongside it.
    con.execute("""
    CREATE OR REPLACE TABLE fact_trial_balance AS
    SELECT
        layer_id, scenario_code, version_code,
        entity_code, bu_code, cost_center_code, group_account,
        partner_entity_code,
        fiscal_year, period_key, accounting_period, management_period,
        special_period_type, is_adjustment_period,
        currency_code,
        sum(signed_local_amount) AS signed_local_amount,
        sum(debit_local)  AS debit_local,
        sum(credit_local) AS credit_local,
        count(*) AS line_count
    FROM fact_journal_line
    GROUP BY ALL
    """)
    counts["fact_trial_balance"] = con.execute(
        "SELECT count(*) FROM fact_trial_balance").fetchone()[0]

    # ------------------------------------------------- group adjustment staging
    # Phase 3 does not post consolidation entries, and this table is empty by design.
    # It exists because the architecture has to distinguish three different things that a
    # single "adjustment" column would blur:
    #
    #   a source posting          something an entity's own ledger says
    #   a mapping reclassification  the same amount under a different group caption
    #   a group adjustment        an amount that exists only on consolidation
    #
    # The worked example is the operating lease right-of-use asset: the Kestrel entities do
    # not recognise one locally, so Kestrel's special period 16 has nothing to reclassify
    # and the group figure is carried entirely by the other entities. If a future phase
    # needs to raise it as a top-side entry, this is where it belongs -- at layer 3 or 4,
    # posted by the consolidation engine, never by ingestion. `P3-ADJ-01` fails the build
    # if Phase 3 ever writes a row here.
    con.execute("""
    CREATE OR REPLACE TABLE stg_group_adjustment (
        adjustment_id      VARCHAR,
        layer_id           INTEGER,
        entity_code        VARCHAR,
        group_account      VARCHAR,
        period_key         INTEGER,
        currency_code      VARCHAR,
        signed_amount      DOUBLE,
        adjustment_type    VARCHAR,
        raised_by_phase    INTEGER,
        narrative          VARCHAR,
        preparer           VARCHAR,
        approver           VARCHAR,
        reverses_next_period BOOLEAN
    )""")
    counts["stg_group_adjustment"] = 0

    # ------------------------------------------ group accounts with no source
    # CTL-MAP-06: which group accounts received nothing, and whether that is expected.
    con.execute("""
    CREATE OR REPLACE TABLE rpt_group_account_coverage AS
    SELECT
        a.group_account, a.account_name, a.statement, a.reporting_block,
        a.is_statistical,
        coalesce(p.line_count, 0) AS line_count,
        coalesce(p.erp_systems, []) AS posted_by,
        CASE
            WHEN p.line_count > 0                       THEN 'POSTED'
            WHEN a.is_statistical                       THEN 'STATISTICAL_NOT_IN_LEDGER'
            WHEN a.group_account LIKE '33%'             THEN 'CREATED_BY_TRANSLATION'
            WHEN a.group_account LIKE '34%'             THEN 'CREATED_BY_CONSOLIDATION'
            WHEN a.group_account IN ('160100','160200','160300','165100','166100',
                                     '175200','240100','850100','851100','790100')
                                                        THEN 'CREATED_BY_CONSOLIDATION'
            WHEN m.group_account IS NOT NULL            THEN 'MAPPED_BUT_UNUSED'
            ELSE 'NO_SOURCE_ACCOUNT_MAPS_HERE'
        END AS coverage_status
    FROM dim_account a
    LEFT JOIN (
        SELECT group_account, count(*) AS line_count,
               list_sort(list_distinct(list(erp_system))) AS erp_systems
        FROM fact_journal_line GROUP BY 1
    ) p USING (group_account)
    LEFT JOIN (SELECT DISTINCT target_group_account AS group_account FROM map_rules
               UNION SELECT DISTINCT default_group_account FROM dim_source_account) m
           USING (group_account)
    ORDER BY a.sort_order
    """)
    counts["rpt_group_account_coverage"] = con.execute(
        "SELECT count(*) FROM rpt_group_account_coverage").fetchone()[0]

    # ------------------------------------------------------- validation views
    # LAYER 1 ONLY. Both legs of every intercompany transaction are present, nothing is
    # eliminated and nothing is translated, so these are not financial statements and are
    # named so that nobody can mistake them for one.
    con.execute("""
    CREATE OR REPLACE VIEW vw_layer1_pl_measures AS
    SELECT
        fiscal_year, period_key, entity_code, bu_code, currency_code,
        -- external revenue: revenue accounts, excluding the intercompany 49x block and
        -- net of the contra-revenue accounts, which is how the anchor defines it
        round(sum(CASE WHEN group_account LIKE '4%' AND group_account NOT LIKE '49%'
                       THEN -signed_local_amount ELSE 0 END), 2) AS external_revenue,
        round(sum(CASE WHEN group_account LIKE '49%'
                       THEN -signed_local_amount ELSE 0 END), 2) AS intercompany_revenue,
        round(sum(CASE WHEN group_account LIKE '5%' AND group_account NOT LIKE '59%'
                       THEN signed_local_amount ELSE 0 END), 2) AS cost_of_sales,
        round(sum(CASE WHEN group_account LIKE '59%'
                       THEN signed_local_amount ELSE 0 END), 2) AS intercompany_cost_of_sales,
        round(sum(CASE WHEN group_account LIKE '6%' AND group_account NOT LIKE '695%'
                       THEN signed_local_amount ELSE 0 END), 2) AS operating_expense,
        round(sum(CASE WHEN group_account LIKE '695%'
                       THEN signed_local_amount ELSE 0 END), 2) AS intercompany_opex,
        round(sum(CASE WHEN group_account LIKE '7%'
                       THEN signed_local_amount ELSE 0 END), 2) AS below_ebit,
        round(sum(CASE WHEN group_account LIKE '8%'
                       THEN signed_local_amount ELSE 0 END), 2) AS tax
    FROM fact_journal_line
    -- The year-end close reverses the whole income statement into equity. Including it
    -- would net every P&L measure to nil, so it is excluded from every result measure --
    -- the same treatment the Phase 2 source controls apply.
    WHERE special_period_type IS DISTINCT FROM 'STATUTORY_CLOSE'
      AND source_event_type IS DISTINCT FROM 'YEAR_END_CLOSE'
    GROUP BY ALL
    """)

    # One place where a local amount becomes a USD amount for comparison. Stated once as
    # a macro so no view can quietly translate on a different rule.
    con.execute("""
    CREATE OR REPLACE MACRO usd(local_amount, rate) AS
        CAST(round(local_amount * rate, 2) AS DECIMAL(18,2))
    """)

    # A validation-only conversion to USD at the approved monthly AVERAGE rates. This is
    # not the translation engine: no balance sheet is translated at closing rates, no
    # cumulative translation adjustment is computed, nothing is posted and nothing is
    # stored as a fact. It exists so that the mapped result can be compared against the
    # Phase 2 source-layer targets, which are stated in USD. Phase 4 owns translation.
    con.execute("""
    CREATE OR REPLACE VIEW vw_validation_pl_usd AS
    SELECT
        m.fiscal_year, m.period_key, m.entity_code, m.bu_code,
        -- rounded to the cent and held as DECIMAL for the same reason the fact is:
        -- the sums below must not depend on the order the threads finish in
        usd(m.external_revenue, r.rate_usd_per_unit)           AS external_revenue_usd,
        usd(m.intercompany_revenue, r.rate_usd_per_unit)       AS intercompany_revenue_usd,
        usd(m.cost_of_sales, r.rate_usd_per_unit)              AS cost_of_sales_usd,
        usd(m.intercompany_cost_of_sales, r.rate_usd_per_unit) AS intercompany_cost_of_sales_usd,
        usd(m.operating_expense, r.rate_usd_per_unit)          AS operating_expense_usd,
        usd(m.intercompany_opex, r.rate_usd_per_unit)          AS intercompany_opex_usd,
        usd(m.below_ebit, r.rate_usd_per_unit)                 AS below_ebit_usd,
        usd(m.tax, r.rate_usd_per_unit)                        AS tax_usd
    FROM vw_layer1_pl_measures m
    JOIN ref_fx_rate r
      ON r.currency_code = m.currency_code
     AND r.period_key = m.period_key
     AND r.rate_type = 'AVG'
     AND r.rate_set = CASE WHEN m.fiscal_year = 2026 THEN 'FORECAST' ELSE 'ACTUAL' END
    """)

    # Gross margin by business unit is the measure that catches a mapping which balances
    # but is wrong: move payroll from cost of sales to SG&A and every statement still ties,
    # while the margin moves. It is computed on EXTERNAL revenue and cost, which is the
    # basis the business-unit anchor is stated on.
    con.execute("""
    CREATE OR REPLACE VIEW vw_validation_gross_margin_usd AS
    SELECT fiscal_year, bu_code,
           round(sum(external_revenue_usd) / 1e6, 6)  AS revenue_usd_m,
           round(sum(cost_of_sales_usd) / 1e6, 6)     AS cost_of_sales_usd_m,
           round((sum(external_revenue_usd) - sum(cost_of_sales_usd)) / 1e6, 6)
               AS gross_profit_usd_m,
           round((sum(external_revenue_usd) - sum(cost_of_sales_usd))
                 / nullif(sum(external_revenue_usd), 0), 6) AS gross_margin_pct
    FROM vw_validation_pl_usd
    GROUP BY ALL
    """)

    # The balance sheet is compared at CLOSING rates, cumulatively, because a balance is a
    # position and not a flow. Same qualification: validation only.
    con.execute("""
    CREATE OR REPLACE VIEW vw_validation_bs_usd AS
    SELECT f.fiscal_year, f.group_account, f.entity_code, f.bu_code,
           sum(usd(f.signed_local_amount, r.rate_usd_per_unit)) AS closing_balance_usd
    FROM (
        SELECT y.fiscal_year, j.entity_code, j.bu_code, j.currency_code, j.group_account,
               sum(j.signed_local_amount) AS signed_local_amount
        FROM fact_journal_line j
        JOIN (SELECT DISTINCT fiscal_year FROM fact_journal_line) y
          ON j.period_key <= y.fiscal_year * 100 + 12
        WHERE j.group_account LIKE '1%' OR j.group_account LIKE '2%'
           OR j.group_account LIKE '3%'
        GROUP BY ALL
    ) f
    JOIN ref_fx_rate r
      ON r.currency_code = f.currency_code
     AND r.period_key = f.fiscal_year * 100 + 12
     AND r.rate_type = 'CLOSE'
     AND r.rate_set = CASE WHEN f.fiscal_year = 2026 THEN 'FORECAST' ELSE 'ACTUAL' END
    GROUP BY ALL
    """)

    # Every committed artefact needs a total order. Without one, DuckDB's parallel scan is
    # free to emit rows in a different sequence on an identical input, and two runs of the
    # same build write different bytes -- which would make the determinism proof
    # meaningless. The journal-line fact orders by its lineage; everything else is small
    # enough to order by all of its columns.
    ARTEFACT_ORDER = {
        "fact_journal_line": "erp_system, source_file, source_row_ordinal",
        "fact_trial_balance": "ALL",
        "rpt_group_account_coverage": "ALL",
    }
    for name, by in ARTEFACT_ORDER.items():
        if not writing_artefacts():
            break
        out = LAYER_DIR["conformed"] / f"{name}.parquet"
        con.execute(f"COPY (SELECT * FROM {name} ORDER BY {by}) TO '{out.as_posix()}' "
                    f"(FORMAT PARQUET, COMPRESSION ZSTD)")
    return counts
