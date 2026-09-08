"""
Investment elimination, purchase accounting and acquired intangible amortisation.

Three things happen here, and they are one entry seen from three angles.

**The investment eliminates against what it bought.** Layer 1 carries the parent's investment
at cost *and* the subsidiary's equity, so consolidating both would count the same net assets
twice. The elimination removes the double count -- relationship by relationship, never at group
total. That distinction is the whole point: eliminating the sum of all investments against the
sum of all subsidiary equity gives the same consolidated figure whenever everything matches and
tells you nothing when it does not, and it cannot express a second-tier holding at all. Vector
Systems is held by Vector Engineered Systems, not by Topco; Parts UK is held by Aftermarket and
only 80% owned.

**Goodwill is the residual, and it is computed.**

    goodwill = consideration + non-controlling interest at acquisition
             - fair value of identifiable net assets

Nothing here plugs. If the schedule's inputs and the acquired entity's own equity do not
produce the goodwill the approved anchor carries, that is a finding and not something to
absorb: `P4-PPA-01` compares the computed bridge with the anchor and reports the difference.

**The acquired intangibles amortise on their own schedule**, per acquisition and per tranche,
from the month the acquisition completes. Amortisation that starts at the beginning of the
year an acquisition happened in overstates the charge by the months before it -- a small,
plausible and entirely wrong number.

## The opening consolidated position

Nine of the eleven acquisitions completed before the modelled window. Their goodwill, acquired
intangibles and deferred tax are **opening balances**, because the acquired entities' balance
sheets at their own acquisition dates predate the generated ledgers -- there is nothing to
recompute them from. They are taken from the approved opening consolidated balance sheet and
posted as one dated entry, with the same goodwill identity applied to the aggregate, so the
entry balances for the same reason every other one does rather than by construction.

The group's accumulated translation adjustment at the opening date is a separate entry: it
reclassifies USD 3.5m out of the opening retained earnings the entity ledgers brought in and
into the CTA opening account where the policy holds it. It moves nothing outside equity.
"""

from __future__ import annotations

import duckdb

from .config import (CONFIG, CTA_OPENING, GOODWILL, INVESTMENT, LAYER, NCI_OPENING,
                     PPA_ACCUM_AMORT, PPA_AMORT_EXPENSE, PPA_DTL)
from .journals import post_sql

RETAINED_EARNINGS_OPENING = "320100"
OPENING_CTA_USD_M = -3.5          # the approved opening consolidated balance sheet


def _load(con: duckdb.DuckDBPyConnection) -> None:
    """The acquisition register and its intangible tranches, as controlled configuration."""
    con.execute(f"""
    CREATE OR REPLACE TABLE ref_acquisition AS
    SELECT acquisition_id, investment_id, parent_entity, subsidiary_entity,
           CAST(effective_period AS INTEGER) AS effective_period, basis,
           CAST(consideration_usd_m AS DOUBLE) * 1e6        AS consideration_usd,
           CAST(ownership_pct AS DOUBLE)                    AS ownership_pct,
           CAST(nci_at_acquisition_usd_m AS DOUBLE) * 1e6   AS nci_at_acquisition_usd,
           CAST(book_net_assets_usd_m AS DOUBLE) * 1e6      AS book_net_assets_usd,
           CAST(fv_uplift_ppe_usd_m AS DOUBLE) * 1e6        AS fv_uplift_usd,
           CAST(deferred_tax_rate AS DOUBLE)                AS deferred_tax_rate,
           currency_code, notes
    FROM read_csv('{(CONFIG / "consolidation" / "acquisition.csv").as_posix()}',
                  all_varchar=true, header=true)
    """)
    con.execute(f"""
    CREATE OR REPLACE TABLE ref_ppa_intangible AS
    SELECT ppa_id, acquisition_id, intangible_class, group_account,
           CAST(gross_usd_m AS DOUBLE) * 1e6 AS gross_usd,
           CAST(useful_life_years AS DOUBLE) AS useful_life_years,
           CAST(amortisation_start_period AS INTEGER) AS amortisation_start_period,
           CAST(accumulated_amortisation_at_open_usd_m AS DOUBLE) * 1e6 AS accum_at_open_usd,
           notes
    FROM read_csv('{(CONFIG / "consolidation" / "ppa_intangible.csv").as_posix()}',
                  all_varchar=true, header=true)
    """)

    # The goodwill bridge, computed. Never a plug, and never read from an anchor.
    con.execute("""
    CREATE OR REPLACE TABLE rpt_goodwill_bridge AS
    WITH intangibles AS (
        SELECT acquisition_id, sum(gross_usd) AS intangibles_usd
        FROM ref_ppa_intangible GROUP BY 1
    )
    SELECT a.acquisition_id, a.parent_entity, a.subsidiary_entity, a.effective_period,
           a.basis, a.consideration_usd, a.nci_at_acquisition_usd, a.book_net_assets_usd,
           a.fv_uplift_usd, coalesce(i.intangibles_usd, 0) AS intangibles_usd,
           round(coalesce(i.intangibles_usd, 0) * a.deferred_tax_rate, 2) AS deferred_tax_usd,
           round(a.book_net_assets_usd + a.fv_uplift_usd + coalesce(i.intangibles_usd, 0)
                 - coalesce(i.intangibles_usd, 0) * a.deferred_tax_rate, 2)
               AS fair_value_net_assets_usd,
           round(a.consideration_usd + a.nci_at_acquisition_usd
                 - (a.book_net_assets_usd + a.fv_uplift_usd + coalesce(i.intangibles_usd, 0)
                    - coalesce(i.intangibles_usd, 0) * a.deferred_tax_rate), 2)
               AS goodwill_usd
    FROM ref_acquisition a
    LEFT JOIN intangibles i USING (acquisition_id)
    ORDER BY a.effective_period, a.acquisition_id
    """)


def build(con: duckdb.DuckDBPyConnection, scenario: str = "ACT",
          version: str = "ACTUAL") -> dict[str, int]:
    _load(con)
    layer = LAYER["CONSOL_ADJ"]
    counts: dict[str, int] = {}

    # ------------------------------------------------------------------ the entry
    # One entry per acquisition, dated at the acquisition. It is posted once because both
    # what it eliminates and what it creates are BALANCES that persist: the parent holds the
    # investment every month and the subsidiary carries the equity every month, so a monthly
    # re-elimination would remove the same position over and over.
    #
    # The acquired equity is debited in two parts because layer 1 carries it in two: the
    # contributed capital the entity actually reports, and the reserves it opened with, which
    # are pre-acquisition from the group's point of view.
    counts["investment_elimination_legs"] = post_sql(con, f"""
    WITH capital AS (
        -- the contributed capital the acquired entity actually reports, up to and including
        -- the month the acquisition completes. What the acquisition schedule says the net
        -- assets were worth, less this, is the reserve the subsidiary brought with it.
        SELECT b.acquisition_id, b.subsidiary_entity,
               round(-sum(u.amount_usd), 2) AS contributed_capital_usd
        FROM rpt_goodwill_bridge b
        JOIN fact_layer1_usd u
          ON u.entity_code = b.subsidiary_entity AND u.group_account IN ('310100', '310200')
         AND u.period_key <= b.effective_period
        GROUP BY ALL
    ),
    entry AS (
        SELECT b.*, c.contributed_capital_usd,
               round(b.book_net_assets_usd - c.contributed_capital_usd, 2)
                   AS pre_acquisition_reserves_usd,
               'INV-' || substr(md5(b.acquisition_id), 1, 10) AS jid,
               CAST(b.effective_period / 100 AS INTEGER) AS fy
        FROM rpt_goodwill_bridge b JOIN capital c USING (acquisition_id)
    )
    SELECT jid AS consol_journal_id, 1 AS line_number, {layer} AS layer_id,
           'INVESTMENT' AS process, acquisition_id AS rule_id,
           'ELIM-CON' AS entity_code, subsidiary_entity AS related_entity_code,
           parent_entity AS partner_entity_code, '310200' AS group_account,
           effective_period AS period_key, fy AS fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(contributed_capital_usd AS DECIMAL(18,2)) AS amount_usd,
           'Eliminate the acquired contributed capital' AS narrative,
           acquisition_id || ' contributed capital at ' || CAST(effective_period AS VARCHAR)
               AS evidence
    FROM entry
    UNION ALL BY NAME
    SELECT jid AS consol_journal_id, 2 AS line_number, {layer} AS layer_id,
           'INVESTMENT' AS process, acquisition_id AS rule_id,
           'ELIM-CON' AS entity_code, subsidiary_entity AS related_entity_code,
           parent_entity AS partner_entity_code, '{RETAINED_EARNINGS_OPENING}' AS group_account,
           effective_period AS period_key, fy AS fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(pre_acquisition_reserves_usd AS DECIMAL(18,2)) AS amount_usd,
           'Eliminate the reserves acquired with the subsidiary' AS narrative,
           acquisition_id || ' pre-acquisition reserves' AS evidence
    FROM entry WHERE abs(pre_acquisition_reserves_usd) > 0.005
    UNION ALL BY NAME
    SELECT jid AS consol_journal_id, 3 AS line_number, {layer} AS layer_id,
           'INVESTMENT' AS process, acquisition_id AS rule_id,
           'ELIM-CON' AS entity_code, subsidiary_entity AS related_entity_code,
           parent_entity AS partner_entity_code, '{GOODWILL}' AS group_account,
           effective_period AS period_key, fy AS fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(goodwill_usd AS DECIMAL(18,2)) AS amount_usd,
           'Goodwill: consideration plus non-controlling interest, less the fair value of '
               || 'identifiable net assets' AS narrative,
           acquisition_id || ' goodwill, computed' AS evidence
    FROM entry WHERE abs(goodwill_usd) > 0.005
    UNION ALL BY NAME
    SELECT e.jid AS consol_journal_id, 10 + CAST(row_number() OVER
               (PARTITION BY e.jid ORDER BY p.ppa_id) AS INTEGER) AS line_number,
           {layer} AS layer_id, 'INVESTMENT' AS process, e.acquisition_id AS rule_id,
           'ELIM-CON' AS entity_code, e.subsidiary_entity AS related_entity_code,
           e.parent_entity AS partner_entity_code, p.group_account,
           e.effective_period AS period_key, e.fy AS fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(p.gross_usd AS DECIMAL(18,2)) AS amount_usd,
           'Recognise ' || p.intangible_class || ' at fair value on acquisition' AS narrative,
           p.ppa_id AS evidence
    FROM entry e JOIN ref_ppa_intangible p USING (acquisition_id)
    UNION ALL BY NAME
    SELECT jid AS consol_journal_id, 30 AS line_number, {layer} AS layer_id,
           'INVESTMENT' AS process, acquisition_id AS rule_id,
           'ELIM-CON' AS entity_code, subsidiary_entity AS related_entity_code,
           parent_entity AS partner_entity_code, '{PPA_DTL}' AS group_account,
           effective_period AS period_key, fy AS fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(-deferred_tax_usd AS DECIMAL(18,2)) AS amount_usd,
           'Deferred tax on the fair value recognised' AS narrative,
           acquisition_id || ' deferred tax' AS evidence
    FROM entry WHERE abs(deferred_tax_usd) > 0.005
    UNION ALL BY NAME
    SELECT jid AS consol_journal_id, 31 AS line_number, {layer} AS layer_id,
           'INVESTMENT' AS process, acquisition_id AS rule_id,
           'ELIM-CON' AS entity_code, subsidiary_entity AS related_entity_code,
           parent_entity AS partner_entity_code, '{NCI_OPENING}' AS group_account,
           effective_period AS period_key, fy AS fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(-nci_at_acquisition_usd AS DECIMAL(18,2)) AS amount_usd,
           'Non-controlling interest recognised at acquisition' AS narrative,
           acquisition_id || ' NCI at acquisition' AS evidence
    FROM entry WHERE abs(nci_at_acquisition_usd) > 0.005
    UNION ALL BY NAME
    SELECT jid AS consol_journal_id, 40 AS line_number, {layer} AS layer_id,
           'INVESTMENT' AS process, acquisition_id AS rule_id,
           'ELIM-CON' AS entity_code, subsidiary_entity AS related_entity_code,
           parent_entity AS partner_entity_code, '{INVESTMENT}' AS group_account,
           effective_period AS period_key, fy AS fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(-consideration_usd AS DECIMAL(18,2)) AS amount_usd,
           'Eliminate the parent''s investment at cost' AS narrative,
           acquisition_id || ' investment eliminated' AS evidence
    FROM entry
    """)

    # ------------------------------------------------------------------ opening CTA
    # The group's accumulated translation adjustment at the opening date. The entity ledgers
    # brought their opening position in through a retained-earnings plug, so the accumulated
    # translation sits there; the policy holds it in its own account and the roll-forward
    # needs it there to open from. A reclassification within equity, nothing more.
    counts["opening_cta_legs"] = post_sql(con, f"""
    SELECT 'CTAOPEN-202301' AS consol_journal_id, 1 AS line_number, {layer} AS layer_id,
           'OPENING_CTA' AS process, 'OPENING_BS' AS rule_id,
           'ELIM-CON' AS entity_code, CAST(NULL AS VARCHAR) AS related_entity_code,
           CAST(NULL AS VARCHAR) AS partner_entity_code, '{CTA_OPENING}' AS group_account,
           202301 AS period_key, 2023 AS fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST({-OPENING_CTA_USD_M} * 1e6 AS DECIMAL(18,2)) AS amount_usd,
           'Accumulated translation adjustment brought forward' AS narrative,
           'approved opening consolidated balance sheet' AS evidence
    UNION ALL BY NAME
    SELECT 'CTAOPEN-202301' AS consol_journal_id, 2 AS line_number, {layer} AS layer_id,
           'OPENING_CTA' AS process, 'OPENING_BS' AS rule_id,
           'ELIM-CON' AS entity_code, CAST(NULL AS VARCHAR) AS related_entity_code,
           CAST(NULL AS VARCHAR) AS partner_entity_code,
           '{RETAINED_EARNINGS_OPENING}' AS group_account,
           202301 AS period_key, 2023 AS fiscal_year,
           '{scenario}' AS scenario_code, '{version}' AS version_code, 'USD' AS currency_code,
           CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST({OPENING_CTA_USD_M} * 1e6 AS DECIMAL(18,2)) AS amount_usd,
           'Reclassified out of the opening retained earnings the ledgers brought in'
               AS narrative,
           'approved opening consolidated balance sheet' AS evidence
    """)

    # ------------------------------------------------------------------ amortisation
    # Per tranche, per month, from the month the acquisition completes. Starting at the
    # beginning of the acquisition year overstates the charge by the months before it -- a
    # small, plausible and entirely wrong number.
    con.execute("""
    CREATE OR REPLACE TABLE rpt_intangible_schedule AS
    WITH months AS (
        SELECT DISTINCT period_key, fiscal_year FROM dim_date WHERE accounting_period <= 12
    ),
    charge AS (
        SELECT p.ppa_id, p.acquisition_id, p.intangible_class, p.group_account,
               p.gross_usd, p.useful_life_years, p.amortisation_start_period,
               m.period_key, m.fiscal_year,
               CASE WHEN m.period_key >= p.amortisation_start_period
                    THEN round(p.gross_usd / (p.useful_life_years * 12.0), 2)
                    ELSE 0 END AS monthly_amortisation_usd
        FROM ref_ppa_intangible p CROSS JOIN months m
    ),
    capped AS (
        SELECT *,
               sum(monthly_amortisation_usd) OVER w AS accumulated_before,
               -- an intangible cannot amortise past its cost: the last month of a tranche
               -- carries whatever is left rather than a full month's charge
               least(monthly_amortisation_usd,
                     greatest(gross_usd - coalesce(sum(monthly_amortisation_usd) OVER w
                                                   - monthly_amortisation_usd, 0), 0))
                   AS amortisation_usd
        FROM charge
        WINDOW w AS (PARTITION BY ppa_id ORDER BY period_key ROWS UNBOUNDED PRECEDING)
    )
    SELECT ppa_id, acquisition_id, intangible_class, group_account, period_key, fiscal_year,
           gross_usd, amortisation_usd,
           sum(amortisation_usd) OVER (PARTITION BY ppa_id ORDER BY period_key
                                       ROWS UNBOUNDED PRECEDING) AS accumulated_usd,
           gross_usd - sum(amortisation_usd) OVER (PARTITION BY ppa_id ORDER BY period_key
                                                   ROWS UNBOUNDED PRECEDING) AS closing_nbv_usd
    FROM capped
    ORDER BY ppa_id, period_key
    """)

    counts["amortisation_legs"] = post_sql(con, f"""
    WITH charge AS (
        SELECT s.*, a.subsidiary_entity, a.parent_entity
        FROM rpt_intangible_schedule s JOIN ref_acquisition a USING (acquisition_id)
        WHERE s.amortisation_usd > 0.005
    )
    SELECT 'AMT-' || substr(md5(ppa_id || CAST(period_key AS VARCHAR)), 1, 10)
               AS consol_journal_id,
           1 AS line_number, {layer} AS layer_id, 'PPA_AMORT' AS process, ppa_id AS rule_id,
           'ELIM-CON' AS entity_code, subsidiary_entity AS related_entity_code,
           parent_entity AS partner_entity_code, '{PPA_AMORT_EXPENSE}' AS group_account,
           period_key, fiscal_year, '{scenario}' AS scenario_code, '{version}' AS version_code,
           'USD' AS currency_code, CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(amortisation_usd AS DECIMAL(18,2)) AS amount_usd,
           'Amortisation of ' || intangible_class || ' acquired with ' || acquisition_id
               AS narrative,
           ppa_id AS evidence
    FROM charge
    UNION ALL BY NAME
    SELECT 'AMT-' || substr(md5(ppa_id || CAST(period_key AS VARCHAR)), 1, 10)
               AS consol_journal_id,
           2 AS line_number, {layer} AS layer_id, 'PPA_AMORT' AS process, ppa_id AS rule_id,
           'ELIM-CON' AS entity_code, subsidiary_entity AS related_entity_code,
           parent_entity AS partner_entity_code, '{PPA_ACCUM_AMORT}' AS group_account,
           period_key, fiscal_year, '{scenario}' AS scenario_code, '{version}' AS version_code,
           'USD' AS currency_code, CAST(NULL AS DECIMAL(18,2)) AS amount_local,
           CAST(-amortisation_usd AS DECIMAL(18,2)) AS amount_usd,
           'Accumulated amortisation of acquired intangibles' AS narrative,
           ppa_id AS evidence
    FROM charge
    """)

    counts["acquisitions"] = con.execute(
        "SELECT count(*) FROM rpt_goodwill_bridge").fetchone()[0]
    counts["intangible_tranches"] = con.execute(
        "SELECT count(*) FROM ref_ppa_intangible").fetchone()[0]
    return counts


def elimination_reconciliation(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """
    Gross parent investment, eliminated investment, residual -- relationship by relationship.

    For a consolidated subsidiary the residual must be nil. A residual that is not nil means
    the group is carrying an investment in something it also consolidates, which double counts
    the net assets.
    """
    return con.execute(f"""
        WITH held AS (
            SELECT entity_code AS parent_entity, partner_entity_code AS subsidiary_entity,
                   round(sum(amount_usd), 2) AS gross_investment_usd
            FROM fact_layer1_usd WHERE group_account = '{INVESTMENT}' GROUP BY ALL
        ),
        eliminated AS (
            SELECT partner_entity_code AS parent_entity,
                   related_entity_code AS subsidiary_entity,
                   round(sum(amount_usd), 2) AS eliminated_usd
            FROM fact_consol_journal
            WHERE process = 'INVESTMENT' AND group_account = '{INVESTMENT}'
            GROUP BY ALL
        )
        SELECT coalesce(h.parent_entity, e.parent_entity) AS parent_entity,
               coalesce(h.subsidiary_entity, e.subsidiary_entity) AS subsidiary_entity,
               coalesce(h.gross_investment_usd, 0) AS gross_investment_usd,
               coalesce(e.eliminated_usd, 0) AS eliminated_usd,
               round(coalesce(h.gross_investment_usd, 0)
                     + coalesce(e.eliminated_usd, 0), 2) AS residual_usd
        FROM held h FULL OUTER JOIN eliminated e USING (parent_entity, subsidiary_entity)
        ORDER BY abs(coalesce(h.gross_investment_usd, 0)
                     + coalesce(e.eliminated_usd, 0)) DESC
    """).fetchall()
