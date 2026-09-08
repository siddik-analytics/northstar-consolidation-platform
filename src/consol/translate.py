"""
FX translation and the cumulative translation adjustment.

The group applies the **current rate method** to every foreign operation (ADR-0005,
`docs/fx-cta-policy.md`). Assets and liabilities translate at closing rates, income and
expense at the average rate of the month they were earned in, and contributed capital at the
rate it was contributed at. Those three rules cannot all be satisfied by one number, and the
difference between them is the cumulative translation adjustment.

CTA is therefore **computed**: it is what the translated trial balance is short by, and it is
never entered. That distinction is the whole reason this module exists as a separate step with
its own controls. A hand-plugged CTA balances the balance sheet perfectly and is invisible to
every other control in the framework -- the statements tie, the eliminations net, the trial
balance is zero. Only an independent recomputation finds it, which is what
`data/reference/cta_expectation.csv` is for: an expectation derived from rate movements
applied to balances, produced in Phase 2.2 before any engine existed, and read here as an
oracle and never as an input.

## How each row is translated

A layer-1 row is a *movement* for a month, not a balance, so the rule has to be expressed on
movements:

**Which rule applies is read from `dim_account.fx_method`**, not from a list in this module.
The approved group chart already states, per account, whether it translates at the average
rate, the closing rate, a historical rate, or not at all -- so the engine follows the
controlled configuration and a new account cannot be added without someone deciding how it
translates.

| `fx_method` | Rule | Policy |
|---|---|---|
| `AVG` | × the average rate of the posting month | FX-P01 |
| `CLOSE` | Δ(cumulative local × closing rate) | FX-P02 |
| `HIST` | × the rate frozen at the originating event, or the month's average where the balance accrues month by month | FX-P03 |
| `NONE` | not translated here -- the CTA and NCI-CTA accounts are produced by this engine | FX-P08 |

Two journal characters override the account rule:

| Item | Rule | Policy |
|---|---|---|
| Opening balance journal | × the entity's acquisition-date / opening rate | FX-P16 |
| Year-end and statutory close | the year's translated result, not December's rate | FX-P04, FX-P05 |

The balance sheet rule expands to something worth stating, because it is where CTA comes from:

    usd(p) = cum(p)·close(p) − cum(p−1)·close(p−1)
           = movement(p)·close(p)              the period's own activity, at this month's rate
           + cum(p−1)·(close(p) − close(p−1))  the revaluation of what was already there

The second term is pure translation. It is reported separately as
`fx_revaluation_usd` so that CTA can be explained by the balance it arose on rather than only
as a residual.

The close is the one case that needs its own treatment. Translating a December close entry at
December's average rate would leave the income statement accounts non-zero in USD after the
close, and the difference would silently become CTA. The close instead carries **minus the
sum of the year's translated months**, which is what makes `CTL-FX-03` -- sum of monthly
translated P&L equals the movement in the current-year result -- an identity rather than an
approximation.
"""

from __future__ import annotations

import duckdb

from .config import HISTORICAL_EQUITY, RETAINED_EARNINGS

#: Accounts whose USD value is carried forward rather than translated: the opening balances
#: of retained earnings, CTA and NCI. They are established by the opening journal and by the
#: consolidation entries, never retranslated (FX-P04, FX-P07, FX-P17).
CARRIED_FORWARD = RETAINED_EARNINGS + ("330100", "340100")

#: A historical-rate balance that accrues month by month rather than arising in one
#: transaction -- the share-based compensation reserve, and dividends as they are declared --
#: has no single registered rate. Its historical rate IS the rate of the month it arose in,
#: which is the average rate for that month. Translating it at a closing rate instead would
#: revalue an equity item that the policy freezes, and manufacture CTA that does not exist.
ACCRUING_HISTORICAL = ("315100", "320300", "350100")


def build(con: duckdb.DuckDBPyConnection, rate_set: str = "ACTUAL",
          scenario: str = "ACT", version: str = "ACTUAL") -> dict[str, int]:
    """Translate layer 1 into USD and derive the CTA movement per entity and month."""

    carried = ", ".join(f"'{a}'" for a in CARRIED_FORWARD)
    accruing = ", ".join(f"'{a}'" for a in ACCRUING_HISTORICAL)

    # ---------------------------------------------------------------- movements
    # The consolidation grain, with the two journal characters that translate differently
    # kept apart: the conversion journal that establishes an opening balance sheet, and the
    # close that empties the income statement into reserves.
    con.execute(f"""
    CREATE OR REPLACE TABLE stg_entity_movement AS
    SELECT
        f.entity_code, f.bu_code, f.cost_center_code, f.group_account,
        f.partner_entity_code, f.period_key, f.fiscal_year, f.currency_code,
        -- Which journals are the conversion entry and which are the close, read from what
        -- each ERP actually carries. Aurora and Sable name the event; Kestrel is an
        -- SAP-style extract with no event-type column at all -- it carries SAP document
        -- types 40 and 50 and nothing else -- so its conversion journal is identified from
        -- the document header, which is what a real implementation does. P4-FX-13 proves
        -- every consolidated entity has exactly one conversion journal, in its first
        -- period, so the identification is tested rather than assumed.
        CASE
            WHEN f.source_event_type = 'OPENING_BALANCE'                      THEN 'OPENING'
            WHEN f.source_description = 'Opening balance brought forward'      THEN 'OPENING'
            WHEN f.source_event_type = 'YEAR_END_CLOSE'                       THEN 'CLOSE'
            WHEN f.special_period_type = 'STATUTORY_CLOSE'                    THEN 'CLOSE'
            ELSE 'NORMAL'
        END AS movement_type,
        a.statement, a.fx_method, a.account_class, a.is_statistical,
        sum(f.signed_local_amount) AS amount_local,
        count(*) AS line_count
    FROM fact_journal_line f
    JOIN dim_account a USING (group_account)
    WHERE NOT a.is_statistical
    GROUP BY ALL
    """)

    # ---------------------------------------------------------------- rates
    con.execute(f"""
    CREATE OR REPLACE VIEW vw_rate AS
    SELECT currency_code, period_key,
           max(CASE WHEN rate_type = 'AVG'   THEN rate_usd_per_unit END) AS avg_rate,
           max(CASE WHEN rate_type = 'CLOSE' THEN rate_usd_per_unit END) AS close_rate
    FROM ref_fx_rate WHERE rate_set = '{rate_set}'
    GROUP BY ALL
    """)

    # The opening translation base: the rate an entity's opening balance sheet is stated at.
    # For an entity acquired inside the modelled window this is the closing spot on its
    # consolidation effective date (FX-P16); for one already in the group it is the FY2022
    # closing anchor the ledgers open from.
    con.execute("""
    CREATE OR REPLACE VIEW vw_opening_rate AS
    SELECT entity_code, rate_usd_per_unit AS opening_rate
    FROM ref_fx_rate_historical WHERE group_account = 'ACQ_OPENING_BS'
    """)

    con.execute("""
    CREATE OR REPLACE VIEW vw_historical_rate AS
    SELECT entity_code, group_account, rate_usd_per_unit AS historical_rate
    FROM ref_fx_rate_historical WHERE group_account <> 'ACQ_OPENING_BS'
    """)

    # ---------------------------------------------------------------- balance sheet path
    # A balance sheet movement is translated as the change in the translated BALANCE, which
    # is what the current rate method means and what makes the revaluation of the opening
    # position visible as its own component.
    con.execute("""
    CREATE OR REPLACE TABLE stg_bs_translation AS
    WITH bs AS (
        SELECT entity_code, bu_code, cost_center_code, group_account, partner_entity_code,
               period_key, fiscal_year, currency_code, statement, fx_method, account_class,
               sum(amount_local) FILTER (WHERE movement_type = 'OPENING') AS opening_local,
               sum(amount_local) FILTER (WHERE movement_type <> 'OPENING') AS movement_local
        FROM stg_entity_movement
        WHERE fx_method = 'CLOSE'
        GROUP BY ALL
    ),
    entity_start AS (
        -- the first month an entity has a ledger at all. The spine must not start before
        -- it: an entity acquired in April has no March, and a row in March would make the
        -- lag() below pick up March's closing rate as the basis its opening balance sheet
        -- was carried at, revaluing the acquisition from a rate it was never stated at.
        SELECT entity_code, min(period_key) AS first_period
        FROM stg_entity_movement GROUP BY 1
    ),
    dense AS (
        -- every balance needs a row in every month it exists, or a balance that stops
        -- moving would stop being revalued and its CTA would quietly stop accruing
        SELECT b.entity_code, b.bu_code, b.cost_center_code, b.group_account,
               b.partner_entity_code, d.period_key, d.fiscal_year, b.currency_code,
               b.statement, b.fx_method, b.account_class,
               coalesce(m.opening_local, 0) AS opening_local,
               coalesce(m.movement_local, 0) AS movement_local
        FROM (SELECT DISTINCT entity_code, bu_code, cost_center_code, group_account,
                     partner_entity_code, currency_code, statement, fx_method, account_class
              FROM bs) b
        JOIN entity_start st ON st.entity_code = b.entity_code
        CROSS JOIN (SELECT DISTINCT period_key, fiscal_year FROM dim_date
                    WHERE accounting_period <= 12) d
        LEFT JOIN bs m
               ON m.entity_code = b.entity_code AND m.group_account = b.group_account
              AND m.cost_center_code IS NOT DISTINCT FROM b.cost_center_code
              AND m.partner_entity_code IS NOT DISTINCT FROM b.partner_entity_code
              AND m.period_key = d.period_key
        WHERE d.period_key >= st.first_period
    ),
    running AS (
        SELECT *,
               sum(opening_local + movement_local) OVER w AS cum_local,
               sum(opening_local + movement_local) OVER w
                 - movement_local                          AS prior_cum_local
        FROM dense
        WINDOW w AS (PARTITION BY entity_code, group_account, cost_center_code,
                                  partner_entity_code
                     ORDER BY period_key ROWS UNBOUNDED PRECEDING)
    )
    SELECT r.*, rt.close_rate, op.opening_rate,
           -- the rate the prior balance was carried at: the opening rate in the first month
           -- an entity has a balance, otherwise the previous month's closing rate
           coalesce(lag(rt.close_rate) OVER (PARTITION BY r.entity_code, r.group_account,
                                                          r.cost_center_code,
                                                          r.partner_entity_code
                                             ORDER BY r.period_key),
                    op.opening_rate) AS prior_rate
    FROM running r
    JOIN vw_rate rt ON rt.currency_code = r.currency_code AND rt.period_key = r.period_key
    LEFT JOIN vw_opening_rate op ON op.entity_code = r.entity_code
    """)

    # ---------------------------------------------------------------- the close
    # The year's translated result, per account, so that the close reverses in USD exactly
    # what the year recognised in USD (FX-P05, CTL-FX-03).
    con.execute("""
    CREATE OR REPLACE TABLE stg_close_translation AS
    WITH pl_year AS (
        SELECT m.entity_code, m.fiscal_year, m.group_account, m.cost_center_code,
               m.partner_entity_code,
               sum(m.amount_local * r.avg_rate) AS translated_year_usd
        FROM stg_entity_movement m
        JOIN vw_rate r ON r.currency_code = m.currency_code AND r.period_key = m.period_key
        WHERE m.statement = 'IS' AND m.movement_type = 'NORMAL'
        GROUP BY ALL
    ),
    close_rows AS (
        SELECT * FROM stg_entity_movement WHERE movement_type = 'CLOSE'
    )
    SELECT c.entity_code, c.bu_code, c.cost_center_code, c.group_account,
           c.partner_entity_code, c.period_key, c.fiscal_year, c.currency_code,
           c.statement, c.amount_local,
           CASE
               WHEN c.statement = 'IS'
                   -- reverse exactly what the year recognised, at the rates it was
                   -- recognised at, so the income statement is nil in USD after the close
                   THEN -coalesce(p.translated_year_usd, 0)
               ELSE NULL          -- the reserve leg is the balance of the entry, set below
           END AS amount_usd
    FROM close_rows c
    LEFT JOIN pl_year p
           ON p.entity_code = c.entity_code AND p.fiscal_year = c.fiscal_year
          AND p.group_account = c.group_account
          AND p.cost_center_code IS NOT DISTINCT FROM c.cost_center_code
          AND p.partner_entity_code IS NOT DISTINCT FROM c.partner_entity_code
    """)

    # ---------------------------------------------------------------- assemble
    con.execute(f"""
    CREATE OR REPLACE TABLE fact_layer1_usd AS
    -- 1. the opening balance sheet, at the rate it is stated at
    SELECT m.entity_code, m.bu_code, m.cost_center_code, m.group_account,
           m.partner_entity_code, m.period_key, m.fiscal_year, m.currency_code,
           m.statement, 'OPENING' AS translation_basis,
           m.amount_local,
           round(m.amount_local * op.opening_rate, 2) AS amount_usd,
           CAST(0 AS DECIMAL(18,2)) AS fx_revaluation_usd,
           op.opening_rate AS rate_applied
    FROM stg_entity_movement m
    JOIN vw_opening_rate op ON op.entity_code = m.entity_code
    WHERE m.movement_type = 'OPENING'

    UNION ALL BY NAME
    -- 2. everything the chart says translates at the average rate of its own month
    SELECT m.entity_code, m.bu_code, m.cost_center_code, m.group_account,
           m.partner_entity_code, m.period_key, m.fiscal_year, m.currency_code,
           m.statement, 'AVG' AS translation_basis,
           m.amount_local,
           round(m.amount_local * r.avg_rate, 2) AS amount_usd,
           CAST(0 AS DECIMAL(18,2)) AS fx_revaluation_usd,
           r.avg_rate AS rate_applied
    FROM stg_entity_movement m
    JOIN vw_rate r ON r.currency_code = m.currency_code AND r.period_key = m.period_key
    WHERE m.movement_type = 'NORMAL' AND m.fx_method = 'AVG'

    UNION ALL BY NAME
    -- 3. the close, carrying the year's translated result rather than December's rate
    SELECT c.entity_code, c.bu_code, c.cost_center_code, c.group_account,
           c.partner_entity_code, c.period_key, c.fiscal_year, c.currency_code,
           c.statement, 'CLOSE' AS translation_basis,
           c.amount_local,
           round(coalesce(c.amount_usd, -reserve.leg), 2) AS amount_usd,
           CAST(0 AS DECIMAL(18,2)) AS fx_revaluation_usd,
           CAST(NULL AS DOUBLE) AS rate_applied
    FROM stg_close_translation c
    LEFT JOIN (
        SELECT entity_code, fiscal_year, period_key, sum(amount_usd) AS leg
        FROM stg_close_translation WHERE amount_usd IS NOT NULL
        GROUP BY ALL
    ) reserve
      ON reserve.entity_code = c.entity_code AND reserve.period_key = c.period_key
    WHERE c.statement = 'IS' OR c.amount_usd IS NULL

    UNION ALL BY NAME
    -- 4. equity frozen at the rate of its originating transaction. Where the register names
    -- a rate for the account, that rate is frozen forever; where the balance accrues month
    -- by month instead, the rate of its own month is its historical rate.
    SELECT m.entity_code, m.bu_code, m.cost_center_code, m.group_account,
           m.partner_entity_code, m.period_key, m.fiscal_year, m.currency_code,
           m.statement, 'HIST' AS translation_basis,
           m.amount_local,
           round(m.amount_local * coalesce(h.historical_rate, r.avg_rate), 2) AS amount_usd,
           CAST(0 AS DECIMAL(18,2)) AS fx_revaluation_usd,
           coalesce(h.historical_rate, r.avg_rate) AS rate_applied
    FROM stg_entity_movement m
    JOIN vw_rate r ON r.currency_code = m.currency_code AND r.period_key = m.period_key
    LEFT JOIN vw_historical_rate h
      ON h.entity_code = m.entity_code AND h.group_account = m.group_account
    WHERE m.movement_type = 'NORMAL' AND m.fx_method = 'HIST'
      AND m.group_account NOT IN ({carried})

    UNION ALL BY NAME
    -- 5. the closing-rate accounts: the change in the TRANSLATED balance, which is the
    -- current rate method, and which separates the period's own activity from the
    -- revaluation of what was already there
    SELECT b.entity_code, b.bu_code, b.cost_center_code, b.group_account,
           b.partner_entity_code, b.period_key, b.fiscal_year, b.currency_code,
           b.statement, 'CLOSE_RATE' AS translation_basis,
           b.movement_local AS amount_local,
           round(b.movement_local * b.close_rate
                 + b.prior_cum_local * (b.close_rate - b.prior_rate), 2) AS amount_usd,
           round(b.prior_cum_local * (b.close_rate - b.prior_rate), 2) AS fx_revaluation_usd,
           b.close_rate AS rate_applied
    FROM stg_bs_translation b
    WHERE b.fx_method = 'CLOSE'
      AND b.group_account NOT IN ({carried})
      AND (b.movement_local <> 0 OR b.prior_cum_local <> 0)

    UNION ALL BY NAME
    -- 6. carried-forward equity: retained earnings brought forward is never retranslated
    SELECT b.entity_code, b.bu_code, b.cost_center_code, b.group_account,
           b.partner_entity_code, b.period_key, b.fiscal_year, b.currency_code,
           b.statement, 'CARRIED' AS translation_basis,
           b.movement_local AS amount_local,
           CAST(0 AS DECIMAL(18,2)) AS amount_usd,
           CAST(0 AS DECIMAL(18,2)) AS fx_revaluation_usd,
           CAST(NULL AS DOUBLE) AS rate_applied
    FROM stg_bs_translation b
    WHERE b.group_account IN ({carried}) AND b.movement_local <> 0
    """)

    counts = {
        "stg_entity_movement": con.execute(
            "SELECT count(*) FROM stg_entity_movement").fetchone()[0],
        "fact_layer1_usd": con.execute(
            "SELECT count(*) FROM fact_layer1_usd").fetchone()[0],
    }
    return counts


def cta_movement(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """
    The CTA movement, per entity and month, as the residual of the translated trial balance.

    The local trial balance sums to zero because every journal balances. The translated one
    does not, because its rows were translated at three different kinds of rate, and what it
    is short by IS the translation adjustment. Deriving it this way is what makes it a
    computed figure rather than an input -- and what makes an independent recomputation, from
    rate movements on balances, a genuine test rather than a restatement.
    """
    con.execute("""
    CREATE OR REPLACE TABLE stg_cta_movement AS
    WITH residual AS (
        SELECT entity_code, period_key, fiscal_year, currency_code,
               round(-sum(amount_usd), 2) AS cta_movement_usd
        FROM fact_layer1_usd
        GROUP BY ALL
    ),
    -- explain the residual by the balance it arose on, so CTA can be read as a cause and
    -- not only as a number
    by_cause AS (
        SELECT entity_code, period_key,
               round(sum(fx_revaluation_usd) FILTER (WHERE group_account = '110100'), 2)
                   AS cta_on_cash,
               round(sum(fx_revaluation_usd) FILTER (
                   WHERE group_account LIKE '15%' OR group_account LIKE '158%'), 2)
                   AS cta_on_ppe,
               round(sum(fx_revaluation_usd) FILTER (WHERE group_account LIKE '16%'), 2)
                   AS cta_on_intangibles,
               round(sum(fx_revaluation_usd), 2) AS cta_on_all_balances
        FROM fact_layer1_usd GROUP BY ALL
    )
    SELECT r.entity_code, r.period_key, r.fiscal_year, r.currency_code,
           r.cta_movement_usd,
           o.effective_ownership_pct, o.effective_nci_pct,
           round(r.cta_movement_usd * o.effective_ownership_pct, 2) AS cta_group_usd,
           round(r.cta_movement_usd - round(r.cta_movement_usd
                                            * o.effective_ownership_pct, 2), 2) AS cta_nci_usd,
           c.cta_on_cash, c.cta_on_ppe, c.cta_on_intangibles, c.cta_on_all_balances,
           sum(r.cta_movement_usd) OVER (PARTITION BY r.entity_code
                                         ORDER BY r.period_key
                                         ROWS UNBOUNDED PRECEDING) AS cta_cumulative_usd
    FROM residual r
    JOIN dim_ownership_period o
      ON o.entity_code = r.entity_code AND o.period_key = r.period_key
    LEFT JOIN by_cause c ON c.entity_code = r.entity_code AND c.period_key = r.period_key
    ORDER BY r.entity_code, r.period_key
    """)
    return {"stg_cta_movement": con.execute(
        "SELECT count(*) FROM stg_cta_movement").fetchone()[0]}
