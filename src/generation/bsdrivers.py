"""
Driver-based monthly balance sheet paths.

Phase 2.0 interpolated interim balances between anchored year ends, which produced
month-on-month movement that was visibly a straight line.  This module replaces that with
paths generated from the economics that actually move each balance:

    receivables    an ageing profile over recent revenue, from the entity's DSO
    inventory      opening + purchases - cost of sales, with a seasonal build ahead of demand
    payables       an ageing profile over recent purchases and cash expenses, from DPO
    accrued pay    the unpaid portion of the month's payroll, on a real payday calendar
    accrued bonus  accretes monthly, paid out in March -- a sawtooth, not a line
    accrued int.   accretes monthly, paid quarterly -- a sawtooth
    tax payable    accretes monthly, paid quarterly
    prepaid        annual policies paid at renewal and amortised -- a sawtooth
    PP&E           opening + lumpy capital additions - depreciation
    debt           an instrument schedule: scheduled amortisation, drawdowns on their
                   actual dates, voluntary prepayment at year end
    revolver       drawn to the group's own liquidity need and repaid out of collections,
                   so the group never runs a negative bank balance

Each path is then scaled by a single factor per year so that **December lands exactly on
the anchored year-end balance**.  The factor is close to 1.0 and is blended across the
year, so the anchor is preserved without flattening the shape.
"""

from __future__ import annotations

import math

import numpy as np

from .common import Period, rng

#: December must not sit at a trough of its own driver path, or scaling the path onto the
#: anchored year-end balance would distort every other month.
MIN_YEAR_END_SHARE = 0.20

#: Accounts whose interim months come from an economic driver rather than a straight line.
DRIVEN_CAPTIONS = {
    "120100", "120200",                             # receivables and allowance
    "130100", "130200", "130300",                   # inventory
    "210100", "210200",                             # payables and goods received
    "215100", "215200", "216100", "218100",         # payroll, bonus, interest, tax
    "140100",                                       # prepaid
    "150200", "150300", "150400", "150500", "150600", "155100",   # PP&E
    "230100", "220200",                             # term loan and revolver
    "178100",                                       # investment in subsidiaries
}

#: The subset the linearity control tests.  Accumulated depreciation and scheduled term
#: debt amortisation are genuinely close to linear -- a stable asset base depreciated on a
#: straight-line basis produces a near-constant monthly charge, and a term loan amortises
#: on a fixed schedule -- so demanding curvature of them would be demanding noise.  The
#: captions below are the ones whose interpolation was the Phase 2.0 defect: they are moved
#: by collections, purchasing, payroll and payment calendars, none of which run in a line.
NONLINEAR_CAPTIONS = {
    "120100", "120200", "130100", "130200", "130300", "210100", "210200",
    "215100", "215200", "216100", "218100", "140100",
}

# Payment-behaviour profiles: the share of a month's billing still unpaid after k months.
# Derived from the entity's days ratio, so a slow-collecting entity has a longer tail.
def ageing_profile(days: float, tail: int = 4) -> np.ndarray:
    """Share of a month's billing still outstanding at the end of month, month+1, ..."""
    months = days / 30.44
    w = []
    remaining = 1.0
    for k in range(tail):
        # each month settles a share such that the weighted average life equals `months`
        collected = float(np.clip(1.0 / max(months - k + 0.5, 0.6), 0.0, 1.0))
        w.append(remaining * (1.0 - collected) if k else remaining * 0.62)
        remaining = w[-1]
    out = np.array([1.0] + w[:-1]) if tail > 1 else np.array([1.0])
    # normalise so that sum(w) months of billing outstanding == days/30.44
    scale = months / max(out.sum(), 1e-9)
    return np.clip(out * scale, 0.0, 1.0)


def ageing_balance(flow: np.ndarray, prior: np.ndarray, profile: np.ndarray) -> np.ndarray:
    """Outstanding balance each month given a monthly flow and an ageing profile."""
    series = np.concatenate([prior, flow])
    n0 = len(prior)
    out = np.zeros(len(flow))
    for i in range(len(flow)):
        acc = 0.0
        for k, w in enumerate(profile):
            j = n0 + i - k
            if j >= 0:
                acc += series[j] * w
        out[i] = acc
    return out


def inventory_path(opening: float, cogs: np.ndarray, periods: list[Period],
                   g: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """
    Opening + purchases - cost of sales.

    Purchases lead consumption: stock is built ahead of the seasonal peak and drawn down
    through it, which is what gives inventory its characteristic saw shape rather than a
    smooth ramp.
    """
    n = len(cogs)
    lead = np.roll(cogs, -2)
    lead[-2:] = cogs[-2:]
    build = 1.0 + 0.16 * (lead / max(cogs.mean(), 1e-9) - 1.0)
    purchases = cogs * build * (1.0 + 0.05 * g.normal(size=n))
    bal = np.empty(n)
    prev = opening
    for i in range(n):
        prev = prev + purchases[i] - cogs[i]
        bal[i] = prev
    return bal, purchases


def sawtooth_accrual(monthly_charge: np.ndarray, periods: list[Period],
                     pay_months: set[int], opening: float = 0.0) -> np.ndarray:
    """Accretes each month and is settled in the payment months. A real sawtooth."""
    bal = np.empty(len(monthly_charge))
    acc = opening
    for i, p in enumerate(periods):
        acc += monthly_charge[i]
        if p.month in pay_months:
            acc *= 0.06                  # a small residual always remains outstanding
        bal[i] = acc
    return bal


def payroll_accrual(monthly_payroll: np.ndarray, periods: list[Period]) -> np.ndarray:
    """
    The unpaid portion of payroll at month end.

    Pay runs land on the 15th and the last working day. How much sits unpaid at a month
    end depends on where those dates fall relative to the period end, so the balance moves
    between roughly a third and two thirds of a month's payroll rather than sitting flat.
    """
    out = np.empty(len(monthly_payroll))
    for i, p in enumerate(periods):
        last_dow = p.end.weekday()
        # a period ending on a Friday clears more than one ending on a Sunday
        clear = 0.62 if last_dow <= 4 else 0.38
        seasonal = 1.0 + 0.05 * np.cos(2 * np.pi * (p.month - 1) / 12.0)
        out[i] = monthly_payroll[i] * (1.0 - clear) * seasonal + monthly_payroll[i] * 0.30
    return out


#: Annual contracts renew on their own anniversaries, not all at once: property and
#: liability insurance in January, software subscriptions in April, maintenance and support
#: in July, and licences and memberships in October.  The share of annual prepaid spend
#: each renewal carries is what gives the balance its shape.
PREPAID_RENEWALS = {1: 0.40, 4: 0.20, 7: 0.25, 10: 0.15}


def prepaid_path(monthly_charge: np.ndarray, periods: list[Period],
                 renewals: dict[int, float] | None = None) -> np.ndarray:
    """
    Annual contracts paid up front at renewal and amortised over the following year.

    Each renewal creates a distinct unexpired layer that releases a twelfth of itself a
    month, so the balance steps up on each anniversary and declines in between.  That is
    what makes prepayments a sawtooth rather than a level, and staggering the anniversaries
    means the balance never collapses to nothing at the year end.
    """
    renewals = PREPAID_RENEWALS if renewals is None else renewals
    n = len(periods)
    bal = np.empty(n)
    layers: list[list[float]] = []          # [remaining, monthly release]
    for i, p in enumerate(periods):
        share = renewals.get(p.month)
        if share:
            # the premium covers twelve months from renewal
            premium = monthly_charge[i] * 12.0 * share
            layers.append([premium, premium / 12.0])
        for layer in layers:
            layer[0] -= min(layer[1], layer[0])
        layers = [x for x in layers if x[0] > 1e-6]
        bal[i] = sum(x[0] for x in layers)
    return bal


def ppe_path(opening_gross: float, opening_accum: float, capex: np.ndarray,
             depreciation: np.ndarray, g: np.random.Generator
             ) -> tuple[np.ndarray, np.ndarray]:
    """
    Gross cost and accumulated depreciation, month by month.

    Capital spend is lumpy: projects complete in particular months rather than one twelfth
    landing every month, so gross cost steps rather than ramps.
    """
    n = len(capex)
    lump = g.lognormal(0.0, 0.85, size=n)
    lump = lump / lump.sum() * capex.sum()
    gross = np.empty(n)
    accum = np.empty(n)
    gb, ab = opening_gross, opening_accum
    for i in range(n):
        gb += lump[i]
        ab -= depreciation[i]
        gross[i], accum[i] = gb, ab
    return gross, accum


def debt_path(opening: float, closing: float, periods: list[Period],
              scheduled_quarterly: float, draw_month: int | None,
              draw_amount: float) -> np.ndarray:
    """
    An instrument schedule rather than a straight line.

    Scheduled amortisation falls on quarter ends, any drawdown lands in its actual month,
    and the balancing voluntary prepayment is made in December when the cash is known.
    """
    n = len(periods)
    bal = np.empty(n)
    b = opening
    scheduled_total = 0.0
    for i, p in enumerate(periods):
        if p.month % 3 == 0:
            b -= scheduled_quarterly
            scheduled_total += scheduled_quarterly
        if draw_month and p.month == draw_month:
            b += draw_amount
        bal[i] = b
    # the residual movement is a voluntary prepayment (or drawdown) at the year end
    residual = closing - bal[-1]
    bal[-1] += residual
    if n >= 2 and abs(residual) > 1e-9:
        bal[-2] += residual * 0.35        # partially anticipated in November
    return bal


def apply_year_end_anchor(path: np.ndarray, target: float,
                          prev_factor: float | None = None) -> tuple[np.ndarray, float]:
    """
    Scale a driver-generated path so December lands exactly on the anchored balance.

    The drivers produce a magnitude -- days of sales outstanding, months of stock on hand,
    an unpaid share of payroll -- so a path is first oriented to the sign of the caption it
    represents.  Without that a credit caption such as payables receives a negative scaling
    factor and, blended against the prior year, crosses zero mid-year: a payables balance
    that starts the year as a debit.

    The factor is then blended from the prior year's factor across the twelve months, so
    the anchor is imposed without introducing a step at the year boundary or flattening
    the shape the drivers produced.  In an account's first year there is no prior factor
    and the scaling is constant, because a ramp from an arbitrary 1.0 would distort the
    opening months.
    """
    n = len(path)
    if n == 0 or abs(path[-1]) < 1e-9:
        return path, prev_factor if prev_factor is not None else 1.0
    if target != 0.0 and (path[-1] > 0) != (target > 0):
        path = -path                      # orient the magnitude to the caption's sign
    # Drivers supply the shape and the anchor supplies the level, so a uniform difference
    # in level is exactly what the scaling factor is for.  What scaling cannot fix is a
    # path whose December point sits at a trough -- an accrual settled on the balance sheet
    # date, or a prepayment whose every policy expires in December.  Landing that on the
    # anchor would inflate the other eleven months to an absurd balance, so it is a
    # modelling error in the driver and the build fails rather than hiding it.
    mean_mag = float(np.mean(np.abs(path)))
    if mean_mag > 0 and abs(path[-1]) < MIN_YEAR_END_SHARE * mean_mag:
        raise ValueError(
            f"the driver path ends at {path[-1]:,.0f}, only "
            f"{abs(path[-1]) / mean_mag:.1%} of its own average magnitude "
            f"{mean_mag:,.0f}. December sits at a trough, so scaling it onto the target of "
            f"{target:,.0f} would distort the rest of the year. Fix the driver's payment "
            f"or renewal calendar instead.")
    factor = target / path[-1]
    if prev_factor is None or (prev_factor > 0) != (factor > 0):
        ramp = np.full(n, factor)
    else:
        ramp = prev_factor + (factor - prev_factor) * (np.arange(1, n + 1) / n)
    out = path * ramp
    out[-1] = target
    return out, factor


def linearity(series: np.ndarray) -> float:
    """
    0.0 = a perfect straight line between the endpoints, 1.0 = strongly non-linear.

    Used by control `P2-BR-04` to prove interim balances are driver-generated rather than
    interpolated. Measured as the largest deviation from the straight line joining the
    endpoints, as a share of the series range.
    """
    n = len(series)
    if n < 3:
        return 1.0
    lin = np.linspace(series[0], series[-1], n)
    spread = float(np.max(series) - np.min(series))
    if spread < 1e-9:
        return 0.0
    return float(np.max(np.abs(series - lin)) / spread)


def revolver_path(pre_rcf_cash: dict[int, float], year_end_drawn: dict[int, float],
                  activity: dict[int, float], min_cash_usd: float, buffer_usd: float,
                  commitment_usd: float, draw_increment: float = 0.5e6,
                  repay_block: float = 2.5e6, min_surplus: float = 3.0e6
                  ) -> dict[int, float]:
    """
    Monthly revolving credit facility utilisation, managed against the group's own need.

    The revolver is the group's liquidity instrument, not a balance that sits still.  It is
    drawn when working capital builds or an acquisition completes and repaid out of
    collections, because utilisation costs margin while undrawn commitment costs only the
    commitment fee.  `pre_rcf_cash` is the group cash position the balanced entity ledgers
    produce with the facility undrawn, so the draw required in a month is whatever keeps
    the group above its minimum operating balance.

    Three details keep the path away from a mechanical need-tracking line.  The minimum
    balance the group targets moves with trading activity, because a busier month needs
    more cash on hand to run.  Draws are requested in round amounts, since that is how a
    borrowing notice is actually submitted.  Repayments are made in blocks and only once
    there is a worthwhile surplus, because no treasurer repays half a million and redraws
    it a month later.  The balance is therefore sticky, as a real facility is.

    December is set to the approved year-end anchor, so the entry and exit points of every
    year remain exactly the balances the anchor model proved.

    Returns drawn balances (positive) by period key.
    """
    keys = sorted(pre_rcf_cash)
    mean_act = sum(activity.values()) / max(len(activity), 1) or 1.0
    out: dict[int, float] = {}
    drawn = 0.0
    for pk in keys:
        if pk % 100 == 12 and pk // 100 in year_end_drawn:
            out[pk] = drawn = year_end_drawn[pk // 100]
            continue
        # a busier month needs more cash on hand to run
        floor = min_cash_usd * (0.85 + 0.30 * activity.get(pk, mean_act) / mean_act)
        available = pre_rcf_cash[pk] + drawn
        if available < floor:
            need = floor + buffer_usd - available
            drawn = min(drawn + math.ceil(need / draw_increment) * draw_increment,
                        commitment_usd)
        else:
            surplus = available - floor - buffer_usd
            if surplus > min_surplus and drawn > 0:   # in blocks, not in dribbles
                drawn -= min(drawn, math.floor(surplus / repay_block) * repay_block)
        out[pk] = drawn
    return out


def daily_utilisation(opening: float, closing: float, days: int,
                      draw_day: int, sweep_day: int) -> dict[str, float]:
    """
    One month of revolving facility utilisation, resolved to a daily balance.

    A month-end balance is not what a facility costs.  Interest accrues on the daily drawn
    balance, and the commitment fee on the daily undrawn commitment, so the two need an
    intra-month position rather than the two endpoints.  The credit agreement and the board
    treasury policy already fix the dates that matter (`config/debt/treasury_policy.csv`):

      * a **drawing** is taken on the borrowing-notice date early in the month, because it
        is drawn to fund the supplier payment run and the payroll disbursement.  A month
        that draws is therefore drawn for substantially the whole month.
      * a **repayment** is made on the collections sweep date late in the month, once the
        month's receipts have cleared.  A month that repays is drawn for most of the month
        and repaid only at the end.

    The balance is a step function with one step, so the average daily balance is exact
    rather than an approximation, and `opening + draws - repayments = closing` holds to the
    cent.  Returns the movement and the average daily drawn balance.
    """
    move = closing - opening
    step_day = draw_day if move > 0 else sweep_day
    step_day = max(1, min(step_day, days))
    # `step_day` is the first day on which the new balance stands
    days_at_open = step_day - 1
    days_at_close = days - days_at_open
    average = (opening * days_at_open + closing * days_at_close) / days
    return {
        "opening_drawn": opening,
        "draws": max(move, 0.0),
        "repayments": max(-move, 0.0),
        "closing_drawn": closing,
        "movement_day": step_day if move else 0,
        "days_in_month": days,
        "average_daily_drawn": average,
    }
