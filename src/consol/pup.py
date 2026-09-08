"""
Unrealised profit in inventory.

When one group company sells to another at a margin and the buyer still holds the goods at
period end, the group has recognised profit on a transaction that never left it. That profit
has to come back out, and the inventory has to come down to what the group actually paid:

    Dr  530300  Cost of sales - unrealised intercompany profit
    Cr  130500  Unrealised intercompany profit in inventory

This is the elimination most often missed in a spreadsheet consolidation, because it needs
something the general ledger does not carry: what proportion of closing inventory was bought
internally, and at what margin. Phase 2 produced that evidence transaction by transaction --
`ref_ic_inventory_holding` carries every intercompany goods flow, the seller's cost, the
transfer price, and how much of each purchase layer is still on hand at each month end.

## Computed from the layers, never read

The unrealised profit is derived here from the surviving FIFO layers and each layer's **own**
margin. The holdings file also carries an `unrealised_profit_usd` column, and this module does
not read it: that column is the acceptance oracle (`P4-PUP-01`), and an engine that read its
own answer would prove nothing.

Using a blended average margin instead of each layer's own is a subtler version of the same
error. A buyer holding two months of purchases at 12% and 9% does not hold them at 10.5%: the
layers survive in FIFO order and the surviving ones are the recent, and usually the
higher-margin, purchases.

## Release

Prior-period unrealised profit reverses as the stock is sold on externally. Because the
adjustment is posted as the **movement** in the cumulative provision, the release happens by
construction: when the holding falls, the cumulative provision falls, and the month's entry is
a credit to cost of sales. Posting the cumulative amount every month instead would reverse
nothing and would restate the whole provision as this month's cost.

Where the holding entity is `NIG-510`, 20% of the adjustment belongs to the non-controlling
interest. That share is allocated by the NCI engine from the consolidated result, which
already includes this entry.
"""

from __future__ import annotations

import duckdb

from .config import LAYER, PUP_COS, PUP_INVENTORY, REFERENCE
from .journals import post_sql


def build(con: duckdb.DuckDBPyConnection, scenario: str = "ACT",
          version: str = "ACTUAL") -> dict[str, int]:
    layer = LAYER["CONSOL_ADJ"]

    # ------------------------------------------------------------------ the calculation
    # The transaction file is the AUTHORITY for this calculation: every intercompany goods
    # movement the group made. `ref_ic_inventory_holding` is derived from it, so a control
    # that iterated the holdings would be asking the answer whether it agrees with itself.
    # `P4-PUP-02` iterates these transactions instead.
    con.execute(f"""
    CREATE OR REPLACE TABLE ref_ic_inventory_transaction AS
    SELECT ic_transaction_id, CAST(period_key AS INTEGER) AS period_key,
           seller_entity, buyer_entity, product_category,
           CAST(transfer_price_usd AS DOUBLE) AS transfer_price_usd,
           CAST(ic_gross_profit_usd AS DOUBLE) AS ic_gross_profit_usd,
           CAST(buyer_inventory_account AS VARCHAR) AS buyer_inventory_account
    FROM read_csv('{(REFERENCE / "ic_inventory_transactions.csv").as_posix()}', header=true)
    """)

    # One row per surviving purchase layer per month: what is still held, at what margin, and
    # therefore how much profit the group has recognised on goods it still owns.
    con.execute("""
    CREATE OR REPLACE TABLE stg_pup_layer AS
    SELECT h.holding_period AS period_key,
           CAST(h.holding_period / 100 AS INTEGER) AS fiscal_year,
           h.transaction_period, h.months_held,
           h.seller_entity, h.buyer_entity, h.inventory_category,
           h.buyer_inventory_account,
           h.transfer_price_usd, h.seller_cost_usd, h.ic_gross_profit_usd,
           -- each layer's OWN margin, not a blended one: the surviving layers are the
           -- recent purchases and they do not carry the average margin of all purchases
           CASE WHEN h.transfer_price_usd <> 0
                THEN h.ic_gross_profit_usd / h.transfer_price_usd ELSE 0 END AS layer_margin,
           h.value_remaining_usd,
           round(h.value_remaining_usd
                 * CASE WHEN h.transfer_price_usd <> 0
                        THEN h.ic_gross_profit_usd / h.transfer_price_usd ELSE 0 END, 2)
               AS unrealised_profit_computed_usd
    FROM ref_ic_inventory_holding h
    """)

    # The provision the group should carry at each month end, and the movement in it. The
    # movement is what gets posted: that is what makes the release automatic.
    con.execute("""
    CREATE OR REPLACE TABLE rpt_pup_provision AS
    WITH held AS (
        SELECT period_key, fiscal_year, seller_entity, buyer_entity,
               buyer_inventory_account,
               round(sum(value_remaining_usd), 2) AS inventory_held_usd,
               round(sum(unrealised_profit_computed_usd), 2) AS provision_usd
        FROM stg_pup_layer GROUP BY ALL
    ),
    spine AS (
        SELECT DISTINCT seller_entity, buyer_entity, buyer_inventory_account FROM held
    ),
    dense AS (
        SELECT s.seller_entity, s.buyer_entity, s.buyer_inventory_account,
               d.period_key, d.fiscal_year,
               coalesce(h.inventory_held_usd, 0) AS inventory_held_usd,
               coalesce(h.provision_usd, 0) AS provision_usd
        FROM spine s
        CROSS JOIN (SELECT DISTINCT period_key, fiscal_year FROM dim_date
                    WHERE accounting_period <= 12) d
        LEFT JOIN held h
               ON h.seller_entity = s.seller_entity AND h.buyer_entity = s.buyer_entity
              AND h.buyer_inventory_account = s.buyer_inventory_account
              AND h.period_key = d.period_key
    )
    SELECT *,
           round(provision_usd - coalesce(lag(provision_usd) OVER w, 0), 2) AS movement_usd
    FROM dense
    WINDOW w AS (PARTITION BY seller_entity, buyer_entity, buyer_inventory_account
                 ORDER BY period_key)
    ORDER BY period_key, seller_entity, buyer_entity
    """)

    legs = post_sql(con, f"""
    WITH entry AS (
        SELECT *, 'PUP-' || substr(md5(seller_entity || buyer_entity
                                       || buyer_inventory_account
                                       || CAST(period_key AS VARCHAR)), 1, 10) AS jid
        FROM rpt_pup_provision WHERE abs(movement_usd) > 0.005
    )
    SELECT jid AS consol_journal_id, 1 AS line_number, {layer} AS layer_id,
           'PUP' AS process, 'PUP-FIFO' AS rule_id, 'ELIM-CON' AS entity_code,
           buyer_entity AS related_entity_code, seller_entity AS partner_entity_code,
           '{PUP_COS}' AS group_account, period_key, fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(movement_usd AS DECIMAL(18,2)) AS amount_usd,
           CASE WHEN movement_usd >= 0
                THEN 'Unrealised intercompany profit in inventory'
                ELSE 'Release of unrealised profit as the stock was sold on externally' END
               AS narrative,
           seller_entity || ' -> ' || buyer_entity || ' FIFO layers at '
               || CAST(period_key AS VARCHAR) AS evidence
    FROM entry
    UNION ALL BY NAME
    SELECT jid AS consol_journal_id, 2 AS line_number, {layer} AS layer_id,
           'PUP' AS process, 'PUP-FIFO' AS rule_id, 'ELIM-CON' AS entity_code,
           buyer_entity AS related_entity_code, seller_entity AS partner_entity_code,
           '{PUP_INVENTORY}' AS group_account, period_key, fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(-movement_usd AS DECIMAL(18,2)) AS amount_usd,
           'Inventory carried down to what the group paid' AS narrative,
           seller_entity || ' -> ' || buyer_entity || ' provision' AS evidence
    FROM entry
    """)

    return {"stg_pup_layer": con.execute(
        "SELECT count(*) FROM stg_pup_layer").fetchone()[0],
        "rpt_pup_provision": con.execute(
            "SELECT count(*) FROM rpt_pup_provision").fetchone()[0],
        "pup_legs": legs}


def acceptance(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """
    The computed provision against the expectation Phase 2.1 published with the holdings.

    The oracle is read here and nowhere else. If the engine had used it as an input this
    comparison would be a tautology.
    """
    return con.execute("""
        SELECT c.period_key,
               round(c.computed_usd, 2) AS computed_usd,
               round(o.expected_usd, 2) AS expected_usd,
               round(c.computed_usd - o.expected_usd, 2) AS difference_usd
        FROM (SELECT period_key, sum(unrealised_profit_computed_usd) AS computed_usd
              FROM stg_pup_layer GROUP BY 1) c
        JOIN (SELECT holding_period AS period_key,
                     sum(unrealised_profit_usd) AS expected_usd
              FROM ref_ic_inventory_holding GROUP BY 1) o USING (period_key)
        ORDER BY abs(c.computed_usd - o.expected_usd) DESC
    """).fetchall()
