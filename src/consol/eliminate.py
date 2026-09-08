"""
Intercompany elimination, by entity pair.

The group's internal trade is real accounting in each entity's own books and must not survive
into the group's. What is eliminated is not a total: it is a **relationship**. Entity A's
receivable from B is eliminated against B's payable to A, for one period. Eliminating at group
total instead -- netting all intercompany receivables against all intercompany payables --
produces the same consolidated figure whenever everything happens to match, and hides every
case where it does not. That is the whole point of fault fixture F02: one side of one pair
restated by 4.5%, both trial balances still closing, and no group total showing anything.

## The unit of matching is the pair, not the account

The three source charts do not agree on how many accounts an intercompany position takes.
Sable carries no separate group treasury current account and no separate affiliate note --
both are reported inside the ordinary intercompany trade account -- and Kestrel books every
kind of intercompany cost to one account under *Materialaufwand*. Both are documented Phase 3
substitutions, not defects.

Matching account against account therefore reports the same real, fully matched balance as two
large exceptions: the Sable entity's pool position missing its counterpart, and Topco's side of
the same pool missing its counterpart. So a relationship is defined as **two sides**, each an
account set, and matched at the pair:

| Relationship | Holder side | Owing side | Matched on |
|---|---|---|---|
| `IC_BALANCE` | `120500`, `125100`, `175100` | `210500`, `225100`, `235100` | the cumulative balance at closing rates |
| `IC_FLOW` | `490100`, `490200`, `490300`, `490400`, `795100` | `590100`, `590200`, `695100`, `695200`, `695300`, `795200` | the period's movement at average rates |

A balance is matched on its **cumulative** value because that is what a balance is; a flow on
the **period's movement** because that is what a flow is. Using one rule for both is a common
and invisible error: a balance eliminated on its monthly movement leaves the opening position
standing in the consolidated balance sheet forever.

The elimination is still posted **account by account**, in proportion to what each account
actually holds, so the consolidated balance on every intercompany account goes to nil
(CTL-IC-07) and no account is eliminated for more than it carries.

## What is not eliminated, and why

A residual that arises because the two sides are denominated in **different currencies** is a
genuine FX gain or loss and is posted to `740100`, not absorbed into the elimination (FX-P12).
The lender really does carry translation exposure on a EUR 24m loan, and an elimination that
swallowed it would report a group with no currency risk on its own internal funding.

A residual that arises because the two sides recorded the transaction in **different months**
is a cut-off finding. Everything else that does not match is an exception with a name, and a
blocking one stops certification.
"""

from __future__ import annotations

import duckdb

from .config import (IC_BALANCE_HOLDER, IC_BALANCE_OWING, IC_FLOW_HOLDER, IC_FLOW_OWING,
                     LAYER, TOL_IC_RESIDUAL_USD)
from .journals import post_sql

FX_GAIN_LOSS = "740100"

#: How a difference is classified. Naming the kind is the point: a difference nobody has
#: classified is indistinguishable from one nobody has looked at.
EXCEPTION_TYPES = ("MATCHED", "TIMING_DIFFERENCE", "FX_DIFFERENCE", "MISSING_COUNTERPART",
                   "AMOUNT_MISMATCH")


def _side_sql(accounts, side: str, relationship: str) -> str:
    return ", ".join(f"('{a}', '{side}', '{relationship}')" for a in accounts)


def build(con: duckdb.DuckDBPyConnection, scenario: str = "ACT",
          version: str = "ACTUAL") -> dict[str, int]:
    """Match every intercompany relationship by pair and eliminate what matches."""

    con.execute(f"""
    CREATE OR REPLACE TABLE ref_ic_side AS
    SELECT * FROM (VALUES {_side_sql(IC_BALANCE_HOLDER, 'HOLDER', 'IC_BALANCE')},
                          {_side_sql(IC_BALANCE_OWING, 'OWING', 'IC_BALANCE')},
                          {_side_sql(IC_FLOW_HOLDER, 'HOLDER', 'IC_FLOW')},
                          {_side_sql(IC_FLOW_OWING, 'OWING', 'IC_FLOW')})
        AS t(group_account, side, relationship)
    """)

    # ---------------------------------------------------------------- positions
    con.execute("""
    CREATE OR REPLACE TABLE stg_ic_position AS
    WITH ic AS (
        SELECT u.entity_code, u.partner_entity_code, u.group_account, u.period_key,
               u.fiscal_year, u.currency_code,
               sum(u.amount_usd)   AS flow_usd,
               sum(u.amount_local) AS flow_local
        FROM fact_layer1_usd u
        JOIN dim_account a USING (group_account)
        WHERE a.is_intercompany AND u.partner_entity_code IS NOT NULL
        GROUP BY ALL
    )
    SELECT *,
           sum(flow_usd) OVER w AS balance_usd,
           sum(flow_local) OVER w AS balance_local
    FROM ic
    WINDOW w AS (PARTITION BY entity_code, partner_entity_code, group_account
                 ORDER BY period_key ROWS UNBOUNDED PRECEDING)
    """)

    # ---------------------------------------------------------------- matching
    con.execute("""
    CREATE OR REPLACE TABLE stg_ic_match AS
    WITH sided AS (
        SELECT sd.relationship, sd.side, p.entity_code, p.partner_entity_code,
               p.period_key, p.fiscal_year, p.currency_code, p.group_account,
               CASE WHEN sd.relationship = 'IC_BALANCE' THEN p.balance_usd
                    ELSE p.flow_usd END AS position_usd
        FROM stg_ic_position p
        JOIN ref_ic_side sd USING (group_account)
    ),
    holder AS (
        SELECT relationship, entity_code AS holder_entity,
               partner_entity_code AS owing_entity, period_key, fiscal_year,
               any_value(currency_code) AS holder_currency, sum(position_usd) AS holder_usd
        FROM sided WHERE side = 'HOLDER' GROUP BY ALL
    ),
    owing AS (
        SELECT relationship, partner_entity_code AS holder_entity,
               entity_code AS owing_entity, period_key, fiscal_year,
               any_value(currency_code) AS owing_currency, sum(position_usd) AS owing_usd
        FROM sided WHERE side = 'OWING' GROUP BY ALL
    ),
    paired AS (
        SELECT coalesce(h.relationship, o.relationship)   AS relationship,
               CASE WHEN coalesce(h.relationship, o.relationship) = 'IC_BALANCE'
                    THEN 'BS' ELSE 'IS' END               AS statement,
               coalesce(h.holder_entity, o.holder_entity) AS holder_entity,
               coalesce(h.owing_entity, o.owing_entity)   AS owing_entity,
               coalesce(h.period_key, o.period_key)       AS period_key,
               coalesce(h.fiscal_year, o.fiscal_year)     AS fiscal_year,
               h.holder_currency, o.owing_currency, h.holder_usd, o.owing_usd
        FROM holder h
        FULL OUTER JOIN owing o
          ON o.relationship = h.relationship AND o.holder_entity = h.holder_entity
         AND o.owing_entity = h.owing_entity AND o.period_key = h.period_key
    )
    SELECT relationship, statement, holder_entity, owing_entity, period_key, fiscal_year,
           holder_currency, owing_currency,
           round(coalesce(holder_usd, 0), 2) AS holder_usd,
           round(coalesce(owing_usd, 0), 2)  AS owing_usd,
           round(coalesce(holder_usd, 0) + coalesce(owing_usd, 0), 2) AS residual_usd,
           -- the eliminable amount is the matched part: whichever side is smaller in
           -- absolute terms. Eliminating the larger would create a balance that never
           -- existed on the other side.
           round(CASE WHEN abs(coalesce(holder_usd, 0)) <= abs(coalesce(owing_usd, 0))
                      THEN coalesce(holder_usd, 0) ELSE -coalesce(owing_usd, 0) END, 2)
               AS matched_usd
    FROM paired
    WHERE abs(coalesce(holder_usd, 0)) > 0.005 OR abs(coalesce(owing_usd, 0)) > 0.005
    """)

    # ---------------------------------------------------------------- classification
    con.execute(f"""
    CREATE OR REPLACE TABLE rpt_ic_exception AS
    SELECT m.*,
           CASE
               WHEN abs(m.residual_usd) <= {TOL_IC_RESIDUAL_USD}   THEN 'MATCHED'
               WHEN abs(m.holder_usd) < 0.005
                 OR abs(m.owing_usd) < 0.005                        THEN 'MISSING_COUNTERPART'
               WHEN m.holder_currency IS DISTINCT FROM m.owing_currency
                    AND abs(m.residual_usd)
                        <= 0.05 * greatest(abs(m.holder_usd), abs(m.owing_usd))
                                                                    THEN 'FX_DIFFERENCE'
               WHEN EXISTS (SELECT 1 FROM stg_ic_match n
                            WHERE n.relationship = m.relationship
                              AND n.holder_entity = m.holder_entity
                              AND n.owing_entity = m.owing_entity
                              AND n.period_key > m.period_key
                              AND n.period_key <= m.period_key + 2
                              AND abs(n.residual_usd + m.residual_usd)
                                  <= {TOL_IC_RESIDUAL_USD})         THEN 'TIMING_DIFFERENCE'
               ELSE 'AMOUNT_MISMATCH'
           END AS exception_type,
           CASE WHEN abs(m.residual_usd) <= {TOL_IC_RESIDUAL_USD} THEN 'PASS'
                WHEN m.holder_currency IS DISTINCT FROM m.owing_currency THEN 'INFORM'
                ELSE 'BLOCKING' END AS severity
    FROM stg_ic_match m
    """)

    # ---------------------------------------------------------------- the entries
    # A balance relationship is matched on the CUMULATIVE position, so the amount that has to
    # be eliminated is cumulative too -- but a journal is a movement. Posting the cumulative
    # elimination in every month would eliminate the same balance thirty-six times over.
    #
    # So the engine computes the cumulative elimination each month and posts its FIRST
    # DIFFERENCE: the entry for a month is what changed in what has to be eliminated. The
    # cumulative effect is then exactly right in every period, which is what the consolidated
    # balance sheet needs, and each month's entry is a meaningful movement rather than a
    # restatement. A flow relationship needs none of this: the period's movement is already
    # what is eliminated.
    con.execute("""
    CREATE OR REPLACE TABLE stg_ic_elim_leg AS
    WITH entry AS (
        SELECT * FROM rpt_ic_exception WHERE abs(matched_usd) > 0.005
    ),
    detail AS (
        SELECT e.relationship, e.statement, e.period_key, e.fiscal_year,
               e.holder_entity, e.owing_entity, 'HOLDER' AS side,
               e.holder_entity AS related_entity_code, e.owing_entity AS partner_entity_code,
               p.group_account,
               CASE WHEN e.relationship = 'IC_BALANCE' THEN p.balance_usd
                    ELSE p.flow_usd END AS account_usd,
               e.matched_usd, e.holder_usd AS side_total_usd
        FROM entry e
        JOIN stg_ic_position p
          ON p.entity_code = e.holder_entity AND p.partner_entity_code = e.owing_entity
         AND p.period_key = e.period_key
        JOIN ref_ic_side sd ON sd.group_account = p.group_account AND sd.side = 'HOLDER'
                           AND sd.relationship = e.relationship
        WHERE abs(e.holder_usd) > 0.005
        UNION ALL BY NAME
        SELECT e.relationship, e.statement, e.period_key, e.fiscal_year,
               e.holder_entity, e.owing_entity, 'OWING' AS side,
               e.owing_entity AS related_entity_code, e.holder_entity AS partner_entity_code,
               p.group_account,
               CASE WHEN e.relationship = 'IC_BALANCE' THEN p.balance_usd
                    ELSE p.flow_usd END AS account_usd,
               -e.matched_usd AS matched_usd, e.owing_usd AS side_total_usd
        FROM entry e
        JOIN stg_ic_position p
          ON p.entity_code = e.owing_entity AND p.partner_entity_code = e.holder_entity
         AND p.period_key = e.period_key
        JOIN ref_ic_side sd ON sd.group_account = p.group_account AND sd.side = 'OWING'
                           AND sd.relationship = e.relationship
        WHERE abs(e.owing_usd) > 0.005
    ),
    target AS (
        -- the cumulative elimination this leg should carry at the end of each month
        SELECT *, round(-account_usd * matched_usd / nullif(side_total_usd, 0), 2)
                      AS cumulative_elim_usd
        FROM detail
    )
    SELECT *,
           CASE WHEN relationship = 'IC_BALANCE'
                THEN round(cumulative_elim_usd
                           - coalesce(lag(cumulative_elim_usd) OVER w, 0), 2)
                ELSE cumulative_elim_usd END AS amount_usd
    FROM target
    WINDOW w AS (PARTITION BY relationship, holder_entity, owing_entity, side, group_account
                 ORDER BY period_key)
    """)

    elim = LAYER["IC_ELIM"]
    legs = post_sql(con, f"""
    SELECT 'ICE-' || substr(md5(relationship || holder_entity || owing_entity
                                || CAST(period_key AS VARCHAR)), 1, 10) AS consol_journal_id,
           CAST(row_number() OVER (PARTITION BY relationship, holder_entity, owing_entity,
                                                period_key
                                   ORDER BY side, group_account) AS INTEGER) AS line_number,
           {elim} AS layer_id, 'IC_ELIM' AS process, relationship AS rule_id,
           'ELIM-IC' AS entity_code, related_entity_code,
           partner_entity_code, group_account,
           period_key, fiscal_year, '{scenario}' AS scenario_code, '{version}' AS version_code,
           'USD' AS currency_code, CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(amount_usd AS DECIMAL(18,2)) AS amount_usd,
           'Eliminate ' || relationship || ' ' || related_entity_code || ' <-> '
               || partner_entity_code AS narrative,
           related_entity_code || '/' || group_account || ' @ '
               || CAST(period_key AS VARCHAR) AS evidence
    FROM stg_ic_elim_leg
    WHERE abs(amount_usd) > 0.005
    """)

    balance_entries(con, "IC_ELIM")

    # The unmatched remainder of a cross-currency relationship is a real translation gain or
    # loss on an internal balance. It is posted, not absorbed.
    fx_legs = post_sql(con, f"""
    WITH entry AS (
        SELECT *, 'ICX-' || substr(md5(relationship || holder_entity || owing_entity
                                       || CAST(period_key AS VARCHAR)), 1, 10) AS jid
        FROM rpt_ic_exception
        WHERE exception_type = 'FX_DIFFERENCE' AND abs(residual_usd) > 0.005
    )
    SELECT jid AS consol_journal_id, 1 AS line_number, {elim} AS layer_id,
           'IC_FX' AS process, relationship AS rule_id,
           'ELIM-IC' AS entity_code, holder_entity AS related_entity_code,
           owing_entity AS partner_entity_code, '{FX_GAIN_LOSS}' AS group_account,
           period_key, fiscal_year, '{scenario}' AS scenario_code, '{version}' AS version_code,
           'USD' AS currency_code, CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(residual_usd AS DECIMAL(18,2)) AS amount_usd,
           'Translation difference on a cross-currency intercompany balance, '
               || coalesce(holder_currency, '?') || '/' || coalesce(owing_currency, '?')
               AS narrative,
           relationship || ' ' || holder_entity || '<->' || owing_entity AS evidence
    FROM entry
    UNION ALL BY NAME
    SELECT jid AS consol_journal_id, 2 AS line_number, {elim} AS layer_id,
           'IC_FX' AS process, relationship AS rule_id,
           'ELIM-IC' AS entity_code, holder_entity AS related_entity_code,
           owing_entity AS partner_entity_code, '120500' AS group_account,
           period_key, fiscal_year, '{scenario}' AS scenario_code, '{version}' AS version_code,
           'USD' AS currency_code, CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(-residual_usd AS DECIMAL(18,2)) AS amount_usd,
           'Translation difference carried to the intercompany balance it arose on'
               AS narrative,
           relationship || ' ' || holder_entity || '<->' || owing_entity AS evidence
    FROM entry
    """)

    return {
        "stg_ic_position": con.execute(
            "SELECT count(*) FROM stg_ic_position").fetchone()[0],
        "stg_ic_match": con.execute("SELECT count(*) FROM stg_ic_match").fetchone()[0],
        "ic_elimination_legs": legs,
        "ic_fx_legs": fx_legs,
    }


def balance_entries(con: duckdb.DuckDBPyConnection, process: str) -> None:
    """
    Carry a multi-leg entry's rounding difference onto its largest leg.

    Allocating one matched amount across several accounts rounds each leg, so the two sides
    of an entry can differ by a cent or two. Left alone those cents accumulate into the
    consolidated balance sheet as a residual nobody can name -- which is exactly the kind of
    unattributable plug this phase exists to make impossible. Carrying the difference onto
    the largest leg is what a multi-leg journal does everywhere else in the platform.
    """
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE _drift AS
    SELECT consol_journal_id, round(sum(amount_usd), 2) AS drift
    FROM fact_consol_journal WHERE process = '{process}'
    GROUP BY 1 HAVING abs(sum(amount_usd)) > 0.001
    """)
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE _biggest AS
    SELECT consol_journal_id, line_number FROM (
        SELECT consol_journal_id, line_number,
               row_number() OVER (PARTITION BY consol_journal_id
                                  ORDER BY abs(amount_usd) DESC, line_number) AS rn
        FROM fact_consol_journal
        WHERE process = '{process}'
          AND consol_journal_id IN (SELECT consol_journal_id FROM _drift)
    ) WHERE rn = 1
    """)
    con.execute("""
    UPDATE fact_consol_journal AS j
    SET amount_usd = j.amount_usd - d.drift
    FROM _drift d, _biggest b
    WHERE j.consol_journal_id = d.consol_journal_id
      AND b.consol_journal_id = d.consol_journal_id
      AND j.line_number = b.line_number
    """)


def residuals(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Pairs whose relationship does not net after elimination, worst first."""
    return con.execute("""
        SELECT relationship, holder_entity, owing_entity, period_key,
               holder_usd, owing_usd, residual_usd, exception_type, severity
        FROM rpt_ic_exception
        WHERE exception_type <> 'MATCHED'
        ORDER BY abs(residual_usd) DESC
    """).fetchall()
