"""
Management adjustments (layer 4), Adjusted EBITDA and Covenant EBITDA.

Layer 4 exists because the alternative is worse. In most hand-built consolidations
"management adjustments" are made inside the consolidated numbers and then backed out for
statutory reporting -- so the statutory number is derived by subtraction from a management
number, and nobody can be certain what was removed. Here the statutory result is the primary
number and the management view is derived from it. That direction is the point: it is far
easier to defend a management view built on an audited base than an audited base
reconstructed out of a management view.

    statutory   = layer 1 + layer 2 + layer 3 + layer 5
    management  = statutory + layer 4

`P4-LAY-03` asserts the statutory basis excludes layer 4 entirely. Leakage is a blocking
defect, not a rounding difference.

## What is in the register, and what is deliberately not

Two adjustments, both **presentation reclassifications that net to nil** within the income
statement: shared services cost presented where it is consumed, and acquired intangible
amortisation presented apart from organic depreciation.

Nothing in layer 4 changes a subtotal, and that is a finding about the approved policy set
rather than an omission. The group's non-recurring items -- restructuring, transaction costs,
the ERP programme, the sponsor fee -- are already **inside operating expenses at layer 1**,
flagged `is_ebitda_addback` on the account (ADR-0013). Adjusted EBITDA is therefore computed
from an account attribute in the statutory data, not from a management journal. Adding them
again at layer 4 would double count them, and inventing new ones to lift Adjusted EBITDA is
exactly what the brief forbids.

## Two adjusted measures, and they are not the same

| | Adjusted EBITDA | Covenant EBITDA |
|---|---|---|
| Basis | approved add-back policy, ADR-0013 | the credit agreement, CA-021 to CA-030 |
| Restructuring, transaction costs, integration, legal, retention | added back | added back |
| Sponsor monitoring fee | added back in full | added back **capped at USD 1.5m a year** (CA-027) |
| Unrealised foreign exchange | not an add-back | **added back** (CA-030) |
| Share-based compensation | not an add-back | not permitted (CA-029) |
| Run-rate synergies | not claimed | not permitted (CA-028) |

Assuming the two are the same is a common and expensive error: the covenant is tested on the
agreement's definition, and a headroom calculated on the management definition can be wrong in
the direction that matters.
"""

from __future__ import annotations

import duckdb

from .config import CONFIG, LAYER
from .journals import post_sql

SPONSOR_FEE_ACCOUNT = "630400"
UNREALISED_FX_ACCOUNTS = ("740100", "740200")


def build(con: duckdb.DuckDBPyConnection, scenario: str = "ACT",
          version: str = "ACTUAL") -> dict[str, int]:
    layer = LAYER["MGMT_ADJ"]

    con.execute(f"""
    CREATE OR REPLACE TABLE ref_management_adjustment AS
    SELECT adjustment_id, category, entity_code, group_account, offset_account,
           CAST(period_from AS INTEGER) AS period_from,
           CAST(period_to AS INTEGER)   AS period_to,
           CAST(amount_usd_m AS DOUBLE) * 1e6 AS amount_usd,
           basis, ebitda_treatment, covenant_treatment, rationale,
           preparer, approver, approval_status,
           reverses_next_period = 'TRUE' AS reverses_next_period
    FROM read_csv('{(CONFIG / "consolidation" / "management_adjustment.csv").as_posix()}',
                  all_varchar=true, header=true)
    """)

    # Only an APPROVED adjustment is posted. An adjustment nobody has approved is a proposal,
    # and a management view built on proposals is not a management view.
    legs = post_sql(con, f"""
    WITH approved AS (
        SELECT * FROM ref_management_adjustment
        WHERE approval_status = 'APPROVED' AND abs(amount_usd) > 0.005
    ),
    months AS (
        SELECT a.*, d.period_key, d.fiscal_year
        FROM approved a
        JOIN (SELECT DISTINCT period_key, fiscal_year FROM dim_date
              WHERE accounting_period <= 12) d
          ON d.period_key BETWEEN a.period_from AND a.period_to
    )
    SELECT 'MGT-' || substr(md5(adjustment_id || CAST(period_key AS VARCHAR)), 1, 10)
               AS consol_journal_id,
           1 AS line_number, {layer} AS layer_id, 'MGMT_ADJ' AS process,
           adjustment_id AS rule_id, 'ELIM-MGT' AS entity_code,
           entity_code AS related_entity_code, CAST(NULL AS VARCHAR) AS partner_entity_code,
           group_account, period_key, fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(amount_usd AS DECIMAL(18,2)) AS amount_usd,
           category || ': ' || basis AS narrative, adjustment_id AS evidence
    FROM months
    UNION ALL BY NAME
    SELECT 'MGT-' || substr(md5(adjustment_id || CAST(period_key AS VARCHAR)), 1, 10)
               AS consol_journal_id,
           2 AS line_number, {layer} AS layer_id, 'MGMT_ADJ' AS process,
           adjustment_id AS rule_id, 'ELIM-MGT' AS entity_code,
           entity_code AS related_entity_code, CAST(NULL AS VARCHAR) AS partner_entity_code,
           offset_account AS group_account, period_key, fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(-amount_usd AS DECIMAL(18,2)) AS amount_usd,
           category || ': the offsetting side' AS narrative, adjustment_id AS evidence
    FROM months
    """)

    return {"ref_management_adjustment": con.execute(
        "SELECT count(*) FROM ref_management_adjustment").fetchone()[0],
        "management_adjustment_legs": legs}


def ebitda_bridges(con: duckdb.DuckDBPyConnection) -> None:
    """Statutory EBITDA to Adjusted EBITDA, and separately to Covenant EBITDA."""
    fx_accounts = ", ".join(f"'{a}'" for a in UNREALISED_FX_ACCOUNTS)
    con.execute(f"""
    CREATE OR REPLACE TABLE ref_covenant_term AS
    SELECT term_id, category, term, value, unit
    FROM read_csv('{(CONFIG / "debt" / "credit_agreement_terms.csv").as_posix()}',
                  all_varchar=true, header=true)
    """)
    cap = con.execute("""
        SELECT CAST(value AS DOUBLE) * 1e6 FROM ref_covenant_term WHERE term_id = 'CA-027'
    """).fetchone()[0]

    con.execute(f"""
    CREATE OR REPLACE TABLE rpt_ebitda_bridge AS
    WITH statutory AS (
        SELECT fiscal_year,
               round(-sum(amount_usd) FILTER (WHERE is_ebitda), 2) AS statutory_ebitda_usd,
               round(sum(amount_usd) FILTER (WHERE is_ebitda_addback), 2)
                   AS approved_addbacks_usd,
               round(sum(amount_usd) FILTER (WHERE group_account = '{SPONSOR_FEE_ACCOUNT}'), 2)
                   AS sponsor_fee_usd,
               round(sum(amount_usd) FILTER (WHERE group_account IN ({fx_accounts})), 2)
                   AS unrealised_fx_usd
        FROM vw_statutory_fact GROUP BY 1
    ),
    mgmt AS (
        SELECT fiscal_year, round(-sum(amount_usd) FILTER (WHERE is_ebitda), 2)
                   AS management_ebitda_effect_usd
        FROM vw_management_fact WHERE layer_id = 4 GROUP BY 1
    )
    SELECT s.fiscal_year,
           s.statutory_ebitda_usd,
           coalesce(m.management_ebitda_effect_usd, 0) AS management_layer4_effect_usd,
           s.approved_addbacks_usd,
           -- Adjusted EBITDA: the approved add-back policy, applied to the statutory result
           round(s.statutory_ebitda_usd + s.approved_addbacks_usd
                 + coalesce(m.management_ebitda_effect_usd, 0), 2) AS adjusted_ebitda_usd,
           -- Covenant EBITDA: the agreement's own definition. The sponsor fee is capped and
           -- unrealised foreign exchange is permitted, so the two measures are not equal by
           -- construction and are not assumed to be.
           round(least(s.sponsor_fee_usd, {cap}) - s.sponsor_fee_usd, 2)
               AS sponsor_fee_cap_effect_usd,
           s.unrealised_fx_usd AS covenant_fx_addback_usd,
           round(s.statutory_ebitda_usd + s.approved_addbacks_usd
                 + least(s.sponsor_fee_usd, {cap}) - s.sponsor_fee_usd
                 + s.unrealised_fx_usd, 2) AS covenant_ebitda_usd
    FROM statutory s LEFT JOIN mgmt m USING (fiscal_year)
    ORDER BY s.fiscal_year
    """)
