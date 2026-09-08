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
           -- the part of the movement that is translation rather than activity. It is what
           -- the cash flow needs to separate the FX effect on cash from a real cash flow,
           -- and it is NOT the CTA: CTA is what the whole balance sheet's translation nets
           -- to inside equity, this is one account's share of the same arithmetic.
           CAST(sum(u.fx_revaluation_usd) AS DECIMAL(18,2)) AS fx_revaluation_usd,
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
           CAST(0 AS DECIMAL(18,2)) AS fx_revaluation_usd,
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
    WITH pl_period AS (
        -- Per period: the whole income statement movement, and the fiscal year to date on
        -- the income statement's own basis. `ytd_usd` restarts each fiscal year because the
        -- window is partitioned by it -- that restart is what makes the result caption a
        -- year-to-date figure rather than an ever-growing one.
        SELECT period_key, fiscal_year,
               sum(sum(amount_usd)) OVER (PARTITION BY fiscal_year ORDER BY period_key
                                          ROWS UNBOUNDED PRECEDING) AS all_usd_cum,
               sum(amount_usd) AS all_usd,
               sum(coalesce(sum(amount_usd) FILTER (WHERE counts_in_result), 0))
                   OVER (PARTITION BY fiscal_year ORDER BY period_key
                         ROWS UNBOUNDED PRECEDING) AS ytd_usd
        FROM vw_statutory_fact WHERE statement = 'IS' GROUP BY period_key, fiscal_year
    ),
    movement AS (
        SELECT period_key, fiscal_year, fs_caption_l2, account_class, sort_order,
               sum(amount_usd) AS movement_usd
        FROM vw_statutory_fact WHERE statement = 'BS' GROUP BY ALL
        UNION ALL BY NAME
        -- ------------------------------------------------------------------ P4-D-01
        -- Equity carries the group's earnings in two captions and the split between them is
        -- a presentation decision, not an accounting one. Total equity is the same either
        -- way, which is why getting it wrong is invisible to every balancing control.
        --
        -- The rule here: **`Result for the period` is the fiscal year to date, on the same
        -- basis as the income statement** -- every income statement account for the current
        -- fiscal year, EXCLUDING the year-end close. Everything else that the cumulative
        -- income statement contains belongs in retained earnings.
        --
        -- Excluding the close is what makes the caption mean one thing in every month. The
        -- close reverses each entity's own result into its reserves in December; including
        -- it would make the caption a different measure in December from the one it is in
        -- November, and it would never agree with the income statement at a year end.
        --
        -- What the first version got wrong was the other half. It presented the cumulative
        -- income statement balance INCLUDING the close, reasoning that the close leaves
        -- behind exactly what is not yet in reserves. That is true for layer 1 and false for
        -- the group: **no entity ledger closes a consolidation adjustment**, because
        -- consolidation adjustments do not exist in any entity's books. So three years of
        -- PPA amortisation, unrealised profit and NCI attribution accumulated in a caption
        -- called "the period's result" -- USD 19.869m at December 2025 against a FY2025
        -- group result of 7.046m -- while total equity stayed exactly right.
        --
        -- The two movements below therefore sum, by construction, to the whole income
        -- statement movement for the period. The split moves; the total cannot.
        SELECT period_key, fiscal_year, 'Result for the period' AS fs_caption_l2,
               'EQUITY' AS account_class, 3999 AS sort_order,
               ytd_usd - coalesce(lag(ytd_usd) OVER (ORDER BY period_key), 0)
                   AS movement_usd
        FROM pl_period
        UNION ALL BY NAME
        -- and the remainder: the prior years' result the entity ledgers closed into their
        -- own reserves, plus the prior years' consolidation adjustments that nothing closes.
        -- Both belong in retained earnings by the year end that follows them.
        SELECT period_key, fiscal_year, 'Retained earnings' AS fs_caption_l2,
               'EQUITY' AS account_class, 3210 AS sort_order,
               all_usd - (ytd_usd - coalesce(lag(ytd_usd) OVER (ORDER BY period_key), 0))
                   AS movement_usd
        FROM pl_period
    )
    ,
    caption AS (
        -- One row per caption, CLASS and month before the running sum: several accounts share
        -- a caption and carry different sort orders, so partitioning on anything finer
        -- silently produces one running balance per account and prints the caption once for
        -- each of them.
        --
        -- The class belongs in the key. 'Intercompany balances' captions the receivables AND
        -- the payables -- deliberately, so that the elimination is visible on both sides --
        -- and collapsing it to one row meant picking one of the two classes arbitrarily.
        -- That is a presentation choice, and it was being made by whichever row the
        -- aggregate happened to see first: the artefact's bytes changed between two builds
        -- of identical data, which is how this was found.
        SELECT period_key, fiscal_year, fs_caption_l2, account_class,
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
        FROM (
            -- the caption spine, resolved ONCE for the whole statement. Taking the sort order
            -- per period instead lets a caption whose accounts move in different months
            -- appear under two sort orders, and the cross join below then prints -- and sums
            -- -- that caption twice in every month.
            SELECT fs_caption_l2, account_class, min(sort_order) AS sort_order
            FROM caption GROUP BY 1, 2
        ) c
        CROSS JOIN (SELECT DISTINCT period_key, fiscal_year FROM dim_date
                    WHERE accounting_period <= 12) d
        LEFT JOIN caption m
               ON m.fs_caption_l2 = c.fs_caption_l2 AND m.account_class = c.account_class
              AND m.period_key = d.period_key
    )
    SELECT fs_caption_l2, account_class, period_key, fiscal_year,
           round(sum(movement_usd) OVER (PARTITION BY fs_caption_l2, account_class
                                         ORDER BY period_key
                                         ROWS UNBOUNDED PRECEDING), 2) AS balance_usd,
           movement_usd, sort_order
    FROM dense ORDER BY period_key, sort_order, account_class, fs_caption_l2
    """)

    # ------------------------------------------------------------------ cash flow
    # An algebraic rearrangement of the balance sheet, not a separate model (ADR-0006).
    #
    #     0 = cash + every other balance sheet account + every income statement account
    #  => cash movement = -(other balance sheet movements) - (result)
    #
    # So the statement ties by construction PROVIDED every non-cash balance sheet account
    # lands in exactly one cash flow category and the whole income statement lands in
    # operating. That proviso is the thing to test, not the tie: a mis-categorised account
    # still ties while reporting the wrong line, which is why `P4-CF-02` tests the partition
    # and not only the total.
    #
    # The translation effect appears in two places and conflating them was a real defect
    # corrected in Phase 1. On CASH it is its own line below financing, because no cash
    # moved. On everything else it is a non-cash reconciling item inside operating
    # activities -- not a working capital swing, because no cash moved there either.
    con.execute("""
    CREATE OR REPLACE TABLE rpt_cash_flow AS
    WITH movement AS (
        -- The year-end close is excluded from both sides. It moves the result into reserves
        -- and nets to zero across the two, so dropping both sides leaves the identity intact
        -- while stopping a 14m non-cash transfer from appearing as a financing flow.
        SELECT period_key, fiscal_year, group_account,
               -- The translation accounts are taken out of every operating, investing and
               -- financing bucket, not only out of financing. The chart files them under
               -- OP_NONCASH, which is right for a statement that does not separate the FX
               -- effect -- but this one does, and leaving them in a bucket AND deriving the
               -- non-cash FX line from them counts the same translation twice.
               CASE WHEN group_account LIKE '330%' OR group_account = '340400'
                    THEN 'CTA' ELSE cash_flow_category END AS cash_flow_category,
               sum(amount_usd) AS movement_usd,
               sum(fx_revaluation_usd) AS fx_usd
        FROM vw_statutory_fact
        WHERE statement = 'BS' AND journal_character <> 'CLOSE'
        GROUP BY ALL
    ),
    pl AS (
        SELECT period_key, fiscal_year, round(-sum(amount_usd), 2) AS result_usd
        FROM vw_statutory_fact WHERE counts_in_result GROUP BY ALL
    ),
    close_entry AS (
        -- The year-end close is excluded from both sides above, and its two sides do not
        -- quite cancel. In local currency the close balances to the cent; translated, its
        -- income statement legs carry each month's average rate and its retained-earnings leg
        -- does not, so the entry as translated is out by a few cents. That difference is a
        -- translation effect and the trial balance already absorbs it into CTA -- which is
        -- why layers 1 and 5 still sum to zero and the balance sheet still balances at 0.00.
        --
        -- Dropping both sides of the entry therefore strands it, and the cash flow was short
        -- by exactly that amount in the three December months where a close exists: 0.08,
        -- 0.03 and 0.03 USD. It is presented here as what it is, computed from the close
        -- entry itself rather than derived as the difference between the two sides of the
        -- statement. A statement that ties because one line is whatever makes it tie is not
        -- a statement that ties.
        SELECT period_key, fiscal_year,
               -sum(amount_usd) AS close_translation_usd
        FROM vw_statutory_fact WHERE journal_character = 'CLOSE' GROUP BY ALL
    ),
    cat AS (
        SELECT period_key, fiscal_year,
               -- Every line is stated NET of its own translation, because no cash moved when
               -- a rate did. Stripping it means the cumulative translation accounts have to
               -- come out of financing too: they are the offsetting side of the same
               -- arithmetic, and leaving them in would remove the effect twice.
               (-coalesce(sum(movement_usd) FILTER (
                   WHERE cash_flow_category IN ('OP_NI', 'OP_NONCASH')), 0))
                   AS non_cash_and_other_usd,
               (-coalesce(sum(movement_usd) FILTER (
                   WHERE cash_flow_category = 'OP_WC'), 0)) AS working_capital_usd,
               (-coalesce(sum(movement_usd) FILTER (
                   WHERE cash_flow_category LIKE 'INV%'), 0)) AS investing_cash_flow_usd,
               (-coalesce(sum(movement_usd) FILTER (
                   WHERE cash_flow_category LIKE 'FIN%'), 0)) AS financing_cash_flow_usd,
               -- the cumulative translation adjustment posted for the period. It is taken
               -- out of financing above and used below to derive the non-cash reconciling
               -- item, because CTA is the offsetting side of every translation effect on
               -- the balance sheet -- not a financing flow and not an effect on cash.
               (coalesce(sum(movement_usd) FILTER (
                   WHERE cash_flow_category = 'CTA'), 0)) AS cta_movement_usd,
               (coalesce(sum(movement_usd) FILTER (
                   WHERE cash_flow_category = 'CASH'), 0)) AS net_change_in_cash_usd,
               -- the translation on foreign-currency CASH: its own line below financing,
               -- because it is not an operating, investing or financing flow. It is NOT the
               -- cumulative translation adjustment, which is what the whole balance sheet's
               -- translation nets to inside equity.
               (coalesce(sum(fx_usd) FILTER (
                   WHERE cash_flow_category = 'CASH'), 0)) AS fx_effect_on_cash_usd,
               -- the translation on everything else: a non-cash reconciling item inside
               -- operating activities, not a working capital swing
               -- what is left of the translation once the effect on cash is taken out:
               -- the FX policy's second component (section 4), a non-cash reconciling item
               -- inside operating activities and NOT a working capital movement, because
               -- no cash moved when a rate did
               (-coalesce(sum(movement_usd) FILTER (
                   WHERE cash_flow_category = 'CTA'), 0)
                     - coalesce(sum(fx_usd) FILTER (
                   WHERE cash_flow_category = 'CASH'), 0)) AS fx_non_cash_usd
        FROM movement GROUP BY ALL
    )
    SELECT c.period_key, c.fiscal_year,
           round(p.result_usd, 2) AS result_usd,
           round(c.non_cash_and_other_usd, 2) AS non_cash_and_other_usd,
           round(c.working_capital_usd, 2) AS working_capital_usd,
           round(c.fx_non_cash_usd, 2) AS fx_non_cash_usd,
           round(coalesce(e.close_translation_usd, 0), 2) AS close_translation_usd,
           round(p.result_usd + c.non_cash_and_other_usd + c.working_capital_usd
                 + c.fx_non_cash_usd + coalesce(e.close_translation_usd, 0), 2)
               AS operating_cash_flow_usd,
           round(c.investing_cash_flow_usd, 2) AS investing_cash_flow_usd,
           round(c.financing_cash_flow_usd, 2) AS financing_cash_flow_usd,
           round(c.fx_effect_on_cash_usd, 2) AS fx_effect_on_cash_usd,
           round(c.net_change_in_cash_usd, 2) AS net_change_in_cash_usd,
           round(sum(c.net_change_in_cash_usd) OVER w, 2) AS closing_cash_usd,
           round(coalesce(sum(c.net_change_in_cash_usd) OVER w
                          - c.net_change_in_cash_usd, 0), 2) AS opening_cash_usd
    FROM cat c JOIN pl p USING (period_key, fiscal_year)
    LEFT JOIN close_entry e USING (period_key, fiscal_year)
    WINDOW w AS (ORDER BY c.period_key ROWS UNBOUNDED PRECEDING)
    ORDER BY c.period_key
    """)

    # ------------------------------------------------------------------ the bridge
    # Layer by layer, for the measures a reader checks first. This is the artefact that
    # answers "where did this number come from" in one page rather than one week.
    #
    # P4-D-03: the income statement measures exclude the year-end close, exactly as
    # `rpt_income_statement` and `rpt_ebitda_bridge` do. Including it nets layer 1's year to
    # approximately nil, so the bridge showed the group's net income arriving almost entirely
    # from the consolidation layers -- the opposite of the truth, in the one artefact whose
    # job is to say where a number came from. The balance sheet movements below DO include
    # the close, because moving the result into reserves is a real equity movement.
    #
    # Found by `P4-XAR-11` the first time it ran: a third instance of the same close defect,
    # in a third artefact, none of which any accounting control could see.
    con.execute("""
    CREATE OR REPLACE TABLE rpt_layer_bridge AS
    WITH measure AS (
        SELECT f.layer_id, f.fiscal_year,
               round(-coalesce(sum(f.amount_usd) FILTER (
                   WHERE a.is_ebitda AND f.journal_character <> 'CLOSE'), 0), 2)
                   AS ebitda_usd,
               round(-coalesce(sum(f.amount_usd) FILTER (
                   WHERE a.statement = 'IS' AND a.group_account <> '850100'
                     AND f.journal_character <> 'CLOSE'), 0), 2) AS net_income_usd,
               round(coalesce(sum(f.amount_usd) FILTER (
                   WHERE a.statement = 'BS' AND a.account_class = 'ASSET'), 0), 2)
                   AS total_assets_movement_usd,
               round(-coalesce(sum(f.amount_usd) FILTER (
                   WHERE a.statement = 'BS' AND a.account_class = 'EQUITY'), 0), 2)
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

    # ------------------------------------------------------- statutory vs management
    # The two bases differ by layer 4 and by nothing else. That is an arithmetic consequence
    # of the layer architecture rather than a hope, so the proof is stated as a table a reader
    # can check line by line: seven headline measures, both bases, the difference, and the
    # layer-4 total that must explain it exactly.
    #
    # Flow measures are the year's postings. Balance measures are cumulative to the year end,
    # because a balance sheet caption is a position and not a movement -- and the year-end
    # close is included in both, since it moves the result into reserves and nets to zero.
    con.execute("""
    CREATE OR REPLACE TABLE rpt_basis_comparison AS
    WITH m AS (
        SELECT f.layer_id, f.fiscal_year, f.period_key,
               (a.statement = 'IS' AND f.journal_character <> 'CLOSE') AS counts_in_result,
               f.amount_usd, a.statement, a.account_class, a.is_ebitda, a.group_account
        FROM fact_financials f JOIN dim_account a USING (group_account)
        WHERE NOT a.is_statistical
    ),
    flow AS (
        SELECT layer_id, fiscal_year, 'Revenue' AS measure,
               -coalesce(sum(amount_usd) FILTER (WHERE group_account LIKE '4%'
                                          AND group_account NOT LIKE '49%'), 0) AS v
        FROM m WHERE counts_in_result GROUP BY ALL
        UNION ALL BY NAME
        SELECT layer_id, fiscal_year, 'Gross profit' AS measure,
               -coalesce(sum(amount_usd) FILTER (WHERE (group_account LIKE '4%'
                                               AND group_account NOT LIKE '49%')
                                           OR group_account LIKE '5%'), 0) AS v
        FROM m WHERE counts_in_result GROUP BY ALL
        UNION ALL BY NAME
        SELECT layer_id, fiscal_year, 'EBITDA' AS measure,
               -coalesce(sum(amount_usd) FILTER (WHERE is_ebitda), 0) AS v
        FROM m WHERE counts_in_result GROUP BY ALL
        UNION ALL BY NAME
        SELECT layer_id, fiscal_year, 'EBIT' AS measure,
               -coalesce(sum(amount_usd) FILTER (WHERE is_ebitda
                                           OR group_account LIKE '71%'
                                           OR group_account LIKE '72%'), 0) AS v
        FROM m WHERE counts_in_result GROUP BY ALL
        UNION ALL BY NAME
        SELECT layer_id, fiscal_year, 'Net income' AS measure,
               -coalesce(sum(amount_usd) FILTER (WHERE statement = 'IS'
                                          AND group_account <> '850100'), 0) AS v
        FROM m WHERE counts_in_result GROUP BY ALL
    ),
    yend AS (SELECT fiscal_year AS fy, max(period_key) AS pk
             FROM fact_financials GROUP BY 1),
    bal AS (
        SELECT m.layer_id, y.fy AS fiscal_year, 'Total assets' AS measure,
               coalesce(sum(m.amount_usd) FILTER (WHERE m.account_class = 'ASSET'), 0) AS v
        FROM m CROSS JOIN yend y
        WHERE m.statement = 'BS' AND m.period_key <= y.pk
        GROUP BY 1, 2
        UNION ALL BY NAME
        SELECT m.layer_id, y.fy AS fiscal_year, 'Total equity' AS measure,
               -coalesce(sum(m.amount_usd) FILTER (WHERE m.account_class = 'EQUITY'), 0) AS v
        FROM m CROSS JOIN yend y
        WHERE m.statement = 'BS' AND m.period_key <= y.pk
        GROUP BY 1, 2
    ),
    all_m AS (SELECT * FROM flow UNION ALL BY NAME SELECT * FROM bal),
    agg AS (
        SELECT measure, fiscal_year,
               round(coalesce(sum(v) FILTER (WHERE layer_id IN (SELECT layer_id
                   FROM dim_consolidation_layer WHERE in_statutory_view)), 0), 2)
                   AS statutory_usd,
               round(coalesce(sum(v) FILTER (WHERE layer_id IN (SELECT layer_id
                   FROM dim_consolidation_layer WHERE in_management_view)), 0), 2)
                   AS management_usd,
               round(coalesce(sum(v) FILTER (WHERE layer_id = 4), 0), 2) AS layer4_usd
        FROM all_m GROUP BY ALL
    )
    SELECT measure, fiscal_year, statutory_usd, management_usd,
           round(management_usd - statutory_usd, 2) AS difference_usd, layer4_usd,
           abs(round(management_usd - statutory_usd, 2) - layer4_usd) <= 0.01
               AS explained_by_layer_4
    FROM agg
    ORDER BY measure, fiscal_year
    """)

    counts = {}
    for name in ("fact_financials", "rpt_income_statement", "rpt_balance_sheet",
                 "rpt_cash_flow", "rpt_layer_bridge", "rpt_basis_comparison",
                 "rpt_nci_rollforward",
                 "rpt_ebitda_bridge"):
        counts[name] = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]

    if writing_artefacts():
        for name in ("fact_financials", "fact_consol_journal", "rpt_income_statement",
                     "rpt_balance_sheet", "rpt_cash_flow", "rpt_layer_bridge",
                     "rpt_basis_comparison",
                     "rpt_goodwill_bridge", "rpt_nci_rollforward", "rpt_cta_rollforward",
                     "rpt_pup_provision", "rpt_ic_exception", "rpt_intangible_schedule",
                     "rpt_ebitda_bridge"):
            out = CONSOL_DIR / f"{name}.parquet"
            con.execute(f"COPY (SELECT * FROM {name} ORDER BY ALL) TO '{out.as_posix()}' "
                        f"(FORMAT PARQUET, COMPRESSION ZSTD)")
    return counts
