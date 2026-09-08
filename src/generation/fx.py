"""
Monthly FX rate series for USD, CAD, GBP and EUR.

Phase 2 produces *source and reference* rates only. No translation is performed here --
that is Phase 4 (ADR-0005).

Construction
------------
Rates are built as a seeded random walk between the anchored year-end closing rates, so
the path has economic shape rather than being noise around a mean.  Two constraints are
then imposed exactly:

  1. December's closing spot equals the annual closing anchor.
  2. The mean of the twelve monthly average rates equals the annual average anchor.

Quotation is USD per one unit of foreign currency throughout (FX-P15), so translation is
always a multiplication and an inverted pair is detectable by range (CTL-FX-05).
"""

from __future__ import annotations

from datetime import date as _date

import numpy as np

from .common import (ACTUAL_PERIODS, CONFIG, PLAN_YEAR, Period, REFERENCE, read_csv,
                     rng, write_csv, plan_periods)

CURRENCIES = ["USD", "CAD", "GBP", "EUR"]
RATE_SETS = ["ACTUAL", "BUDGET", "FORECAST"]

# Volatility of the monthly walk, by currency (annualised, roughly realistic)
MONTHLY_VOL = {"CAD": 0.016, "GBP": 0.021, "EUR": 0.022, "USD": 0.0}

PLAUSIBLE = {"USD": (1.0, 1.0), "CAD": (0.60, 0.90), "GBP": (1.00, 1.60), "EUR": (0.90, 1.35)}


def _anchor_rates() -> dict[tuple[str, int, str], tuple[float, float]]:
    out = {}
    for r in read_csv(CONFIG / "anchors" / "anchor_fx_rates.csv"):
        out[(r["currency_code"], int(r["fiscal_year"]), r["rate_set"])] = (
            float(r["average_rate_usd"]), float(r["closing_rate_usd"]))
    return out


def _year_path(ccy: str, year: int, open_spot: float, close_spot: float,
               avg_target: float, seed_tag: str) -> tuple[np.ndarray, np.ndarray]:
    """
    Twelve month-end spots and twelve monthly averages for one currency-year.

    A Brownian bridge between the opening and closing spot gives a path that wanders
    rather than sliding linearly; the monthly average is the mean of the month's opening
    and closing spot plus a small intra-month excursion.  The averages are then shifted
    onto the anchor by an affine correction so the anchor holds exactly.
    """
    if ccy == "USD":
        return np.ones(12), np.ones(12)

    g = rng("fx", ccy, year, seed_tag)
    vol = MONTHLY_VOL[ccy]

    steps = g.normal(scale=vol, size=12)
    walk = np.cumsum(steps)
    # Brownian bridge: force the endpoint onto the closing anchor
    walk = walk - np.linspace(0, 1, 12) * walk[-1]
    drift = np.linspace(open_spot, close_spot, 12)
    spots = drift * (1.0 + walk)
    spots[-1] = close_spot

    prev = np.concatenate(([open_spot], spots[:-1]))
    intra = 1.0 + g.normal(scale=vol * 0.35, size=12)
    avgs = (prev + spots) / 2.0 * intra

    # Impose the annual average anchor exactly, preserving the shape of the deviations
    avgs = avgs * (avg_target / avgs.mean())
    return spots, avgs


def build_rate_series() -> list[dict]:
    """One row per currency x period x rate type x rate set."""
    anchors = _anchor_rates()
    rows: list[dict] = []

    years = sorted({p.year for p in ACTUAL_PERIODS})
    for ccy in CURRENCIES:
        # ---- ACTUAL -------------------------------------------------------
        open_spot = anchors[(ccy, 2022, "ACTUAL")][1]
        for year in years:
            key = (ccy, year, "ACTUAL")
            if key not in anchors:
                # FY2026 has no ACTUAL anchor row; actual months to date follow the
                # forecast rate set, which is how a live year genuinely behaves.
                key = (ccy, year, "FORECAST")
            avg_t, close_t = anchors[key]
            spots, avgs = _year_path(ccy, year, open_spot, close_t, avg_t, "actual")
            for m in range(1, 13):
                p_key = year * 100 + m
                if not any(p.period_key == p_key for p in ACTUAL_PERIODS):
                    continue
                rows.append(dict(currency_code=ccy, period_key=p_key, rate_set="ACTUAL",
                                 rate_type="AVG", rate_usd_per_unit=round(avgs[m - 1], 8)))
                rows.append(dict(currency_code=ccy, period_key=p_key, rate_set="ACTUAL",
                                 rate_type="CLOSE", rate_usd_per_unit=round(spots[m - 1], 8)))
            open_spot = close_t

        # ---- BUDGET: locked flat at the approved budget rate (FX-P09) ------
        b_avg, b_close = anchors[(ccy, PLAN_YEAR, "BUDGET")]
        for p in plan_periods():
            rows.append(dict(currency_code=ccy, period_key=p.period_key, rate_set="BUDGET",
                             rate_type="AVG", rate_usd_per_unit=round(b_avg, 8)))
            rows.append(dict(currency_code=ccy, period_key=p.period_key, rate_set="BUDGET",
                             rate_type="CLOSE", rate_usd_per_unit=round(b_close, 8)))

        # ---- FORECAST: actuals for closed months, forwards thereafter ------
        f_avg, f_close = anchors[(ccy, PLAN_YEAR, "FORECAST")]
        open_spot_f = anchors[(ccy, PLAN_YEAR - 1, "ACTUAL")][1]
        spots_f, avgs_f = _year_path(ccy, PLAN_YEAR, open_spot_f, f_close, f_avg, "actual")
        for p in plan_periods():
            rows.append(dict(currency_code=ccy, period_key=p.period_key, rate_set="FORECAST",
                             rate_type="AVG", rate_usd_per_unit=round(avgs_f[p.month - 1], 8)))
            rows.append(dict(currency_code=ccy, period_key=p.period_key, rate_set="FORECAST",
                             rate_type="CLOSE", rate_usd_per_unit=round(spots_f[p.month - 1], 8)))

    return rows


def rate_lookup(rows: list[dict]) -> dict[tuple[str, int, str, str], float]:
    return {(r["currency_code"], r["period_key"], r["rate_type"], r["rate_set"]):
            r["rate_usd_per_unit"] for r in rows}


#: The first day of the modelled window. An entity consolidated on or before it opens from
#: the FY2022 closing balance sheet; one consolidated after it opens from its own
#: acquisition-date balance sheet. `series.opening_bs_usd()` applies the same test when it
#: converts opening balances into local currency, and the two must agree or the translation
#: base is stated at a different rate from the balance it is the base for (P3-D-05).
WINDOW_OPENS = _date(2023, 1, 1)


def historical_rates(entities) -> list[dict]:
    """
    Entity- and event-specific historical rates for equity translation (FX-P03/FX-P16).

    An acquired entity's opening balance sheet is frozen at the spot rate on its
    consolidation effective date; contributed capital is frozen at the rate on the date
    it was contributed.
    """
    series = rate_lookup(build_rate_series())
    out = []
    for e in entities.values():
        eff = e.effective_from
        pk = eff.year * 100 + eff.month
        # Which rate an entity's opening balance sheet is stated at depends on WHEN that
        # balance sheet is, and there are only two cases.
        #
        # An entity already in the group when the modelled window opens has its opening
        # balance sheet at 31 December 2022, so its base is the FY2022 closing anchor. That
        # includes an entity whose consolidation begins on 1 January 2023: the opening
        # position it brings in is the FY2022 closing position, and `opening_bs_usd()`
        # converts its opening balances into local currency at exactly that anchor. The
        # test was `pk < 202301`, which put such an entity in the wrong branch and
        # registered the JANUARY 2023 closing rate as the base for a balance sheet stated
        # at the DECEMBER 2022 one -- so the two halves of the generator disagreed with
        # each other about the same opening balance sheet, and the translation base was
        # 2.1% out for the whole of the entity's life (defect P3-D-05).
        #
        # An entity acquired inside the window has its opening balance sheet at the
        # acquisition date, and `_build_actuals` converts it at that month's closing rate,
        # so the base is that month's close.
        if eff <= WINDOW_OPENS:
            rate = _anchor_rates()[(e.currency, 2022, "ACTUAL")][1]
            basis = "FY2022 closing anchor"
        else:
            rate = series[(e.currency, pk, "CLOSE", "ACTUAL")]
            basis = f"closing spot {pk}"
        for acct, label in [("310100", "Share capital"), ("310200", "Additional paid-in capital")]:
            out.append(dict(entity_code=e.code, group_account=acct, event_type="CAPITAL_CONTRIBUTION",
                            event_date=eff.isoformat(), currency_code=e.currency,
                            rate_usd_per_unit=round(rate, 8), basis=basis, note=label))
        if e.acquisition_date and e.effective_from >= eff:
            out.append(dict(entity_code=e.code, group_account="ACQ_OPENING_BS",
                            event_type="ACQUISITION_DATE", event_date=eff.isoformat(),
                            currency_code=e.currency, rate_usd_per_unit=round(rate, 8),
                            basis=basis, note="Opening balance sheet translation base (FX-P16)"))
    return out


def write_reference(entities) -> dict[str, int]:
    rows = build_rate_series()
    write_csv(REFERENCE / "fx_rates_monthly.csv",
              ["currency_code", "period_key", "rate_set", "rate_type", "rate_usd_per_unit",
               "base_currency", "quote_convention", "source", "effective_month"],
              [[r["currency_code"], r["period_key"], r["rate_set"], r["rate_type"],
                f"{r['rate_usd_per_unit']:.8f}", "USD", "USD per 1 unit of foreign currency",
                "Northstar Treasury rate file", f"{r['period_key'] // 100}-{r['period_key'] % 100:02d}"]
               for r in rows])

    hist = historical_rates(entities)
    write_csv(REFERENCE / "fx_rates_historical.csv",
              ["entity_code", "group_account", "event_type", "event_date", "currency_code",
               "rate_usd_per_unit", "basis", "note"],
              [[h["entity_code"], h["group_account"], h["event_type"], h["event_date"],
                h["currency_code"], f"{h['rate_usd_per_unit']:.8f}", h["basis"], h["note"]]
               for h in hist])
    return {"fx_rates_monthly": len(rows), "fx_rates_historical": len(hist)}
