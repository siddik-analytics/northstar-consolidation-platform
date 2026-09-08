"""
The consolidated fact, the statements and the bridges.

## Two facts, and why

`fact_consol_journal` holds every consolidation entry at leg grain, with the process and rule
that produced it, the entities it is about and the evidence it rests on. It is what answers
"why did group equity move" -- a total can only be recomputed, a journal can be read.

`fact_financials` holds the monthly financial position at the consolidation grain: entity x
account x cost centre x partner x period x scenario x version x **layer**. It is what a
reporting layer queries. Layer 1 comes from the translated entity ledgers and layers 2 to 5
from the journal fact, so the two cannot disagree -- and `P4-FCT-01` proves it by rebuilding
one from the other.

Keeping both is a deliberate choice rather than duplication. Aggregating the journals away
would lose the lineage; querying the journals for every report would mean scanning leg-level
detail to answer a question about a caption. They reconcile exactly, which is what makes
holding both safe (ADR-0024).

## The reporting bases

    statutory   layers 1, 2, 3, 5
    management  layers 1, 2, 3, 4, 5

Separated at the architecture level, not by filtering at report time. A management
normalisation can never accidentally reach the reported result because it is not in the set.

## The cash flow

Derived from balance sheet movements, never sourced (ADR-0006). Each balance sheet account
carries a `cash_flow_category`, and the statement is the period movement in each account
sorted into those categories. Because it is an algebraic rearrangement of the balance sheet it
ties to the movement in cash **by construction** -- which is exactly why it has to be tested
anyway: the property only holds if every balance sheet movement lands in exactly one category,
and a mis-categorised account still ties while reporting the wrong thing.

Two effects need explicit handling or the statement reports movements that never happened:

* **Translation on foreign-currency cash** is presented as its own line below financing. It is
  not an operating flow and it is not CTA.
* **Translation on everything else** is a non-cash reconciling item inside operating
  activities. Routing the whole CTA movement through the cash line makes the statement still
  tie while reporting an implausible FX effect on a mostly-USD cash balance -- every balancing
  control passes and only plausibility review catches it (`P4-CF-03`).
"""

from __future__ import annotations

import duckdb

from .config import CONSOL_DIR, MANAGEMENT_LAYERS, STATUTORY_LAYERS, writing_artefacts
from . import cta, mgmt, nci


def build(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    statutory = ", ".join(str(x) for x in STATUTORY_LAYERS)
    management = ", ".join(str(x) for x in MANAGEMENT_LAYERS)

    # ------------------------------------------------------------------ the fact
    con.execute("""
    CREATE OR REPLACE TABLE fact_financials AS
    SELECT 1 AS layer_id, 'ACT' AS scenario_code, 'ACTUAL' AS version_code,
           u.entity_code, u.bu_code, u.cost_center_code, u.partner_entity_code,
           u.group_account, u.period_key, u.fiscal_year, u.currency_code,
           CAST(sum(u.amount_local) AS DECIMAL(18,2)) AS amount_local,
           CAST(sum(u.amount_usd) AS DECIMAL(18,2)) AS amount_usd,
           CAST(NULL AS VARCHAR) AS process,
           -- The year-end close reverses the whole income statement into reserves. It is a
           -- real posting and the balance sheet needs it, but every RESULT measure has to
           -- exclude it or a year's revenue nets to nil. Carrying the character on the row
           -- is what lets one fact serve both without a second copy of the data.
           u.translation_basis AS journal_character
    FROM fact_layer1_usd u
    GROUP BY ALL
    UNION ALL BY NAME
    SELECT j.layer_id, j.scenario_code, j.version_code,
           j.entity_code,
           coalesce(e.bu_code, o.bu_code) AS bu_code,
           CAST(NULL AS VARCHAR) AS cost_center_code,
           j.partner_entity_code, j.group_account, j.period_key, j.fiscal_year,
           j.currency_code,
           CAST(sum(j.amount_local) AS DECIMAL(18,2)) AS amount_local,
           CAST(sum(j.amount_usd) AS DECIMAL(18,2)) AS amount_usd,
           j.process, 'CONSOLIDATION' AS journal_character
    FROM fact_consol_journal j
    LEFT JOIN dim_entity e ON e.entity_code = j.entity_code
    LEFT JOIN dim_entity o ON o.entity_code = j.related_entity_code
    GROUP BY ALL
    """)

    con.execute(f"""
    CREATE OR REPLACE VIEW vw_statutory_fact AS
    SELECT f.*, a.statement, a.fs_caption_l1, a.fs_caption_l2, a.account_class,
           a.is_ebitda, a.is_ebitda_addback, a.cash_flow_category, a.account_name, a.sort_order,
           -- a row that counts towards a RESULT: the close is excluded, because it is the
           -- reversal of the result rather than part of it
           (a.statement = 'IS' AND f.journal_character <> 'CLOSE') AS counts_in_result
    FROM fact_financials f JOIN dim_account a USING (group_account)
    WHERE f.layer_id IN ({statutory})
    """)
    con.execute(f"""
    CREATE OR REPLACE VIEW vw_management_fact AS
    SELECT f.*, a.statement, a.fs_caption_l1, a.fs_caption_l2, a.account_class,
           a.is_ebitda, a.is_ebitda_addback, a.cash_flow_category, a.account_name, a.sort_order,
           (a.statement = 'IS' AND f.journal_character <> 'CLOSE') AS counts_in_result
    FROM fact_financials f JOIN dim_account a USING (group_account)
    WHERE f.layer_id IN ({management})
    """)

    nci.rollforward(con)
    mgmt.ebitda_bridges(con)

    # ------------------------------------------------------------------ income statement
    # Every measure is coalesced where it is built. A FILTER that matches nothing yields
    # NULL, and one NULL anywhere in a subtraction voids the whole line -- so an entity with
    # cost and no revenue silently removed its own gross profit from the group total.
    con.execute("""
    CREATE OR REPLACE TABLE rpt_income_statement AS
    WITH base AS (
        SELECT period_key, fiscal_year, bu_code, entity_code,
               round(-coalesce(sum(amount_usd) FILTER (
                   WHERE group_account LIKE '4%' AND group_account NOT LIKE '49%'), 0), 2)
                   AS revenue_usd,
               round(coalesce(sum(amount_usd) FILTER (
                   WHERE group_account LIKE '5%'), 0), 2) AS cost_of_sales_usd,
               round(coalesce(sum(amount_usd) FILTER (
                   WHERE group_account LIKE '6%'), 0), 2) AS operating_expenses_usd,
               round(coalesce(sum(amount_usd) FILTER (
                   WHERE group_account LIKE '71%' OR group_account LIKE '72%'), 0), 2)
                   AS depreciation_amortisation_usd,
               round(coalesce(sum(amount_usd) FILTER (
                   WHERE group_account LIKE '7%' AND group_account NOT LIKE '71%'
                     AND group_account NOT LIKE '72%'), 0), 2) AS net_finance_usd,
               round(coalesce(sum(amount_usd) FILTER (
                   WHERE group_account LIKE '8%' AND group_account <> '850100'), 0), 2)
                   AS tax_usd,
               round(coalesce(sum(amount_usd) FILTER (
                   WHERE group_account = '850100'), 0), 2) AS nci_attribution_usd,
               round(-coalesce(sum(amount_usd) FILTER (WHERE is_ebitda), 0), 2) AS ebitda_usd,
               round(coalesce(sum(amount_usd) FILTER (WHERE is_ebitda_addback), 0), 2)
                   AS addbacks_usd
        FROM vw_statutory_fact WHERE counts_in_result GROUP BY ALL
    )
    SELECT *,
           round(revenue_usd - cost_of_sales_usd, 2) AS gross_profit_usd,
           round((revenue_usd - cost_of_sales_usd) / nullif(revenue_usd, 0), 6)
               AS gross_margin_pct,
           round(ebitda_usd + addbacks_usd, 2) AS adjusted_ebitda_usd,
           round(ebitda_usd - depreciation_amortisation_usd, 2) AS ebit_usd,
           round(ebitda_usd - depreciation_amortisation_usd - net_finance_usd - tax_usd, 2)
               AS net_income_usd,
           round(ebitda_usd - depreciation_amortisation_usd - net_finance_usd - tax_usd
                 - nci_attribution_usd, 2) AS net_income_parent_usd
    FROM base ORDER BY period_key, bu_code, entity_code
    """)

    # ------------------------------------------------------------------ balance sheet
    con.execute("""
    CREATE OR REPLACE TABLE rpt_balance_sheet AS
    WITH movement AS (
        SELECT period_key, fiscal_year, fs_caption_l2, account_class, sort_order,
               sum(amount_usd) AS movement_usd
        FROM vw_statutory_fact WHERE statement = 'BS' GROUP BY ALL
        UNION ALL BY NAME
        -- The result of the period is part of equity at any date before it is closed. Layer
        -- 1 closes its own income statement into reserves each December; the consolidation
        -- adjustments -- acquired intangible amortisation, the unrealised profit charge, the
        -- share allocated to the minority -- are never closed by anybody, because no entity
        -- ledger owns them. Leaving them out is why a consolidated balance sheet built only
        -- from balance sheet accounts does not balance, and the gap is exactly the
        -- consolidation's effect on the result.
        SELECT period_key, fiscal_year, 'Result for the period' AS fs_caption_l2,
               'EQUITY' AS account_class, 3999 AS sort_order,
               sum(amount_usd) AS movement_usd
        FROM vw_statutory_fact WHERE counts_in_result GROUP BY ALL
    )
    ,
    caption AS (
        -- one row per caption and month before the running sum: several accounts share a
        -- caption and they carry different sort orders, so partitioning on anything finer
        -- silently produces one running balance per account and prints the caption once for
        -- each of them
        SELECT period_key, fiscal_year, fs_caption_l2,
               any_value(account_class) AS account_class,
               min(sort_order) AS sort_order,
               round(sum(movement_usd), 2) AS movement_usd
        FROM movement GROUP BY ALL
    ),
    dense AS (
        -- and a row in every month, whether or not the caption moved. Goodwill moves three
        -- times in four years; without a row for the months in between, the running sum has
        -- nothing to carry it forward and the balance sheet simply loses it from December
        -- while still looking like a balance sheet.
        SELECT c.fs_caption_l2, c.account_class, c.sort_order, d.period_key, d.fiscal_year,
               coalesce(m.movement_usd, 0) AS movement_usd
        FROM (SELECT DISTINCT fs_caption_l2, account_class, sort_order FROM caption) c
        CROSS JOIN (SELECT DISTINCT period_key, fiscal_year FROM dim_date
                    WHERE accounting_period <= 12) d
        LEFT JOIN caption m
               ON m.fs_caption_l2 = c.fs_caption_l2 AND m.period_key = d.period_key
    )
    SELECT fs_caption_l2, account_class, period_key, fiscal_year,
           round(sum(movement_usd) OVER (PARTITION BY fs_caption_l2 ORDER BY period_key
                                         ROWS UNBOUNDED PRECEDING), 2) AS balance_usd,
           movement_usd, sort_order
    FROM dense ORDER BY period_key, sort_order
    """)

    # ------------------------------------------------------------------ cash flow
    con.execute("""
    CREATE OR REPLACE TABLE rpt_cash_flow AS
    WITH bs AS (
        SELECT period_key, fiscal_year, cash_flow_category, group_account,
               sum(amount_usd) AS movement_usd,
               sum(amount_usd) FILTER (WHERE layer_id = 5) AS fx_movement_usd
        FROM vw_statutory_fact WHERE statement = 'BS' GROUP BY ALL
    ),
    pl AS (
        SELECT period_key, fiscal_year, round(-sum(amount_usd), 2) AS result_usd
        FROM vw_statutory_fact WHERE counts_in_result GROUP BY ALL
    ),
    cat AS (
        SELECT period_key, fiscal_year,
               -- a movement in an asset consumes cash; a movement in a liability or in
               -- equity provides it, which is what the sign flip below expresses
               round(-sum(movement_usd) FILTER (
                   WHERE cash_flow_category = 'OP_WC'), 2) AS working_capital_usd,
               round(-sum(movement_usd) FILTER (
                   WHERE cash_flow_category LIKE 'INV%'), 2) AS investing_usd,
               round(-sum(movement_usd) FILTER (
                   WHERE cash_flow_category LIKE 'FIN%'), 2) AS financing_usd,
               round(-sum(movement_usd) FILTER (
                   WHERE cash_flow_category NOT IN ('OP_WC', 'CASH')
                     AND cash_flow_category NOT LIKE 'INV%'
                     AND cash_flow_category NOT LIKE 'FIN%'), 2) AS other_operating_usd,
               round(sum(movement_usd) FILTER (WHERE cash_flow_category = 'CASH'), 2)
                   AS cash_movement_usd,
               -- the translation effect, split: on cash it is its own line, on everything
               -- else it is a non-cash reconciling item inside operating activities
               round(sum(fx_movement_usd) FILTER (WHERE cash_flow_category = 'CASH'), 2)
                   AS fx_on_cash_usd,
               round(-sum(fx_movement_usd) FILTER (WHERE cash_flow_category <> 'CASH'), 2)
                   AS fx_non_cash_usd
        FROM bs GROUP BY ALL
    )
    SELECT c.period_key, c.fiscal_year,
           p.result_usd,
           coalesce(c.other_operating_usd, 0) AS non_cash_and_other_usd,
           coalesce(c.working_capital_usd, 0) AS working_capital_usd,
           coalesce(c.fx_non_cash_usd, 0) AS fx_non_cash_usd,
           round(p.result_usd + coalesce(c.other_operating_usd, 0)
                 + coalesce(c.working_capital_usd, 0), 2) AS operating_cash_flow_usd,
           coalesce(c.investing_usd, 0) AS investing_cash_flow_usd,
           coalesce(c.financing_usd, 0) AS financing_cash_flow_usd,
           coalesce(c.fx_on_cash_usd, 0) AS fx_effect_on_cash_usd,
           coalesce(c.cash_movement_usd, 0) AS net_change_in_cash_usd,
           round(sum(coalesce(c.cash_movement_usd, 0)) OVER (ORDER BY c.period_key
                                                             ROWS UNBOUNDED PRECEDING), 2)
               AS closing_cash_usd
    FROM cat c JOIN pl p USING (period_key, fiscal_year)
    ORDER BY c.period_key
    """)

    # ------------------------------------------------------------------ the bridge
    # Layer by layer, for the measures a reader checks first. This is the artefact that
    # answers "where did this number come from" in one page rather than one week.
    con.execute("""
    CREATE OR REPLACE TABLE rpt_layer_bridge AS
    WITH measure AS (
        SELECT f.layer_id, f.fiscal_year,
               round(-sum(f.amount_usd) FILTER (WHERE a.is_ebitda), 2) AS ebitda_usd,
               round(-sum(f.amount_usd) FILTER (
                   WHERE a.statement = 'IS' AND a.group_account <> '850100'), 2)
                   AS net_income_usd,
               round(sum(f.amount_usd) FILTER (
                   WHERE a.statement = 'BS' AND a.account_class = 'ASSET'), 2)
                   AS total_assets_movement_usd,
               round(-sum(f.amount_usd) FILTER (
                   WHERE a.statement = 'BS' AND a.account_class = 'EQUITY'), 2)
                   AS total_equity_movement_usd
        FROM fact_financials f JOIN dim_account a USING (group_account)
        GROUP BY ALL
    )
    SELECT l.layer_id, l.layer_code, l.layer_name, m.fiscal_year,
           coalesce(m.ebitda_usd, 0) AS ebitda_usd,
           coalesce(m.net_income_usd, 0) AS net_income_usd,
           coalesce(m.total_assets_movement_usd, 0) AS total_assets_movement_usd,
           coalesce(m.total_equity_movement_usd, 0) AS total_equity_movement_usd,
           l.in_statutory_view, l.in_management_view
    FROM measure m
    JOIN dim_consolidation_layer l ON l.layer_id = m.layer_id
    ORDER BY m.fiscal_year, l.layer_id
    """)

    counts = {}
    for name in ("fact_financials", "rpt_income_statement", "rpt_balance_sheet",
                 "rpt_cash_flow", "rpt_layer_bridge", "rpt_nci_rollforward",
                 "rpt_ebitda_bridge"):
        counts[name] = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]

    if writing_artefacts():
        for name in ("fact_financials", "fact_consol_journal", "rpt_income_statement",
                     "rpt_balance_sheet", "rpt_cash_flow", "rpt_layer_bridge",
                     "rpt_goodwill_bridge", "rpt_nci_rollforward", "rpt_cta_rollforward",
                     "rpt_pup_provision", "rpt_ic_exception", "rpt_intangible_schedule",
                     "rpt_ebitda_bridge"):
            out = CONSOL_DIR / f"{name}.parquet"
            con.execute(f"COPY (SELECT * FROM {name} ORDER BY ALL) TO '{out.as_posix()}' "
                        f"(FORMAT PARQUET, COMPRESSION ZSTD)")
    return counts
