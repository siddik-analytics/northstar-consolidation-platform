"""
The Phase 4 consolidation control suite.

Three statuses, as everywhere else in the platform: `PASS`, `FAIL` (the engine is wrong, and a
blocking failure stops certification) and `SOURCE_FINDING` (a defect in data this phase may not
change). Nothing is downgraded to a warning to obtain a green dashboard.

**Every control iterates from the authority that requires the data, never from the data being
tested.** That rule cost the platform two phases before it was written down -- `P2-IC-01`
walked the intercompany lines that already carried a counterparty and `P2-INV-01` walked the
investments the ledger already held, and neither could fail. So here:

| Control family | Starts from |
|---|---|
| ownership | `ref_ownership`, the ownership register |
| investment | `ref_investment_register` |
| PPA and goodwill | `ref_acquisition` and `ref_ppa_intangible` |
| NCI | the ownership register's non-controlling percentages |
| intercompany | the approved relationship population in `ref_ic_side` |
| FX and CTA | the rate requirements implied by the entity-period population |
| unrealised profit | `ref_ic_inventory_holding`, the transaction population |
| management adjustments | `ref_management_adjustment`, the approved register |

A required record that is **missing** therefore fails a control, which is the whole point: the
absence of a row is exactly what a control that starts from the rows cannot see.
"""

from __future__ import annotations

import csv
import sys

import duckdb

from .config import (CONTROL_RESULTS, MANAGEMENT_LAYERS, STATUTORY_LAYERS,
                     TOL_BALANCE_USD, TOL_IC_RESIDUAL_USD,
                     TOL_STATEMENT_USD, writing_artefacts)



class Result(list):
    def add(self, cid, name, severity, status, measured="", threshold="", detail="",
            defect=""):
        self.append(dict(control_id=cid, control_name=name, severity=severity,
                         status=status, measured=str(measured), threshold=str(threshold),
                         defect_reference=defect, detail=detail))

    def ok(self, cid, name, severity, condition, measured, threshold, detail="", defect=""):
        self.add(cid, name, severity, "PASS" if condition else "FAIL", measured, threshold,
                 detail, defect)

    @property
    def failed(self):
        return [r for r in self if r["status"] == "FAIL" and r["severity"] == "BLOCKING"]

    @property
    def findings(self):
        return [r for r in self if r["status"] == "SOURCE_FINDING"]


def _one(con, sql):
    row = con.execute(sql).fetchone()
    return row[0] if row and row[0] is not None else 0


def run(con: duckdb.DuckDBPyConnection) -> Result:
    r = Result()
    statutory = ", ".join(str(x) for x in STATUTORY_LAYERS)
    management = ", ".join(str(x) for x in MANAGEMENT_LAYERS)

    # ================================================================== ownership
    from . import ownership
    r.ok("P4-OWN-01", "No circular ownership", "BLOCKING",
         not ownership.cycles(con), len(ownership.cycles(con)), 0,
         "an entity in its own ownership path would consolidate itself")
    r.ok("P4-OWN-02", "Every consolidated entity has one valid ownership path", "BLOCKING",
         not ownership.missing_path(con), str(ownership.missing_path(con)[:3]), 0,
         "walked from the ownership register, so an entity the register omits fails here")
    r.ok("P4-OWN-03", "Ownership effective dates do not overlap", "BLOCKING",
         not ownership.overlapping_effective_dates(con),
         len(ownership.overlapping_effective_dates(con)), 0,
         "an overlap makes the percentage for a month ambiguous")
    r.ok("P4-OWN-04", "Ownership percentages are valid and complement the NCI share",
         "BLOCKING", not ownership.invalid_percentages(con),
         str(ownership.invalid_percentages(con)[:3]), 0, "")
    r.ok("P4-OWN-05", "The ownership register and the investment register agree", "BLOCKING",
         not ownership.register_disagreement(con),
         str(ownership.register_disagreement(con)[:3]), 0,
         "a subsidiary consolidated on a relationship nobody paid for, or an investment in "
         "something not consolidated")
    # The expectation is taken FROM THE REGISTER -- the entities whose registered parent is
    # not the ultimate parent -- rather than written here as a number. A hard-coded four would
    # be a control that has to be edited whenever the group changes, which is a control that
    # will eventually be edited to agree with whatever the engine produced.
    expected_tier2, second_tier = con.execute("""
        SELECT (SELECT count(DISTINCT o.entity_code) FROM ref_ownership o
                -- held by an entity that is itself held by somebody: the register's own
                -- definition of a second tier, with no entity codes written down here
                WHERE o.parent_entity_code IN (SELECT entity_code FROM ref_ownership)),
               (SELECT count(DISTINCT entity_code) FROM dim_ownership_period
                WHERE tiers_to_parent > 1)
    """).fetchone()
    r.ok("P4-OWN-06", "Second-tier holdings are resolved through their own parent", "BLOCKING",
         second_tier == expected_tier2 and second_tier > 0,
         f"{second_tier} resolved, {expected_tier2} registered", "equal",
         "an entity held by an operating company rather than by Topco consolidates through "
         "its own parent; a flat register would consolidate it one tier too high and the "
         "group percentage would be its direct percentage")

    # ================================================================== FX and CTA
    missing_rates = _one(con, """
        SELECT count(*) FROM (
            -- the requirement, not the supply: every currency and period for which an entity
            -- actually posted something and therefore needs translating
            SELECT DISTINCT e.functional_currency, m.period_key
            FROM stg_entity_movement m JOIN dim_entity e USING (entity_code)
            WHERE e.entity_type <> 'ELIMINATION'
        ) req
        LEFT JOIN vw_rate rt ON rt.currency_code = req.functional_currency
                            AND rt.period_key = req.period_key
        WHERE rt.currency_code IS NULL OR rt.avg_rate IS NULL OR rt.close_rate IS NULL""")
    r.ok("P4-FX-01", "Every currency and period the entities require has both rates",
         "BLOCKING", missing_rates == 0, missing_rates, 0,
         "CTL-FX-01, iterated from the entity-period population that NEEDS a rate rather "
         "than from the rates that happen to exist")

    hist_missing = _one(con, """
        SELECT count(*) FROM dim_entity e
        LEFT JOIN vw_opening_rate o ON o.entity_code = e.entity_code
        WHERE e.entity_type <> 'ELIMINATION' AND o.entity_code IS NULL""")
    r.ok("P4-FX-02", "Every entity has a registered opening translation base", "BLOCKING",
         hist_missing == 0, hist_missing, 0, "FX-P16")

    equity_at_close = _one(con, """
        SELECT count(*) FROM fact_layer1_usd u JOIN dim_account a USING (group_account)
        WHERE a.fx_method = 'HIST' AND u.translation_basis = 'CLOSE_RATE'""")
    r.ok("P4-FX-03", "Historical-rate equity is never translated at a closing rate",
         "BLOCKING", equity_at_close == 0, equity_at_close, 0,
         "FX-P03. Retranslating contributed capital would make CTA a plug rather than a "
         "residual, and the balance sheet would still balance")

    cta_rows, cta_agree, cta_worst = con.execute("""
        SELECT count(*),
               count(*) FILTER (WHERE abs(-c.cta_movement_usd / 1e6
                                          - o.cta_movement_usd_m) <= 0.0005),
               round(max(abs(-c.cta_movement_usd / 1e6 - o.cta_movement_usd_m)), 6)
        FROM stg_cta_movement c JOIN ref_cta_expectation o USING (entity_code, period_key)
    """).fetchone()
    uncovered = _one(con, """
        SELECT count(*) FROM ref_cta_expectation o
        LEFT JOIN stg_cta_movement c USING (entity_code, period_key)
        WHERE c.entity_code IS NULL""")
    r.ok("P4-FX-04", "Derived CTA reproduces the independent expectation", "BLOCKING",
         cta_agree == cta_rows and uncovered == 0,
         f"{cta_agree}/{cta_rows} agree, worst {cta_worst} USD m, {uncovered} untested",
         "all rows within USD 1",
         "CTL-FX-04, CTL-FX-12. The oracle is read here and by nothing that computes CTA. "
         "Iterated from the expectation's population, so an entity-period the engine failed "
         "to produce fails the control rather than disappearing from it")

    usd_cta = _one(con, """
        SELECT round(sum(abs(cta_movement_usd)), 2) FROM stg_cta_movement
        WHERE currency_code = 'USD'""")
    r.ok("P4-FX-05", "The presentation currency generates no translation adjustment",
         "BLOCKING", usd_cta == 0, usd_cta, 0,
         "every translation rule must give the same answer at a rate of one; any difference "
         "is a defect in the rules themselves")

    cta_break = _one(con, """
        SELECT count(*) FROM (
            SELECT entity_code, fiscal_year, closing_usd,
                   lag(closing_usd) OVER (PARTITION BY entity_code ORDER BY fiscal_year)
                       AS prior_closing, opening_usd
            FROM rpt_cta_rollforward
        ) WHERE prior_closing IS NOT NULL AND abs(opening_usd - prior_closing) > 0.01""")
    r.ok("P4-FX-06", "The CTA roll-forward is continuous across periods", "BLOCKING",
         cta_break == 0, cta_break, 0,
         "CTL-FX-09. A discontinuity means a closed period was restated or the engine "
         "recomputed CTA from scratch instead of rolling it forward")

    nci_cta_wrong = _one(con, """
        SELECT count(*) FROM stg_cta_movement c
        JOIN dim_ownership_period o USING (entity_code, period_key)
        WHERE abs(c.cta_nci_usd - (c.cta_movement_usd - c.cta_group_usd)) > 0.01
           OR (o.effective_nci_pct = 0 AND abs(c.cta_nci_usd) > 0.01)""")
    r.ok("P4-FX-07", "The NCI share of the translation movement is allocated correctly",
         "BLOCKING", nci_cta_wrong == 0, nci_cta_wrong, 0,
         "CTL-CON-11. Allocating all of a partly owned subsidiary's translation to group "
         "equity overstates it and understates NCI by the same amount, and total equity is "
         "unchanged, so nothing else catches it")

    fx_cash_vs_cta = con.execute("""
        SELECT round(sum(fx_effect_on_cash_usd) / 1e6, 4),
               round(sum(fx_non_cash_usd) / 1e6, 4) FROM rpt_cash_flow""").fetchone()
    r.ok("P4-FX-08", "The FX effect on cash is not the translation adjustment", "BLOCKING",
         abs(fx_cash_vs_cta[0]) < abs(fx_cash_vs_cta[1]) and fx_cash_vs_cta[0] != 0,
         f"on cash {fx_cash_vs_cta[0]}m, non-cash {fx_cash_vs_cta[1]}m", "distinct and both non-nil",
         "CTL-FX-11. Routing the whole translation movement through the cash line makes the "
         "statement still tie while reporting an implausible FX effect on a mostly-USD cash "
         "balance: every balancing control passes and only this one objects")

    # ================================================================== intercompany
    ic_unmatched = _one(con, f"""
        SELECT count(*) FROM rpt_ic_exception WHERE exception_type <> 'MATCHED'""")
    ic_worst = _one(con, """SELECT round(max(abs(residual_usd)), 2) FROM rpt_ic_exception""")
    r.ok("P4-IC-01", "Every intercompany relationship nets by entity pair", "BLOCKING",
         ic_unmatched == 0, f"{ic_unmatched} unmatched, worst {ic_worst}",
         f"0 unmatched, {TOL_IC_RESIDUAL_USD} USD per pair",
         "CTL-IC-01, CTL-IC-02. Matched at the PAIR: a group total nets whenever everything "
         "happens to agree and says nothing when it does not, which is what fault F02 is")

    ic_pop = _one(con, "SELECT count(*) FROM rpt_ic_exception")
    r.ok("P4-IC-02", "The intercompany population is not empty", "BLOCKING", ic_pop > 0,
         ic_pop, "> 0",
         "a pair reconciliation over no pairs passes trivially, which is how a matching "
         "engine that stopped working would look")

    ic_residual = _one(con, """
        SELECT round(max(abs(t)), 2) FROM (
            SELECT group_account, period_key,
                   sum(sum(amount_usd)) OVER (PARTITION BY group_account ORDER BY period_key
                                              ROWS UNBOUNDED PRECEDING) AS t
            FROM vw_statutory_fact
            WHERE group_account IN ('120500','210500','125100','225100','175100','235100')
            GROUP BY group_account, period_key)""")
    r.ok("P4-IC-03", "Consolidated intercompany balances are nil", "BLOCKING",
         ic_residual <= 1.00, ic_residual, "1.00 USD",
         "CTL-IC-07, on the cumulative balance rather than the month's movement")

    ic_pl_residual = _one(con, """
        SELECT round(max(abs(t)), 2) FROM (
            SELECT group_account, sum(amount_usd) AS t FROM vw_statutory_fact
            WHERE group_account LIKE '49%' OR group_account LIKE '59%'
               OR group_account LIKE '695%' OR group_account LIKE '795%'
            GROUP BY group_account)""")
    r.ok("P4-IC-04", "Consolidated intercompany income and expense are nil", "BLOCKING",
         ic_pl_residual <= 1.00, ic_pl_residual, "1.00 USD", "CTL-IC-02")

    unclassified = _one(con, """
        SELECT count(*) FROM rpt_ic_exception WHERE exception_type IS NULL""")
    r.ok("P4-IC-05", "Every intercompany difference carries a classification", "BLOCKING",
         unclassified == 0, unclassified, 0,
         "matched, timing, FX, missing counterpart or amount mismatch. A difference nobody "
         "has classified is indistinguishable from one nobody has looked at")

    # ================================================================== investments
    inv_missing = _one(con, """
        SELECT count(*) FROM ref_investment_register reg
        LEFT JOIN (SELECT DISTINCT parent_entity, subsidiary_entity FROM ref_acquisition) a
               ON a.parent_entity = reg.parent_entity
              AND a.subsidiary_entity = reg.subsidiary_entity
        WHERE a.parent_entity IS NULL""")
    r.ok("P4-INV-01", "Every register relationship has an acquisition schedule", "BLOCKING",
         inv_missing == 0, inv_missing, 0,
         "iterated from the investment register: a relationship with no schedule is invisible "
         "to a control that starts from the schedules")

    from . import investments
    inv_residual = [row for row in investments.elimination_reconciliation(con)
                    if abs(row[4]) > 0.01]
    r.ok("P4-INV-02", "Every investment in a consolidated subsidiary eliminates in full",
         "BLOCKING", not inv_residual,
         f"{len(inv_residual)} with a residual, worst "
         f"{max((abs(x[4]) for x in inv_residual), default=0):,.2f}", "0.01 USD",
         "relationship by relationship, never at group total: a group-level elimination "
         "cannot express a second-tier holding at all")

    # Iterated from the investment REGISTER, not from the acquisition schedule the engine was
    # driven by. A schedule that says the group owned something from January is perfectly
    # self-consistent with entries posted from January; only the register knows when the group
    # actually bought it. For a relationship that predates the reporting window the
    # elimination belongs in the month the window opens, because there is no earlier month to
    # post it in -- so the expected month is the later of the two.
    con.execute("""
    CREATE OR REPLACE TEMP TABLE chk_investment_timing AS
    WITH expected AS (
        SELECT a.acquisition_id,
               greatest(CAST(strftime(reg.consolidation_effective_date, '%Y%m') AS INTEGER),
                        (SELECT min(period_key) FROM dim_date WHERE accounting_period <= 12))
                   AS expected_period
        FROM ref_investment_register reg
        JOIN ref_acquisition a ON a.investment_id = reg.investment_id
    ),
    posted AS (
        SELECT rule_id AS acquisition_id, min(period_key) AS first_period,
               max(period_key) AS last_period, count(*) AS legs
        FROM fact_consol_journal WHERE process = 'INVESTMENT' GROUP BY 1
    )
    SELECT e.acquisition_id, e.expected_period, p.first_period, p.last_period,
           coalesce(p.legs, 0) AS legs
    FROM expected e LEFT JOIN posted p USING (acquisition_id)
    """)
    timing_bad = _one(con, """
        SELECT count(*) FROM chk_investment_timing
        WHERE legs = 0 OR first_period <> expected_period OR last_period <> expected_period""")
    r.ok("P4-INV-03", "Every investment is eliminated in the month the register gives it",
         "BLOCKING", timing_bad == 0, timing_bad, 0,
         "CTL-CON-02. Eliminating early removes equity that was still outside the group; "
         "eliminating late leaves an investment in a subsidiary the group already owns. "
         "Eliminating not at all leaves both, and every total stays plausible")

    # ================================================================== PPA and goodwill
    gw_plug = _one(con, """
        SELECT count(*) FROM rpt_goodwill_bridge
        WHERE abs(consideration_usd + nci_at_acquisition_usd - fair_value_net_assets_usd
                  - goodwill_usd) > 0.01""")
    r.ok("P4-PPA-01", "Goodwill is the residual of the bridge and never a plug", "BLOCKING",
         gw_plug == 0, gw_plug, 0,
         "consideration plus non-controlling interest, less the fair value of identifiable "
         "net assets, equals goodwill -- computed for every acquisition in the register")

    gw_negative = _one(con, """
        SELECT count(*) FROM rpt_goodwill_bridge WHERE goodwill_usd < -0.01""")
    r.ok("P4-PPA-02", "No acquisition produces negative goodwill", "WARNING",
         gw_negative == 0, gw_negative, 0,
         "a bargain purchase is possible but would be a disclosure, not a silent balance")

    dtl_wrong = _one(con, """
        SELECT count(*) FROM rpt_goodwill_bridge b JOIN ref_acquisition a USING (acquisition_id)
        WHERE abs(b.deferred_tax_usd - b.intangibles_usd * a.deferred_tax_rate) > 0.01""")
    r.ok("P4-PPA-03", "Deferred tax on the fair value uplift follows the schedule's rate",
         "BLOCKING", dtl_wrong == 0, dtl_wrong, 0, "")

    gw_traceable = _one(con, """
        SELECT count(*) FROM fact_consol_journal
        WHERE group_account = '160100'
          AND (rule_id IS NULL OR rule_id NOT IN (SELECT acquisition_id FROM ref_acquisition))""")
    r.ok("P4-PPA-04", "Every goodwill posting names the acquisition it arose on", "BLOCKING",
         gw_traceable == 0, gw_traceable, 0,
         "goodwill that cannot be traced to an acquisition is a balance nobody can explain "
         "and nobody can impair")

    # ================================================================== intangibles
    tranche_missing = _one(con, """
        SELECT count(*) FROM ref_ppa_intangible p
        LEFT JOIN rpt_intangible_schedule s ON s.ppa_id = p.ppa_id
        WHERE s.ppa_id IS NULL""")
    r.ok("P4-INT-01", "Every intangible tranche has an amortisation schedule", "BLOCKING",
         tranche_missing == 0, tranche_missing, 0,
         "iterated from the PPA register")

    # Again measured against the register rather than against the PPA schedule the charge was
    # computed from. A schedule that starts amortising in January is internally consistent
    # with a charge that starts in January.
    amort_early = _one(con, """
        SELECT count(*) FROM rpt_intangible_schedule s
        JOIN ref_ppa_intangible p USING (ppa_id)
        JOIN ref_acquisition a ON a.acquisition_id = p.acquisition_id
        JOIN ref_investment_register reg ON reg.investment_id = a.investment_id
        WHERE s.amortisation_usd > 0.005
          AND s.period_key < CAST(strftime(reg.consolidation_effective_date, '%Y%m') AS INTEGER)""")
    r.ok("P4-INT-02", "Amortisation begins in the month the acquisition completes",
         "BLOCKING", amort_early == 0, amort_early, 0,
         "starting at the beginning of the acquisition year overstates the charge by the "
         "months before it: small, plausible and entirely wrong")

    over_amortised = _one(con, """
        SELECT count(*) FROM rpt_intangible_schedule
        WHERE closing_nbv_usd < -0.01 OR accumulated_usd > gross_usd + 0.01""")
    r.ok("P4-INT-03", "No intangible amortises past its cost", "BLOCKING",
         over_amortised == 0, over_amortised, 0, "")

    nbv_break = _one(con, """
        SELECT count(*) FROM (
            SELECT ppa_id, period_key, closing_nbv_usd, gross_usd, accumulated_usd
            FROM rpt_intangible_schedule)
        WHERE abs(gross_usd - accumulated_usd - closing_nbv_usd) > 0.01""")
    r.ok("P4-INT-04", "Gross less accumulated amortisation equals net book value",
         "BLOCKING", nbv_break == 0, nbv_break, 0, "the roll-forward closes every period")

    # ================================================================== NCI
    nci_entities = _one(con, """
        SELECT count(DISTINCT entity_code) FROM dim_ownership_period
        WHERE effective_nci_pct > 0""")
    nci_allocated = _one(con, """
        SELECT count(DISTINCT related_entity_code) FROM fact_consol_journal
        WHERE process = 'NCI_RESULT'""")
    r.ok("P4-NCI-01", "Every entity with a non-controlling interest is allocated one",
         "BLOCKING", nci_entities == nci_allocated, f"{nci_allocated} of {nci_entities}",
         "all of them",
         "iterated from the ownership register's non-controlling percentages, so an entity "
         "the engine failed to allocate fails here rather than being absent")

    nci_from_group = _one(con, """
        SELECT count(*) FROM stg_nci_result n
        LEFT JOIN dim_ownership_period o USING (entity_code, period_key)
        WHERE o.effective_nci_pct IS NULL OR abs(n.nci_pct - o.effective_nci_pct) > 1e-9""")
    r.ok("P4-NCI-02", "The NCI share uses the entity's own effective percentage", "BLOCKING",
         nci_from_group == 0, nci_from_group, 0,
         "computed on NIG-510's result at its own 20%, never on a group total and never by "
         "applying a percentage twice down the ownership chain")

    nci_double = _one(con, """
        SELECT count(*) FROM (
            SELECT related_entity_code, period_key, count(*) AS n
            FROM fact_consol_journal WHERE process = 'NCI_RESULT' AND group_account = '850100'
            GROUP BY ALL HAVING count(*) > 1)""")
    r.ok("P4-NCI-03", "The NCI result is attributed once per entity and period", "BLOCKING",
         nci_double == 0, nci_double, 0, "a second allocation would double the minority's share")

    nci_roll = _one(con, """
        SELECT count(*) FROM rpt_nci_rollforward
        WHERE abs(opening_usd + share_of_result_usd + distributions_usd + share_of_cta_usd
                  + acquisition_and_ownership_usd - closing_usd) > 0.01""")
    r.ok("P4-NCI-04", "The NCI roll-forward closes every year", "BLOCKING",
         nci_roll == 0, nci_roll, 0,
         "opening plus the share of result, less distributions, plus the share of "
         "translation, plus ownership movements, equals closing")

    nci_in_ebitda = _one(con, """
        SELECT count(*) FROM dim_account WHERE group_account = '850100' AND is_ebitda""")
    r.ok("P4-NCI-05", "The NCI charge sits below tax and never inside EBITDA", "BLOCKING",
         nci_in_ebitda == 0, nci_in_ebitda, 0,
         "the credit agreement defines Consolidated EBITDA on the group, not on the group's "
         "economic share, so covenant leverage is calculated on the 100% basis")

    # ================================================================== unrealised profit
    from . import pup
    pup_worst = max((abs(row[3]) for row in pup.acceptance(con)), default=0)
    pup_rows = len(pup.acceptance(con))
    r.ok("P4-PUP-01", "Unrealised profit reproduces the independent expectation", "BLOCKING",
         pup_worst <= 1.00 and pup_rows > 0, f"{pup_rows} periods, worst {pup_worst}",
         "1.00 USD",
         "computed from the surviving FIFO layers at each layer's own margin. The holdings "
         "file's own unrealised-profit column is read here and by nothing that computes it")

    # Iterated from the intercompany TRANSACTIONS, which are the authority that requires the
    # calculation. The holdings table is derived from them, so a control that counted holdings
    # against layers would compare a derivation with itself and pass however many rows went
    # missing from both.
    pup_pop = _one(con, "SELECT count(*) FROM ref_ic_inventory_transaction")
    pup_missing = _one(con, """
        SELECT count(*) FROM ref_ic_inventory_transaction t
        LEFT JOIN stg_pup_layer p
               ON p.transaction_period = t.period_key AND p.period_key = t.period_key
              AND p.seller_entity = t.seller_entity AND p.buyer_entity = t.buyer_entity
              AND p.buyer_inventory_account = t.buyer_inventory_account
        WHERE p.period_key IS NULL""")
    pup_wrong = _one(con, """
        SELECT count(*) FROM ref_ic_inventory_transaction t
        JOIN stg_pup_layer p
          ON p.transaction_period = t.period_key AND p.period_key = t.period_key
         AND p.seller_entity = t.seller_entity AND p.buyer_entity = t.buyer_entity
         AND p.buyer_inventory_account = t.buyer_inventory_account
        WHERE abs(p.transfer_price_usd - t.transfer_price_usd) > 0.01
           OR abs(p.ic_gross_profit_usd - t.ic_gross_profit_usd) > 0.01""")
    r.ok("P4-PUP-02", "Every intercompany sale reaches the calculation at its own value",
         "BLOCKING", pup_missing == 0 and pup_wrong == 0 and pup_pop > 0,
         f"{pup_pop - pup_missing} of {pup_pop} present, {pup_wrong} at the wrong value",
         "all of them, at the transacted value")

    pup_release = _one(con, """
        SELECT count(*) FROM rpt_pup_provision WHERE movement_usd < -0.005""")
    r.ok("P4-PUP-03", "Prior-period unrealised profit reverses as the stock is sold on",
         "BLOCKING", pup_release > 0, pup_release, "> 0",
         "posted as the movement in the provision, so the release happens by construction. "
         "A provision that only ever grows is one that is never released")

    pup_blended = _one(con, """
        SELECT count(*) FROM stg_pup_layer
        WHERE abs(unrealised_profit_computed_usd - value_remaining_usd * layer_margin) > 0.01""")
    r.ok("P4-PUP-04", "Each surviving layer carries its own margin", "BLOCKING",
         pup_blended == 0, pup_blended, 0,
         "a buyer holding two months of purchases at 12% and 9% does not hold them at 10.5%")

    # ================================================================== journals and layers
    from . import journals
    unbalanced = journals.unbalanced(con)
    r.ok("P4-JNL-01", "Every consolidation entry in layers 2 to 4 balances", "BLOCKING",
         not unbalanced, f"{len(unbalanced)} unbalanced", 0,
         "layer 5 is excluded by design: it IS the entry that makes the translated trial "
         "balance sum to zero, so it does not balance alone")

    bad_layer = _one(con, f"""
        SELECT count(*) FROM fact_consol_journal WHERE layer_id NOT IN (2, 3, 4, 5)""")
    r.ok("P4-LAY-01", "Only the declared consolidation layers are posted", "BLOCKING",
         bad_layer == 0, bad_layer, 0,
         "CTL-CON-09. Layer 1 originates outside this phase and is never written here")

    tb_15 = _one(con, """
        SELECT round(max(abs(t)), 2) FROM (
            SELECT period_key, sum(amount_usd) AS t FROM fact_financials
            WHERE layer_id IN (1, 5) GROUP BY 1)""")
    r.ok("P4-LAY-02", "Layers 1 and 5 together sum to zero in every period", "BLOCKING",
         tb_15 <= TOL_BALANCE_USD, tb_15, TOL_BALANCE_USD,
         "CTL-TB-03. This is what CTA IS, so it is the only form in which layer 5 can be "
         "tested for balance")

    leak = _one(con, f"""
        SELECT count(*) FROM vw_statutory_fact WHERE layer_id = 4""")
    r.ok("P4-LAY-03", "No management adjustment reaches the statutory basis", "BLOCKING",
         leak == 0, leak, 0,
         "the statutory basis is layers {}, selected at the architecture level rather than "
         "filtered at report time".format(statutory))

    mgmt_missing = _one(con, f"""
        SELECT count(*) FROM (SELECT DISTINCT layer_id FROM dim_consolidation_layer
                              WHERE in_management_view) l
        LEFT JOIN (SELECT DISTINCT layer_id FROM vw_management_fact) f USING (layer_id)
        WHERE f.layer_id IS NULL AND l.layer_id <> 4""")
    r.ok("P4-LAY-04", "The management basis contains every layer it should", "BLOCKING",
         mgmt_missing == 0, mgmt_missing, 0, f"layers {management}")

    source_cta = _one(con, """
        SELECT count(*) FROM fact_layer1_usd
        WHERE group_account IN ('330100', '330200', '330300', '340400')""")
    r.ok("P4-LAY-05", "No source ledger carries a translation adjustment or reserve",
         "BLOCKING", source_cta == 0, source_cta, 0,
         "a source-layer CTA would be a plug, and the balance sheet would balance around it")

    # ================================================================== the two facts
    # `fact_financials` layers 2 to 5 are BUILT from `fact_consol_journal`, so they cannot
    # disagree by construction. Testing it anyway is not about the arithmetic: it is about
    # nobody having since added a path that writes one without the other (ADR-0024).
    fact_break = _one(con, """
        SELECT count(*) FROM (
            SELECT layer_id, period_key, group_account,
                   round(sum(amount_usd), 2) AS journal_usd
            FROM fact_consol_journal GROUP BY ALL
        ) j
        FULL OUTER JOIN (
            SELECT layer_id, period_key, group_account,
                   round(sum(amount_usd), 2) AS fact_usd
            FROM fact_financials WHERE layer_id <> 1 GROUP BY ALL
        ) f USING (layer_id, period_key, group_account)
        WHERE abs(coalesce(j.journal_usd, 0) - coalesce(f.fact_usd, 0)) > 0.01""")
    r.ok("P4-FCT-01", "The journal fact and the financial fact reconcile exactly", "BLOCKING",
         fact_break == 0, fact_break, 0,
         "ADR-0024. Two facts are held so that a total can be queried and an entry can be "
         "read; they are only safe to hold while they agree")

    layer1_in_journal = _one(con, """
        SELECT count(*) FROM fact_consol_journal WHERE layer_id = 1""")
    r.ok("P4-FCT-02", "The entity ledgers are never copied into the journal fact", "BLOCKING",
         layer1_in_journal == 0, layer1_in_journal, 0,
         "layer 1 originates in the frozen Phase 3 conformed layer. A consolidation entry "
         "carrying it would make the reported figures depend on this phase")

    # ================================================================== statements
    bs_worst = _one(con, """
        SELECT round(max(abs(b)), 2) FROM (
            SELECT period_key, sum(balance_usd) AS b FROM rpt_balance_sheet GROUP BY 1)""")
    r.ok("P4-BS-01", "Assets equal liabilities plus equity in every period", "BLOCKING",
         bs_worst <= TOL_STATEMENT_USD, bs_worst, TOL_STATEMENT_USD,
         "no balancing account, no residual reserve and no forced caption")

    caption_dup = _one(con, """
        SELECT count(*) FROM (
            SELECT group_account, count(DISTINCT fs_caption_l2) AS n
            FROM dim_account WHERE statement = 'BS' AND NOT is_statistical
            GROUP BY 1 HAVING count(DISTINCT fs_caption_l2) > 1)""")
    r.ok("P4-BS-02", "Every balance sheet account maps to exactly one caption", "BLOCKING",
         caption_dup == 0, caption_dup, 0,
         "an account in two captions is counted twice and the statement still balances")

    caption_missing = _one(con, """
        SELECT count(*) FROM dim_account a
        WHERE a.statement = 'BS' AND NOT a.is_statistical
          AND (a.fs_caption_l2 IS NULL OR a.fs_caption_l2 = '')""")
    r.ok("P4-BS-03", "No balance sheet account is left without a caption", "BLOCKING",
         caption_missing == 0, caption_missing, 0,
         "an account with no caption disappears from the statement while staying in the fact")

    # 'Non-controlling interests' is legitimately a caption on both statements -- the share of
    # result below tax, and the share of net assets in equity -- so the test is for captions
    # that belong to the income statement ALONE.
    pl_in_bs = _one(con, """
        SELECT count(*) FROM rpt_balance_sheet b
        WHERE b.fs_caption_l2 IN (
            SELECT fs_caption_l2 FROM dim_account WHERE NOT is_statistical
            GROUP BY 1 HAVING bool_and(statement = 'IS'))""")
    r.ok("P4-BS-04", "No income statement caption appears in the balance sheet", "BLOCKING",
         pl_in_bs == 0, pl_in_bs, 0,
         "the result appears once, as its own equity line, and never as a P&L caption")

    result_once = _one(con, """
        SELECT count(*) FROM rpt_balance_sheet
        WHERE fs_caption_l2 = 'Result for the period' AND period_key = 202512""")
    r.ok("P4-BS-05", "The period result appears exactly once in equity", "BLOCKING",
         result_once == 1, result_once, 1,
         "it is the cumulative income statement balance INCLUDING the close. Excluding the "
         "close counts every closed year twice, once here and once in retained earnings")

    pl_arith = _one(con, """
        SELECT count(*) FROM rpt_income_statement
        WHERE abs(revenue_usd - cost_of_sales_usd - gross_profit_usd) > 0.02
           OR abs(ebitda_usd - depreciation_amortisation_usd - ebit_usd) > 0.02""")
    r.ok("P4-PL-01", "The income statement is internally consistent", "BLOCKING",
         pl_arith == 0, pl_arith, 0, "gross profit and EBIT follow from their components")

    cf_tie = _one(con, """
        SELECT round(max(abs(opening_cash_usd + operating_cash_flow_usd
                             + investing_cash_flow_usd + financing_cash_flow_usd
                             + fx_effect_on_cash_usd - closing_cash_usd)), 4)
        FROM rpt_cash_flow""")
    r.ok("P4-CF-01", "The cash flow ties in every period", "BLOCKING",
         cf_tie <= TOL_STATEMENT_USD, cf_tie, TOL_STATEMENT_USD,
         "opening plus operating, investing, financing and the effect of exchange rates "
         "equals closing, at the cent, in all 48 periods. Cash is never the residual, "
         "and the translation carried by the year-end close is presented as its own "
         "line rather than left to be absorbed by whichever bucket is nearest")

    cf_bs = _one(con, """
        SELECT round(max(abs(c.closing_cash_usd - b.balance_usd)), 2)
        FROM rpt_cash_flow c JOIN rpt_balance_sheet b
          ON b.period_key = c.period_key
         AND b.fs_caption_l2 = 'Cash and cash equivalents'""")
    r.ok("P4-CF-02", "Closing cash ties to the consolidated balance sheet", "BLOCKING",
         cf_bs <= TOL_STATEMENT_USD, cf_bs, TOL_STATEMENT_USD, "")

    uncategorised = _one(con, """
        SELECT count(*) FROM dim_account
        WHERE statement = 'BS' AND NOT is_statistical
          AND (cash_flow_category IS NULL OR cash_flow_category = '')""")
    r.ok("P4-CF-03", "Every balance sheet account has exactly one cash flow category",
         "BLOCKING", uncategorised == 0, uncategorised, 0,
         "CTL-FS-04. The statement ties by construction only if the categories partition the "
         "balance sheet; a mis-categorised account still ties while reporting the wrong line")

    # ================================================================== the two bases
    basis_rows = _one(con, "SELECT count(*) FROM rpt_basis_comparison")
    basis_bad = _one(con, """
        SELECT count(*) FROM rpt_basis_comparison WHERE NOT explained_by_layer_4""")
    r.ok("P4-BAS-01", "Management less statutory equals layer 4, for every headline measure",
         "BLOCKING", basis_bad == 0 and basis_rows == 28,
         f"{basis_rows - basis_bad} of {basis_rows} explained", "all of them",
         "revenue, gross profit, EBITDA, EBIT, net income, total assets and total equity, "
         "each of four years. Any other difference would mean the two bases diverge somewhere "
         "the layer architecture does not describe")

    layer4_legs = _one(con, "SELECT count(*) FROM fact_consol_journal WHERE layer_id = 4")
    # A disclosure rather than a test: it reports what the approved register contains so that a
    # comparison of two identical columns cannot be mistaken for a proof that they were kept
    # apart. It carries no pass condition because there is nothing here to fail.
    r.add("P4-BAS-02", "Layer 4 is empty under the approved adjustment register", "WARNING",
          "PASS", layer4_legs, "disclosed",
          "Both approved adjustments (MA-001, MA-002) are presentation reclassifications "
          "carrying a nil amount, so no layer-4 entry is posted and the management basis is "
          "numerically identical to the statutory basis for FY2023-FY2026. P4-BAS-01 and "
          "P4-LAY-03 therefore prove the architecture separates the bases but cannot prove it "
          "from production data. Fault fixture F4-MGT-LEAK supplies that proof by injecting a "
          "layer-4 adjustment and showing the statutory basis unmoved. An amount is NOT "
          "invented here to make the comparison look richer.")

    # ================================================================== management view
    unapproved = _one(con, """
        SELECT count(*) FROM ref_management_adjustment WHERE approval_status <> 'APPROVED'""")
    posted_ids = _one(con, """
        SELECT count(DISTINCT rule_id) FROM fact_consol_journal WHERE process = 'MGMT_ADJ'""")
    approved_ids = _one(con, """
        SELECT count(*) FROM ref_management_adjustment
        WHERE approval_status = 'APPROVED' AND abs(amount_usd) > 0.005""")
    r.ok("P4-MGT-01", "Only approved management adjustments are posted", "BLOCKING",
         posted_ids == approved_ids, f"{posted_ids} posted, {approved_ids} approved", "equal",
         "iterated from the adjustment register. An adjustment nobody has approved is a "
         "proposal, and a management view built on proposals is not a management view")

    anonymous = _one(con, """
        SELECT count(*) FROM ref_management_adjustment
        WHERE coalesce(preparer, '') = '' OR coalesce(approver, '') = ''
           OR coalesce(rationale, '') = ''""")
    r.ok("P4-MGT-02", "No management adjustment is anonymous", "BLOCKING",
         anonymous == 0, anonymous, 0, "CTL-CON-07")

    ebitda_same = _one(con, """
        SELECT count(*) FROM rpt_ebitda_bridge
        WHERE abs(adjusted_ebitda_usd - covenant_ebitda_usd) < 0.005""")
    r.ok("P4-MGT-03", "Adjusted and covenant EBITDA are computed separately", "WARNING",
         True, f"{ebitda_same} of 4 years equal", "reported, not failed",
         "the credit agreement caps the sponsor fee (CA-027) and permits unrealised foreign "
         "exchange (CA-030) where the management policy does neither, so the two measures "
         "are not assumed to be the same number")

    return r


def write(con: duckdb.DuckDBPyConnection, res: Result) -> None:
    if not writing_artefacts():
        return
    with open(CONTROL_RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(res)


def report(res: Result) -> None:
    passed = sum(1 for r in res if r["status"] == "PASS")
    print(f"{passed}/{len(res)} controls passed, {len(res.findings)} source findings, "
          f"{len(res.failed)} blocking failures")
    for row in res:
        if row["status"] != "PASS":
            print(f"  {row['status']:14} {row['severity']:8} {row['control_id']:11} "
                  f"{row['control_name'][:52]:54} {row['measured']} vs {row['threshold']}")


def main() -> int:
    from .config import DUCKDB_PATH
    con = duckdb.connect(str(DUCKDB_PATH))
    res = run(con)
    write(con, res)
    report(res)
    con.close()
    return 1 if res.failed else 0


if __name__ == "__main__":
    sys.exit(main())
