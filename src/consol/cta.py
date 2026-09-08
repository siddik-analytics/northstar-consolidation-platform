"""
Posting the cumulative translation adjustment to layer 5.

The derivation is in `translate.py`; this module only writes it down. Keeping the two apart
matters: the derivation is tested against an oracle produced before any engine existed, and
the posting is tested for the structural properties a journal has to have. Merging them would
let a posting bug hide behind a correct derivation.

## Why layer 5 does not balance on its own

Layers 2, 3 and 4 are self-balancing sets of journal entries: debits equal credits within each
layer, every period. Layer 5 is not, and testing it for independent balance would fail every
month. It **is** the balancing entry that makes the translated layer-1 trial balance sum to
zero -- so the property to test is that layers 1 and 5 together sum to zero, which is
`CTL-TB-03`.

## Why it is posted to the real entity

Every other consolidation entry goes to a virtual entity so that an entity's reported figures
still agree with its own trial balance (ADR-0014). CTA is the exception. It is an attribute of
a specific foreign operation, and "what is Halden's cumulative translation adjustment?" is a
question the group has to be able to answer. Posting it to `ELIM-CON` would make it
unattributable.

## The split between the group and the minority

The movement is allocated between `330200` (group) and `340400` (non-controlling interests) in
proportion to ownership for the period. Allocating 100% of a partly owned subsidiary's
translation movement to group equity overstates group equity and understates NCI by the same
amount -- and because both sit inside total equity, the balance sheet still balances and
nothing else catches it (`CTL-CON-11`).
"""

from __future__ import annotations

import duckdb

from .config import CTA_MOVEMENT, LAYER, NCI_CTA
from .journals import post_sql


def build(con: duckdb.DuckDBPyConnection, scenario: str = "ACT",
          version: str = "ACTUAL") -> dict[str, int]:
    layer = LAYER["FX_CTA"]

    legs = post_sql(con, f"""
    WITH entry AS (
        SELECT *, 'CTA-' || substr(md5(entity_code || CAST(period_key AS VARCHAR)), 1, 10)
                      AS jid
        FROM stg_cta_movement WHERE abs(cta_movement_usd) > 0.005
    )
    SELECT jid AS consol_journal_id, 1 AS line_number, {layer} AS layer_id,
           'CTA' AS process, 'FX-P06' AS rule_id,
           entity_code, entity_code AS related_entity_code,
           CAST(NULL AS VARCHAR) AS partner_entity_code,
           '{CTA_MOVEMENT}' AS group_account, period_key, fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(cta_group_usd AS DECIMAL(18,2)) AS amount_usd,
           'Cumulative translation adjustment for the period, group share' AS narrative,
           'derived as the residual of the translated trial balance' AS evidence
    FROM entry WHERE abs(cta_group_usd) > 0.005
    UNION ALL BY NAME
    SELECT jid AS consol_journal_id, 2 AS line_number, {layer} AS layer_id,
           'CTA' AS process, 'FX-P20' AS rule_id,
           entity_code, entity_code AS related_entity_code,
           CAST(NULL AS VARCHAR) AS partner_entity_code,
           '{NCI_CTA}' AS group_account, period_key, fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(cta_nci_usd AS DECIMAL(18,2)) AS amount_usd,
           'Non-controlling interests - share of the translation adjustment' AS narrative,
           'ownership share of the same derived movement' AS evidence
    FROM entry WHERE abs(cta_nci_usd) > 0.005
    """)

    # The roll-forward, as a report. Closing is derived from opening plus movement rather
    # than held as a balance, so a discontinuity is visible instead of being absorbed.
    con.execute(f"""
    CREATE OR REPLACE TABLE rpt_cta_rollforward AS
    SELECT entity_code, fiscal_year,
           round(sum(cta_movement_usd) OVER w - sum(cta_movement_usd) OVER y, 2)
               AS opening_usd,
           round(sum(cta_movement_usd) OVER y, 2) AS movement_usd,
           0.0 AS recycled_usd,
           round(sum(cta_movement_usd) OVER w, 2) AS closing_usd,
           round(sum(cta_group_usd) OVER y, 2) AS movement_group_usd,
           round(sum(cta_nci_usd) OVER y, 2) AS movement_nci_usd
    FROM (SELECT entity_code, fiscal_year,
                 sum(cta_movement_usd) AS cta_movement_usd,
                 sum(cta_group_usd) AS cta_group_usd,
                 sum(cta_nci_usd) AS cta_nci_usd
          FROM stg_cta_movement GROUP BY ALL)
    WINDOW w AS (PARTITION BY entity_code ORDER BY fiscal_year ROWS UNBOUNDED PRECEDING),
           y AS (PARTITION BY entity_code, fiscal_year)
    ORDER BY entity_code, fiscal_year
    """)

    return {"cta_legs": legs,
            "rpt_cta_rollforward": con.execute(
                "SELECT count(*) FROM rpt_cta_rollforward").fetchone()[0]}
