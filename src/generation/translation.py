"""
The cumulative translation adjustment, derived from the source ledgers.

Phase 2.0 absorbed a residual into investment-at-cost.  Phase 2.1 moved it to a named
holding-company equity reserve, `329100 Group reporting measurement reserve`.  Both were
plugs: a balance created so that the generated source data would agree with an
independently specified group target.  Phase 2.2 removes the mechanism entirely and
replaces it with the arithmetic that should always have closed the layer.

Why there is nothing left to plug
---------------------------------
A subsidiary's ledger is kept in its own currency.  Its share capital is a fixed local
amount struck at the rate ruling when it was contributed (FX-P03); its retained earnings
roll forward from locally-measured results; and every other balance is what the entity's
own economics produce.  Translate that ledger at closing rates and the difference between
the translated net assets and the sum of capital at historical rates plus results at the
rates when they were earned IS the cumulative translation adjustment.  It is not a
residual to be assigned somewhere -- it is the definition.

Phase 2.1's ledgers could not produce it, because contributed capital was re-pinned to a
closing-rate USD target every year: a German subsidiary's Stammkapital moved because
EUR/USD moved.  With the capital frozen in local currency, the layer-1 equity
roll-forward closes exactly:

    opening equity (at historical rates)
      + result for the period (at the rates when earned)
      + capital contributed          (at the rate on the contribution date)
      + equity brought in on acquisition
      - distributions                (at the rate on the payment date)
      + CTA                          (computed below)
      = closing equity translated at closing rates

`P2-FX-01` proves that identity against the generated ledgers, to the cent, in every
period.  There is no measurement reserve and no equivalent account anywhere in the source
architecture.

What this module produces
-------------------------
`data/reference/cta_expectation.csv` -- per entity and period, the opening net assets, the
rates applied, the result for the period, the movement on net assets, the movement on the
result, and the CTA movement and closing balance implied.  It is the expected result for
the Phase 5 translation engine (FX_CTA), and the anchored CTA roll-forward is derived from
it rather than asserted alongside it (ADR-0017).

`data/reference/layer1_equity_bridge.csv` -- the same identity presented as a bridge from
the approved consolidated anchors to what the sum of the source ledgers must say, so a
reviewer can check the closure without re-running the generator.

The bridge from layer 1 to the group
------------------------------------
The consolidated CTA is the layer-1 figure plus the translation of the balances that exist
only on consolidation:

    CTA(group) = CTA(layer 1)
               + FX on goodwill + FX on acquired intangibles     (layer-3 balances)
               - the non-controlling interest's share
               - the movement in unrealised intercompany profit

Only the two layer-3 FX terms remain estimates, because goodwill and acquired intangibles
exist in no source ledger.  Everything else is computed here.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from .common import REFERENCE, load_anchor, load_ic_anchor, write_csv
from .fx import _anchor_rates
from .investments import investments_at

#: Equity in the source ledgers.  There is no CTA account and no reserve: a local ledger
#: has neither, because both are created by the consolidation, not by the entity.
EQUITY_ACCOUNTS = ("310100", "310200", "315100", "320100", "320200", "320300")

#: The layer-3 balances whose retranslation belongs to the group CTA but to no entity.
LAYER3_FX = ("fx_on_goodwill", "fx_on_intangibles")


def _rate_set(period_key: int) -> str:
    return "FORECAST" if period_key // 100 == 2026 else "ACTUAL"


def _net_assets(em) -> float:
    """
    Net assets in local currency at the month end.

    Interim months carry the year's result in the income statement accounts rather than in
    equity -- the ledger closes them to retained earnings once, at the year end -- so the
    year-to-date result is part of net assets until it is closed.
    """
    ytd = 0.0 if em.context.get("year_end") else em.context.get("ytd_pl", 0.0)
    return -sum(em.bs_close.get(a, 0.0) for a in EQUITY_ACCOUNTS) - ytd


def cta_by_period(sb, rows) -> list[dict]:
    """
    The translation adjustment each foreign entity generates, month by month.

        CTA movement = opening net assets x (closing rate - prior closing rate)
                     + result for the period x (closing rate - average rate)
                     + equity movements x (closing rate - transaction rate)

    Every term comes from the entity's own ledger and the approved rate file.  Nothing
    references a group target, which is what makes this an expectation the Phase 5
    translation engine can be tested against rather than a number it must be given.
    """
    anchors = _anchor_rates()
    by_entity: dict[str, list] = defaultdict(list)
    for em in rows:
        by_entity[em.entity].append(em)

    out: list[dict] = []
    for code in sorted(by_entity):
        e = sb.ent[code]
        if e.currency == "USD":
            continue                      # the presentation currency generates no CTA
        months = sorted(by_entity[code], key=lambda x: x.period_key)
        events = sb.equity_events(code)
        opening_pk = e.effective_from.year * 100 + e.effective_from.month
        prev_rate: float | None = None
        prev_na: float | None = None
        cumulative = 0.0
        for em in months:
            pk = em.period_key
            rs = _rate_set(pk)
            close = sb.m.rate(e.currency, pk, "CLOSE", rs)
            avg = sb.m.rate(e.currency, pk, "AVG", rs)
            na_close = _net_assets(em)
            result = -sum(em.pl.values())
            # equity movements dated in this month, credit-positive, with the rate that
            # translated them when they happened
            moved = 0.0
            on_events = 0.0
            for acct, dated in events.items():
                for event_pk, amount in dated:
                    if event_pk != pk:
                        continue
                    rate = avg if acct == "320300" else close
                    moved += -amount
                    on_events += -amount * (close - rate)
            if prev_rate is None:
                # An entity in the opening balance sheet was translated at the FY2022
                # closing anchor; one acquired later, at the rate on its effective date.
                prev_rate = (anchors[(e.currency, 2022, "ACTUAL")][1]
                             if opening_pk <= 202301 else close)
                prev_na = na_close - result - moved
            on_net_assets = prev_na * (close - prev_rate)
            on_result = result * (close - avg)
            movement = (on_net_assets + on_result + on_events) / 1e6
            cumulative += movement
            out.append(dict(
                entity_code=code, period_key=pk, currency_code=e.currency,
                opening_net_assets_local=round(prev_na, 2),
                closing_net_assets_local=round(na_close, 2),
                result_local=round(result, 2),
                equity_movement_local=round(moved, 2),
                opening_rate=round(prev_rate, 8), closing_rate=round(close, 8),
                average_rate=round(avg, 8),
                cta_on_opening_net_assets=round(on_net_assets / 1e6, 6),
                cta_on_result=round(on_result / 1e6, 6),
                cta_on_equity_movements=round(on_events / 1e6, 6),
                cta_movement_usd_m=round(movement, 6),
                cta_cumulative_usd_m=round(cumulative, 6)))
            prev_rate, prev_na = close, na_close
    return out


def annual_cta(cta_rows: list[dict]) -> dict[int, float]:
    """Layer-1 CTA movement by fiscal year, USD millions."""
    out: dict[int, float] = defaultdict(float)
    for r in cta_rows:
        out[r["period_key"] // 100] += r["cta_movement_usd_m"]
    return dict(out)


def annual_cta_for(cta_rows: list[dict], entity: str) -> dict[int, float]:
    """One entity's CTA movement by fiscal year, USD millions."""
    out: dict[int, float] = defaultdict(float)
    for r in cta_rows:
        if r["entity_code"] == entity:
            out[r["period_key"] // 100] += r["cta_movement_usd_m"]
    return dict(out)


def layer1_equity_target(col: str) -> float:
    """
    What the sum of the source ledgers' equity must be, derived from the approved anchors.

    Consolidation replaces each subsidiary's equity with the parent's investment in it,
    recognises the goodwill and acquired intangibles that investment bought, provides
    deferred tax on the intangibles, and eliminates the unrealised profit sitting in
    intercompany inventory.  Reverse those four and the consolidated equity becomes the
    layer-1 equity:

        layer-1 equity = consolidated total equity
                       + investment in subsidiaries at cost
                       - goodwill
                       - acquired intangibles, net
                       + deferred tax on the purchase price allocation
                       + unrealised intercompany profit in inventory

    This is the line the Phase 2.1 bridge was missing.  Without it the layer-1 balance
    sheet had one unconstrained degree of freedom and the generator closed it with a plug.
    """
    bs = load_anchor("balance_sheet")
    ic = load_ic_anchor()
    year = 2026 if col.startswith("FY2026") else int(col[2:6])
    investments = sum(investments_at(dt.date(year, 12, 31)).values())
    return (bs["total_equity"][col] + investments - bs["goodwill"][col]
            - bs["intangibles_net"][col] + bs["dtl"][col]
            + ic["pup_in_inventory"][col])


def equity_bridge(sb, rows, cta_rows: list[dict]) -> list[dict]:
    """
    Year by year: the layer-1 equity roll-forward, and its agreement with the anchors.

    `unexplained_usd_m` is the control.  It is zero because every line is an actual
    transaction or the computed translation adjustment -- there is no reserve, no residual
    and no balancing account.
    """
    annual = annual_cta(cta_rows)
    by_period: dict[int, list] = defaultdict(list)
    for em in rows:
        by_period[em.period_key].append(em)
    opening = sb.opening_bs_usd()
    prev = -sum(v for e in opening for a, v in opening[e].items() if a.startswith("3"))

    # equity an entity brings with it on the date it joins the group
    acquired_equity: dict[int, float] = defaultdict(float)
    for code, e in sb.ent.items():
        if code in opening or e.entity_type != "OPERATING":
            continue
        book = sb.acquisition_opening_usd(code)
        acquired_equity[e.effective_from.year] += -sum(
            v for a, v in book.items() if a.startswith("3"))

    out: list[dict] = []
    for year, col in ((2023, "FY2023A"), (2024, "FY2024A"), (2025, "FY2025A")):
        pk = year * 100 + 12
        closing = sum(-sum(em.bs_close.get(a, 0.0) for a in EQUITY_ACCOUNTS)
                      * sb.m.rate(em.currency, pk, "CLOSE", _rate_set(pk)) / 1e6
                      for em in by_period[pk])
        result = sum(-sum(em.pl.values())
                     * sb.m.rate(em.currency, em.period_key, "AVG",
                                 _rate_set(em.period_key)) / 1e6
                     for em in rows if em.period_key // 100 == year)
        sbc = sum(em.pl.get("610500", 0.0)
                  * sb.m.rate(em.currency, em.period_key, "AVG",
                              _rate_set(em.period_key)) / 1e6
                  for em in rows if em.period_key // 100 == year)
        contributed = 0.0
        distributed = 0.0
        for code in sb.ent:
            for acct, dated in sb.equity_events(code).items():
                for event_pk, amount in dated:
                    if event_pk // 100 != year:
                        continue
                    rs = _rate_set(event_pk)
                    rate = sb.m.rate(sb.ent[code].currency, event_pk,
                                     "AVG" if acct == "320300" else "CLOSE", rs)
                    if acct == "320300":
                        distributed += amount * rate / 1e6
                    else:
                        contributed += -amount * rate / 1e6
        cta = annual.get(year, 0.0)
        acq = acquired_equity.get(year, 0.0)
        rolled = prev + result + sbc + contributed + acq - distributed + cta
        target = layer1_equity_target(col)
        out.append(dict(
            fiscal_year=year,
            opening_equity_usd_m=round(prev, 6),
            result_for_the_year_usd_m=round(result, 6),
            share_based_compensation_usd_m=round(sbc, 6),
            capital_contributed_usd_m=round(contributed, 6),
            equity_acquired_usd_m=round(acq, 6),
            distributions_usd_m=round(-distributed, 6),
            cta_movement_usd_m=round(cta, 6),
            closing_equity_rolled_usd_m=round(rolled, 6),
            closing_equity_generated_usd_m=round(closing, 6),
            unexplained_usd_m=round(closing - rolled, 6),
            anchor_layer1_equity_target_usd_m=round(target, 6),
            variance_vs_anchor_usd_m=round(closing - target, 6)))
        prev = closing
    return out


def group_cta_expectation(sb, rows, cta_rows: list[dict]) -> list[dict]:
    """
    The bridge from the layer-1 CTA to the anchored consolidated CTA roll-forward.

    `derivation_variance_usd_m` is nil when the anchored CTA has been derived from this
    calculation, which is what `P2-FX-02` proves.  It is the statement that supersedes the
    provisional Phase 1 CTA target.
    """
    annual = annual_cta(cta_rows)
    nci = annual_cta_for(cta_rows, "NIG-510")
    anchor = load_anchor("cta_rollforward")
    ic = load_ic_anchor()
    nci_share = sb.ent["NIG-510"].nci
    prev_pup = 0.50                        # the FY2022 opening unrealised profit
    out = []
    for year, col in ((2023, "FY2023A"), (2024, "FY2024A"), (2025, "FY2025A")):
        layer1 = annual.get(year, 0.0)
        minority = nci.get(year, 0.0) * nci_share
        pup = ic["pup_in_inventory"][col]
        fx_gw = anchor["fx_on_goodwill"][col]
        fx_int = anchor["fx_on_intangibles"][col]
        derived = layer1 + fx_gw + fx_int - minority - (pup - prev_pup)
        out.append(dict(
            fiscal_year=year,
            layer1_cta_movement_usd_m=round(layer1, 6),
            fx_on_goodwill_usd_m=round(fx_gw, 6),
            fx_on_intangibles_usd_m=round(fx_int, 6),
            nci_share_of_cta_usd_m=round(minority, 6),
            movement_in_unrealised_profit_usd_m=round(pup - prev_pup, 6),
            derived_group_cta_movement_usd_m=round(derived, 6),
            anchored_group_cta_movement_usd_m=round(anchor["cta_movement_group"][col], 6),
            derivation_variance_usd_m=round(
                derived - anchor["cta_movement_group"][col], 6),
            anchored_cta_closing_usd_m=round(anchor["cta_closing"][col], 6)))
        prev_pup = pup
    return out


def write_reference(sb, rows) -> dict[str, int]:
    cta_rows = cta_by_period(sb, rows)
    write_csv(REFERENCE / "cta_expectation.csv", list(cta_rows[0]),
              [list(r.values()) for r in cta_rows])
    bridge = equity_bridge(sb, rows, cta_rows)
    write_csv(REFERENCE / "layer1_equity_bridge.csv", list(bridge[0]),
              [list(r.values()) for r in bridge])
    group = group_cta_expectation(sb, rows, cta_rows)
    write_csv(REFERENCE / "cta_group_bridge.csv", list(group[0]),
              [list(r.values()) for r in group])
    return {"cta_expectation": len(cta_rows), "layer1_equity_bridge": len(bridge),
            "cta_group_bridge": len(group)}
