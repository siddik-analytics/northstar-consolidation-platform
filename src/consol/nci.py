"""
Non-controlling interests.

`NIG-510` Northstar Parts UK is 80% owned by `NIG-500` and 20% by its founding management. It
is the group's only non-controlling interest, and it is **fully consolidated**: every asset,
liability, income and expense line comes in at 100%, exactly as for a wholly owned subsidiary,
and the 20% is then presented separately within equity and below the tax line.

The intuitive alternative -- consolidating 80% of each line -- is a real error made in
spreadsheet consolidations. It would understate revenue, EBITDA and every balance sheet
caption, break the reconciliation between the consolidated accounts and the entity trial
balances, and quietly change covenant leverage, because the credit agreement defines
Consolidated EBITDA on the group and not on the group's economic share.

## What is allocated

    Dr  850100  Net income attributable to non-controlling interests    income statement
    Cr  340200  Non-controlling interests - share of result             equity

    amount = NIG-510's net income after tax, consolidated, x the NCI % for the period

"Consolidated" matters: the subsidiary's own result is not the same as its contribution to the
group. Its intercompany sales are eliminated, its share of unrealised profit is removed, and
the acquired intangibles bought with it amortise at group level. Allocating the entity's
reported result instead would give the minority a share of profit the group never made.

The roll-forward is held in five accounts rather than as one moving balance, so every line of
it can be tested:

    closing NCI = opening + share of result - dividends + share of CTA + ownership changes

Losses allocate on the same basis, with no floor at zero: a loss-making period allocates the
NCI share even where that drives the balance negative, and nothing is reallocated to the
group.
"""

from __future__ import annotations

import duckdb

from .config import (LAYER, NCI_CTA, NCI_DIVIDEND, NCI_IN_PL, NCI_OPENING, NCI_OWNERSHIP,
                     NCI_RESULT)
from .journals import post_sql

#: The entity ledger account the subsidiary books a distribution to its shareholders through.
#: The NCI's share of it reduces the NCI balance rather than group equity.
DISTRIBUTION_ACCOUNT = "320300"


def build(con: duckdb.DuckDBPyConnection, scenario: str = "ACT",
          version: str = "ACTUAL") -> dict[str, int]:
    layer = LAYER["CONSOL_ADJ"]

    # ------------------------------------------------------------------ the subsidiary's
    # consolidated result: its own income statement, plus every consolidation entry that
    # relates to it. Layer 5 is excluded because translation belongs in the CTA share below,
    # not in the result share -- counting it in both is the double count this splits apart.
    con.execute("""
    CREATE OR REPLACE TABLE stg_nci_result AS
    WITH entity_result AS (
        SELECT u.entity_code, u.period_key, u.fiscal_year,
               round(-sum(u.amount_usd), 2) AS result_usd
        FROM fact_layer1_usd u
        JOIN dim_account a USING (group_account)
        WHERE a.statement = 'IS' AND a.group_account <> '850100'
          -- the close reverses the year's result into reserves; counting it would net the
          -- subsidiary's whole year to nil and allocate the minority a share of nothing
          AND u.translation_basis <> 'CLOSE'
        GROUP BY ALL
    ),
    consolidation_effect AS (
        -- Only LAYER 3. Layer 2 is deliberately excluded, and it is the difference between
        -- a defensible allocation and a nonsensical one.
        --
        -- An intercompany elimination removes a matched pair -- the seller's revenue and the
        -- buyer's cost -- and changes group profit by nothing. Attributing the buyer's half
        -- to the buyer, without attributing the seller's half to the seller, hands the buyer
        -- its goods for free: NIG-510's own result of USD (0.78)m becomes +4.71m, which is
        -- simply its external result, as though its purchases from Meridian had cost
        -- nothing. The minority would then be allocated a share of profit that belongs to
        -- the entity that made the goods.
        --
        -- Layer 3 is different: acquired intangible amortisation and the unrealised profit
        -- charge DO change group profit, and each is attributable to the subsidiary it
        -- arose on, so each belongs in the base the minority's share is taken on.
        SELECT j.related_entity_code AS entity_code, j.period_key, j.fiscal_year,
               round(-sum(j.amount_usd), 2) AS result_usd
        FROM fact_consol_journal j
        JOIN dim_account a USING (group_account)
        WHERE a.statement = 'IS' AND j.layer_id = 3
          AND j.related_entity_code IS NOT NULL AND a.group_account <> '850100'
        GROUP BY ALL
    ),
    combined AS (
        SELECT * FROM entity_result UNION ALL BY NAME SELECT * FROM consolidation_effect
    )
    SELECT c.entity_code, c.period_key, c.fiscal_year,
           round(sum(c.result_usd), 2) AS consolidated_result_usd,
           any_value(o.effective_nci_pct) AS nci_pct,
           round(sum(c.result_usd) * any_value(o.effective_nci_pct), 2) AS nci_share_usd
    FROM combined c
    JOIN dim_ownership_period o
      ON o.entity_code = c.entity_code AND o.period_key = c.period_key
    WHERE o.effective_nci_pct > 0
    GROUP BY ALL
    ORDER BY c.entity_code, c.period_key
    """)

    legs = post_sql(con, f"""
    SELECT 'NCI-' || substr(md5(entity_code || CAST(period_key AS VARCHAR)), 1, 10)
               AS consol_journal_id,
           1 AS line_number, {layer} AS layer_id, 'NCI_RESULT' AS process,
           'NCI-POLICY' AS rule_id, 'ELIM-CON' AS entity_code,
           entity_code AS related_entity_code, CAST(NULL AS VARCHAR) AS partner_entity_code,
           '{NCI_IN_PL}' AS group_account, period_key, fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(nci_share_usd AS DECIMAL(18,2)) AS amount_usd,
           'Net income attributable to non-controlling interests' AS narrative,
           entity_code || ' consolidated result x ' || CAST(nci_pct AS VARCHAR) AS evidence
    FROM stg_nci_result WHERE abs(nci_share_usd) > 0.005
    UNION ALL BY NAME
    SELECT 'NCI-' || substr(md5(entity_code || CAST(period_key AS VARCHAR)), 1, 10)
               AS consol_journal_id,
           2 AS line_number, {layer} AS layer_id, 'NCI_RESULT' AS process,
           'NCI-POLICY' AS rule_id, 'ELIM-CON' AS entity_code,
           entity_code AS related_entity_code, CAST(NULL AS VARCHAR) AS partner_entity_code,
           '{NCI_RESULT}' AS group_account, period_key, fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(-nci_share_usd AS DECIMAL(18,2)) AS amount_usd,
           'Non-controlling interests - share of the result for the period' AS narrative,
           entity_code || ' share of result' AS evidence
    FROM stg_nci_result WHERE abs(nci_share_usd) > 0.005
    """)

    # ------------------------------------------------------------------ distributions
    # The subsidiary's distribution is in its own ledger; the minority's share of it belongs
    # against the NCI balance, not against group equity.
    dividend_legs = post_sql(con, f"""
    WITH dist AS (
        SELECT u.entity_code, u.period_key, u.fiscal_year,
               round(sum(u.amount_usd) * o.effective_nci_pct, 2) AS nci_share_usd
        FROM fact_layer1_usd u
        JOIN dim_ownership_period o
          ON o.entity_code = u.entity_code AND o.period_key = u.period_key
        WHERE u.group_account = '{DISTRIBUTION_ACCOUNT}' AND o.effective_nci_pct > 0
        GROUP BY u.entity_code, u.period_key, u.fiscal_year, o.effective_nci_pct
    )
    SELECT 'NCID-' || substr(md5(entity_code || CAST(period_key AS VARCHAR)), 1, 10)
               AS consol_journal_id,
           1 AS line_number, {layer} AS layer_id, 'NCI_DIVIDEND' AS process,
           'NCI-POLICY' AS rule_id, 'ELIM-CON' AS entity_code,
           entity_code AS related_entity_code, CAST(NULL AS VARCHAR) AS partner_entity_code,
           '{NCI_DIVIDEND}' AS group_account, period_key, fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(nci_share_usd AS DECIMAL(18,2)) AS amount_usd,
           'Distribution to the non-controlling shareholder' AS narrative,
           entity_code || ' distribution, NCI share' AS evidence
    FROM dist WHERE abs(nci_share_usd) > 0.005
    UNION ALL BY NAME
    SELECT 'NCID-' || substr(md5(entity_code || CAST(period_key AS VARCHAR)), 1, 10)
               AS consol_journal_id,
           2 AS line_number, {layer} AS layer_id, 'NCI_DIVIDEND' AS process,
           'NCI-POLICY' AS rule_id, 'ELIM-CON' AS entity_code,
           entity_code AS related_entity_code, CAST(NULL AS VARCHAR) AS partner_entity_code,
           '{DISTRIBUTION_ACCOUNT}' AS group_account, period_key, fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(-nci_share_usd AS DECIMAL(18,2)) AS amount_usd,
           'Reclassified out of group equity: the minority bore its share' AS narrative,
           entity_code || ' distribution reclassified' AS evidence
    FROM dist WHERE abs(nci_share_usd) > 0.005
    """)

    return {"stg_nci_result": con.execute(
        "SELECT count(*) FROM stg_nci_result").fetchone()[0],
        "nci_result_legs": legs, "nci_dividend_legs": dividend_legs}


def rollforward(con: duckdb.DuckDBPyConnection) -> None:
    """
    The five-account roll-forward, as a report rather than as an assertion.

    Opening plus share of result, less distributions, plus the share of translation, plus
    ownership movements, equals closing. Holding it in five accounts is what makes each line
    testable: a single moving balance can only be compared with itself.
    """
    con.execute(f"""
    CREATE OR REPLACE TABLE rpt_nci_rollforward AS
    WITH movement AS (
        SELECT fiscal_year, related_entity_code AS entity_code,
               round(-sum(amount_usd) FILTER (WHERE group_account = '{NCI_RESULT}'), 2)
                   AS share_of_result_usd,
               round(-sum(amount_usd) FILTER (WHERE group_account = '{NCI_DIVIDEND}'), 2)
                   AS distributions_usd,
               round(-sum(amount_usd) FILTER (WHERE group_account = '{NCI_CTA}'), 2)
                   AS share_of_cta_usd,
               round(-sum(amount_usd) FILTER (WHERE group_account IN ('{NCI_OPENING}',
                                                                      '{NCI_OWNERSHIP}')), 2)
                   AS acquisition_and_ownership_usd
        FROM fact_consol_journal
        WHERE group_account IN ('{NCI_OPENING}', '{NCI_RESULT}', '{NCI_DIVIDEND}',
                                '{NCI_CTA}', '{NCI_OWNERSHIP}')
          AND related_entity_code IS NOT NULL
        GROUP BY ALL
    ),
    ordered AS (
        SELECT *, coalesce(share_of_result_usd, 0) + coalesce(distributions_usd, 0)
                  + coalesce(share_of_cta_usd, 0)
                  + coalesce(acquisition_and_ownership_usd, 0) AS total_movement_usd
        FROM movement
    )
    SELECT entity_code, fiscal_year,
           coalesce(sum(total_movement_usd) OVER w - total_movement_usd, 0) AS opening_usd,
           coalesce(share_of_result_usd, 0) AS share_of_result_usd,
           coalesce(distributions_usd, 0) AS distributions_usd,
           coalesce(share_of_cta_usd, 0) AS share_of_cta_usd,
           coalesce(acquisition_and_ownership_usd, 0) AS acquisition_and_ownership_usd,
           sum(total_movement_usd) OVER w AS closing_usd
    FROM ordered
    WINDOW w AS (PARTITION BY entity_code ORDER BY fiscal_year ROWS UNBOUNDED PRECEDING)
    ORDER BY entity_code, fiscal_year
    """)
