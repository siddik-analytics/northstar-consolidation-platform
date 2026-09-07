"""
The layer-1 translation difference.

Phase 2.0 absorbed a residual into investment-at-cost, which made investment balances
unexplainable.  Phase 2.1 removes that: investments now come straight from the investment
register, and the residual is measured, decomposed and disclosed here instead.

Where the residual comes from
-----------------------------
Every entity's ledger balances in its own functional currency, and every balance sheet
caption is pinned to the approved anchor.  Retained earnings then rolls forward from local
net income.  Those two facts over-determine the balance sheet, so a difference remains.

Translating the layer-1 population at closing rates cannot reproduce the consolidated
anchor exactly, because the anchor's equity accumulates group results at the rates ruling
when they were earned and carries the group's own cumulative translation adjustment, while
the entity ledgers accumulate locally-measured results and are translated at the closing
rate.  The difference is an equity measurement effect, not a cash effect.

It is therefore posted to a named holding-company equity reserve, 329100 Group reporting
measurement reserve, struck at each year end and carried at Topco.  Cash -- the one group
balance that is externally verifiable -- ties to the approved anchor exactly.  Phase 4
removes the reserve and replaces it with a CTA computed from the entity ledgers; it must
never be treated as a consolidation input (ADR-0004, CTL-FX-04).

This module computes the generated CTA independently, using the standard formula rather
than by reference to the gap:

    CTA movement = opening net assets x (closing rate - prior closing rate)
                 + result for the period x (closing rate - average rate)

so it can be compared against the anchored CTA roll-forward. Phase 4's translation engine
must reproduce it, and `CTL-FX-04` will test it against the same expectation.
"""

from __future__ import annotations

from collections import defaultdict

from .common import REFERENCE, load_anchor, write_csv
from .fx import _anchor_rates

EQUITY_ACCOUNTS = ("310100", "310200", "315100", "320100", "320200")


def generated_cta(sb, rows) -> dict[int, dict[str, float]]:
    """Per period: the CTA movement implied by the generated entity ledgers."""
    anchors = _anchor_rates()
    by_entity: dict[str, list] = defaultdict(list)
    for em in rows:
        by_entity[em.entity].append(em)

    per_period: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for code, months in by_entity.items():
        e = sb.ent[code]
        if e.currency == "USD":
            continue
        months = sorted(months, key=lambda x: x.period_key)
        prev_rate = None
        for em in months:
            rs = "FORECAST" if em.period_key // 100 == 2026 else "ACTUAL"
            close = sb.m.rate(e.currency, em.period_key, "CLOSE", rs)
            avg = sb.m.rate(e.currency, em.period_key, "AVG", rs)
            if prev_rate is None:
                pk = e.effective_from.year * 100 + e.effective_from.month
                prev_rate = (anchors[(e.currency, 2022, "ACTUAL")][1]
                             if pk < 202301 else close)
            net_assets_open = -sum(em.bs_open.get(a, 0.0) for a in EQUITY_ACCOUNTS)
            result = -sum(em.pl.values())
            on_net_assets = net_assets_open * (close - prev_rate)
            on_result = result * (close - avg)
            per_period[em.period_key][code] = (on_net_assets + on_result) / 1e6
            per_period[em.period_key]["_on_net_assets"] += on_net_assets / 1e6
            per_period[em.period_key]["_on_result"] += on_result / 1e6
            prev_rate = close
    return per_period


def build_report(sb, rows) -> list[dict]:
    """Year-by-year: generated CTA, anchored CTA, and the residual carried in cash."""
    cta = generated_cta(sb, rows)
    anchor_cta = load_anchor("cta_rollforward")
    bs = load_anchor("balance_sheet")
    out: list[dict] = []
    cum = 0.0
    for year, col in ((2023, "FY2023A"), (2024, "FY2024A"), (2025, "FY2025A")):
        move = sum(v for pk, d in cta.items() if pk // 100 == year
                   for k, v in d.items() if not k.startswith("_"))
        on_na = sum(d["_on_net_assets"] for pk, d in cta.items() if pk // 100 == year)
        on_res = sum(d["_on_result"] for pk, d in cta.items() if pk // 100 == year)
        cum += move
        pk = year * 100 + 12
        rs = "ACTUAL"
        cash = sum(em.bs_close["110100"]
                   * sb.m.rate(em.currency, pk, "CLOSE", rs) / 1e6
                   for em in rows if em.period_key == pk)
        assets = sum(v * sb.m.rate(em.currency, pk, "CLOSE", rs) / 1e6
                     for em in rows if em.period_key == pk
                     for a, v in em.bs_close.items() if a.startswith("1"))
        anchor_cash = bs["cash"][col]
        gap = cash - anchor_cash
        reserve = -sum(em.bs_close.get("329100", 0.0)
                       * sb.m.rate(em.currency, pk, "CLOSE", rs) / 1e6
                       for em in rows if em.period_key == pk)
        out.append(dict(
            fiscal_year=year,
            generated_cta_movement=round(move, 4),
            generated_cta_on_net_assets=round(on_na, 4),
            generated_cta_on_result=round(on_res, 4),
            generated_cta_cumulative=round(cum, 4),
            anchor_cta_cumulative=round(anchor_cta["cta_closing"][col], 4),
            cta_variance_vs_anchor=round(cum - anchor_cta["cta_closing"][col], 4),
            layer1_cash=round(cash, 4),
            anchor_cash=round(anchor_cash, 4),
            cash_variance_vs_anchor=round(gap, 4),
            measurement_reserve_closing=round(reserve, 4),
            layer1_total_assets=round(assets, 4),
            reserve_pct_of_total_assets=round(abs(reserve) / assets * 100, 4)))
    return out


def write_reference(sb, rows) -> int:
    report = build_report(sb, rows)
    write_csv(REFERENCE / "translation_difference.csv", list(report[0]),
              [list(r.values()) for r in report])
    return len(report)
