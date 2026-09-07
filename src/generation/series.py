"""
Monthly entity ledger positions in functional currency.

Annual anchors are phased into months with genuine seasonality; year-end balances are the
allocated anchor targets and interim months are interpolated and modulated by the entity's
own activity.  Retained earnings roll forward from net income; cash is never targeted --
it is whatever the balanced journals leave behind.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .common import (ACTUAL_PERIODS, Period, allocate_exact, build_periods,
                     plan_periods, rng, seasonal_shape)
from . import bsdrivers as bd
from .ledger import (CAPTION_SPLIT, ENTITY_CAPITAL, KESTREL_ENTITIES, split_for,
                     LedgerBuilder, PPE_CLASSES)
from .investments import investments_at
from .model import DPO_TILT, DSO_TILT, EconomicModel

# Minimum operating liquidity the group holds at any month end, and the headroom it keeps
# above that when it goes to the facility.  A borrowing request is not made for the exact
# shortfall; it is made for the shortfall plus a working buffer.
MIN_GROUP_CASH_USD = 8_000_000.0
CASH_BUFFER_USD = 4_000_000.0

# Facility size from the credit agreement, mirrored in the anchor model.
RCF_COMMITMENT_USD = 60_000_000.0

OPENING_PERIOD = 202212          # the 2022 opening balance sheet date
PL_PREFIXES = ("4", "5", "6", "7", "8")

# Opening (2022-12-31) layer-1 group balance sheet, USD millions, from the anchor opening
# balance sheet with the Phase 4 items removed and intercompany positions added.
# NIG-510 was acquired on 31 December 2022 and consolidated from 1 January 2023, so its
# balance sheet -- and the group's opening non-controlling interest -- are already here.
OPENING_BRIDGE_REMOVE = ("goodwill", "intangibles_net", "dtl", "retained_earnings",
                         "contributed_capital", "cta", "nci", "tlb_gross", "dff")

STREAM_OF_PREFIX = {"4": "revenue", "5": "cos", "6": "opex", "7": "other", "8": "tax"}


@dataclass
class EntityMonth:
    entity: str
    period_key: int
    currency: str
    pl: dict[str, float] = field(default_factory=dict)        # local, debit-positive
    bs_open: dict[str, float] = field(default_factory=dict)   # local, debit-positive
    bs_close: dict[str, float] = field(default_factory=dict)
    context: dict[str, float] = field(default_factory=dict)


class SeriesBuilder:
    def __init__(self, lb: LedgerBuilder | None = None):
        self.lb = lb or LedgerBuilder()
        self.m = self.lb.m
        self.ent = self.m.entities
        self._ic_cache: dict = {}
        self._bs_factor_carry: dict[str, dict[str, float]] = {}
        self.ic_legs: dict[tuple[str, int], list[tuple]] = {}

    # ------------------------------------------------------------------ opening
    def opening_bs_usd(self) -> dict[str, dict[str, float]]:
        """
        Entity opening balance sheets at 2022-12-31, USD millions, debit-positive.

        Each anchor caption is allocated to entities by an FY2023 driver and then split
        across its source accounts using the caption split, which nets to the caption --
        so contra accounts (allowances, accumulated depreciation) cannot distort the net.
        Retained earnings is the entity-level plug, so every opening trial balance is
        exactly zero.
        """
        import datetime as _dt
        ob = self.m.opening
        col = "FY2023A"
        live = [e for e in self.ent
                if self.ent[e].effective_from <= _dt.date(2023, 1, 1)]
        out: dict[str, dict[str, float]] = {e: {} for e in live}
        y1 = self.lb.year_end_bs_usd(col)

        def net(e: str, accts: list[str]) -> float:
            return sum(y1.get(e, {}).get(a, 0.0) for a in accts)

        # caption -> (source account split netting to 1.0, sign, weight accounts)
        plan = {
            "ar":                  (CAPTION_SPLIT["ar"], 1, ["120100", "120200"]),
            "contract_assets":     (CAPTION_SPLIT["contract_assets"], 1, ["121100"]),
            "inventory":           (CAPTION_SPLIT["inventory"], 1,
                                    ["130100", "130200", "130300", "130400"]),
            "prepaid":             (CAPTION_SPLIT["prepaid"], 1, ["140100"]),
            "other_nca":           (CAPTION_SPLIT["other_nca"], 1, ["180100"]),
            "ap":                  (CAPTION_SPLIT["ap"], -1, ["210100", "210200"]),
            "contract_liabilities":(CAPTION_SPLIT["contract_liabilities"], -1, ["211100"]),
            "accrued":             (CAPTION_SPLIT["accrued"], -1,
                                    ["215100", "215200", "215300", "215400", "215500",
                                     "215600", "216100", "219100"]),
            "tax_payable":         (CAPTION_SPLIT["tax_payable"], -1, ["218100"]),
            "other_ltl":           (CAPTION_SPLIT["other_ltl"], -1, ["245100"]),
        }
        pup_open = 0.50
        for caption, (split, sign, wacc) in plan.items():
            target = ob.get(caption, 0.0) + (pup_open if caption == "inventory" else 0.0)
            members = [e for e in live if abs(net(e, wacc)) > 1e-9]
            if not members:
                continue
            amounts = allocate_exact(target, np.array([abs(net(e, wacc)) for e in members]), 6)
            for e, amt in zip(members, amounts):
                for a, share in split_for(e, split).items():
                    out[e][a] = out[e].get(a, 0.0) + sign * amt * share

        # Property, plant and equipment: allocate the NET, then gross up consistently
        ppe_accts = ["150200", "150300", "150400", "150500", "150600", "155100"]
        members = [e for e in live if abs(net(e, ppe_accts)) > 1e-9]
        for e, amt in zip(members, allocate_exact(ob["ppe_net"],
                                                  np.array([abs(net(e, ppe_accts)) for e in members]), 6)):
            gross = amt / 0.62
            for a, share in PPE_CLASSES.items():
                out[e][a] = out[e].get(a, 0.0) + gross * share
            out[e]["155100"] = out[e].get("155100", 0.0) - (gross - amt)

        # Operating leases: never recognised in the Kestrel entities' local books
        nk = [e for e in live if e not in KESTREL_ENTITIES]
        rou_nk = [e for e in nk if abs(net(e, ["158100"])) > 1e-9] or nk
        w = np.array([max(abs(net(e, ["158100"])), 0.05) for e in rou_nk])
        rou_target = ob["rou_asset"] * sum(
            abs(net(e, ["158100"])) for e in nk) / max(
            sum(abs(net(e, ["158100"])) for e in live), 1e-9)
        for e, amt in zip(rou_nk, allocate_exact(rou_target, w, 6)):
            out[e]["158100"] = out[e].get("158100", 0.0) + amt
            out[e]["220400"] = out[e].get("220400", 0.0) - amt * 0.22
            out[e]["230400"] = out[e].get("230400", 0.0) - amt * 0.78

        # Finance leases
        fl_accts = ["220300", "230300"]
        members = [e for e in live if abs(net(e, fl_accts)) > 1e-9]
        for e, amt in zip(members, allocate_exact(ob["finance_lease"],
                                                  np.array([abs(net(e, fl_accts)) for e in members]), 6)):
            out[e]["220300"] = out[e].get("220300", 0.0) - amt * 0.24
            out[e]["230300"] = out[e].get("230300", 0.0) - amt * 0.76

        # Cash: allocated by activity, with Topco holding the group's surplus
        rev = self.m.entity_revenue_usd(col)
        w = np.array([rev.get(e, 0.0) + (ob["cash"] * 0.9 if e == "NIG-100" else 0.0)
                      for e in live])
        for e, amt in zip(live, allocate_exact(ob["cash"], w, 6)):
            out[e]["110100"] = out[e].get("110100", 0.0) + amt

        # External debt and facilities sit with Topco treasury
        out["NIG-100"]["230100"] = -ob["tlb_gross"]
        out["NIG-100"]["230200"] = ob["dff"]
        out["NIG-100"]["220200"] = -ob["rcf"]
        import datetime as _dt2
        for (parent, sub), amt in investments_at(_dt2.date(2022, 12, 31)).items():
            if parent in out and sub in out:
                out[parent]["178100"] = out[parent].get("178100", 0.0) + amt
        for e in live:
            cap = ENTITY_CAPITAL[e]
            out[e]["310100"] = -cap * 0.10
            out[e]["310200"] = -cap * 0.90
            out[e]["320100"] = -sum(out[e].values())        # entity plug
        return out

    def acquisition_opening_usd(self, code: str) -> dict[str, float]:
        """Opening balance sheet an acquired entity brings into the group, USD millions."""
        book = {
            "NIG-220": dict(cash=1.8, ar=5.4, inventory=4.2, contract_assets=0.3, prepaid=0.5,
                            ppe=3.4, ap=2.9, accrued=0.9),
            "NIG-410": dict(cash=1.1, ar=3.6, inventory=1.9, contract_assets=0.9, prepaid=0.3,
                            ppe=5.6, ap=1.8, contract_liabilities=0.7, accrued=0.0),
        }[code]
        out = {
            "110100": book["cash"], "120100": book["ar"] * 1.018, "120200": -book["ar"] * 0.018,
            "121100": book["contract_assets"], "140100": book["prepaid"],
            "130100": book["inventory"] * 0.34, "130200": book["inventory"] * 0.21,
            "130300": book["inventory"] * 0.48, "130400": -book["inventory"] * 0.03,
            "150300": book["ppe"] / 0.62 * 0.70, "150200": book["ppe"] / 0.62 * 0.30,
            "155100": -(book["ppe"] / 0.62 - book["ppe"]),
            "210100": -book["ap"] * 0.86, "210200": -book["ap"] * 0.14,
            "215100": -book.get("accrued", 0.0) * 0.55,
            "215600": -book.get("accrued", 0.0) * 0.45,
            "211100": -book.get("contract_liabilities", 0.0),
        }
        cap = ENTITY_CAPITAL[code]
        out["310100"] = -cap * 0.10
        out["310200"] = -cap * 0.90
        out["320100"] = -sum(out.values())
        return {k: v for k, v in out.items() if abs(v) > 1e-9}

    # ------------------------------------------------------------------ phasing
    def _pl_local_monthly(self, code: str, col: str, periods: list[Period]) -> dict[str, np.ndarray]:
        """{group_account: local monthly array}. Exact on translation at monthly avg rates."""
        annual = dict(self.lb.annual_pl_usd(col).get(code, {}))
        for a, v in self.lb.annual_interest_usd(col).get(code, {}).items():
            annual[a] = annual.get(a, 0.0) + v
        n = len(periods)
        shapes = {s: self.m.seasonality(code, col, n, s)
                  for s in ("revenue", "cos", "opex", "other", "tax")}
        wrates = {s: self.m.weighted_rate(code, col, shapes[s], periods) for s in shapes}
        out: dict[str, np.ndarray] = {}
        for acct, usd in annual.items():
            if abs(usd) < 1e-12:
                continue
            stream = STREAM_OF_PREFIX.get(acct[0], "opex")
            if acct in ("610400", "610500"):
                stream = "opex"
            local_annual = usd * 1_000_000.0 / wrates[stream]
            out[acct] = local_annual * shapes[stream]
        return out

    # ------------------------------------------------------------- driver paths
    #: Accounts whose interim months come from an economic driver rather than a line.
    DRIVEN = bd.DRIVEN_CAPTIONS

    def _bs_driver_path(self, code: str, col: str, periods: list[Period],
                        open_local: dict[str, float], pl: dict[str, np.ndarray]
                        ) -> list[dict[str, float]]:
        """
        Monthly balances generated from the economics that move them, then scaled so the
        December balance lands exactly on the anchored year-end target.

        Slow-moving captions with no meaningful intra-year driver -- other non-current
        assets, other long-term liabilities, right-of-use assets, intercompany positions,
        equity -- continue to interpolate, which is documented rather than hidden.
        """
        e = self.ent[code]
        n = len(periods)
        g = rng("bs", code, col)
        ye_usd = self.lb.year_end_bs_usd(col).get(code, {})
        rate_ye = self.lb.close_rate(code, periods[-1].period_key, col)
        ye = {a: v * 1_000_000.0 / rate_ye for a, v in ye_usd.items()}

        def stream(prefixes, exclude=()) -> np.ndarray:
            out = np.zeros(n)
            for a, arr in pl.items():
                if a.startswith(prefixes) and not a.startswith(exclude):
                    out += arr[:n]
            return out

        revenue = -stream(("4",), ("44", "49"))
        cos = stream(("5",), ("59",))
        opex = stream(("6",), ("695",))
        payroll = sum((pl[a][:n] for a in ("610100", "610200", "610300", "610600",
                                           "515100", "515200", "515300", "520100")
                       if a in pl), start=np.zeros(n))
        bonus = pl.get("610400", np.zeros(n))[:n]
        # Intercompany interest accrues and settles exactly like external interest, and at
        # the service and holding entities it is the whole of the charge.
        interest = sum((pl[a][:n] for a in ("730100", "730200", "730300", "730500",
                                            "795200")
                        if a in pl), start=np.zeros(n))
        tax = stream(("8",))
        dep = stream(("710",))
        # Operating expenditure settled in cash, used to size prepaid policies.  Only the
        # payroll that sits inside operating expenses is removed -- the production payroll
        # in cost of sales was never part of `opex` to begin with.
        opex_payroll = sum((pl[a][:n] for a in ("610100", "610200", "610300", "610600")
                            if a in pl), start=np.zeros(n))
        cash_opex = np.maximum(opex - opex_payroll - bonus, 0.0)

        prior_rev = np.full(3, revenue.mean() if revenue.sum() else 0.0)
        prior_spend = np.full(3, (cos + cash_opex).mean() if cos.sum() else 0.0)

        paths: dict[str, np.ndarray] = {}
        # paths that are already the answer and must not be scaled onto an anchor
        exact: dict[str, np.ndarray] = {}

        # --- receivables: an ageing profile over recent revenue --------------
        if revenue.sum() > 0:
            dso = 58.0 * DSO_TILT.get(code, 1.0)
            paths["120100"] = bd.ageing_balance(revenue, prior_rev, bd.ageing_profile(dso))
            # The allowance is assessed against the ledger it provides for, so it moves
            # with receivables rather than drifting between year ends on its own line.
            paths["120200"] = -paths["120100"]
        # --- payables: an ageing profile over recent purchases and cash costs -
        spend = cos + cash_opex
        if spend.sum() > 0:
            dpo = 50.0 * DPO_TILT.get(code, 1.0)
            paths["210100"] = bd.ageing_balance(spend, prior_spend, bd.ageing_profile(dpo))
            paths["210200"] = paths["210100"] * 0.163
        # --- inventory: opening + purchases - consumption ---------------------
        inv_open = sum(open_local.get(a, 0.0) for a in ("130100", "130200", "130300"))
        if inv_open > 0 or ye.get("130300", 0.0) > 0:
            inv, _purch = bd.inventory_path(inv_open, cos, periods, g)
            for acct, share in (("130100", 0.34), ("130200", 0.21), ("130300", 0.48)):
                paths[acct] = inv * share / 1.03
        # --- accruals: real sawtooths ----------------------------------------
        if payroll.sum() > 0:
            paths["215100"] = -bd.payroll_accrual(payroll, periods)
        if bonus.sum() > 0:
            paths["215200"] = -bd.sawtooth_accrual(bonus, periods, {3},
                                                   -open_local.get("215200", 0.0))
        if interest.sum() > 0:
            # Interest is paid quarterly in arrears, settling in the month after each
            # interest period ends, so a quarter's accrual is always outstanding at the
            # balance sheet date.  Settling on the quarter end itself would leave December
            # at a trough and make the year-end accrual unexplainable.
            paths["216100"] = -bd.sawtooth_accrual(interest, periods, {1, 4, 7, 10},
                                                   -open_local.get("216100", 0.0))
        if tax.sum() > 0:
            paths["218100"] = -bd.sawtooth_accrual(tax, periods, {1, 4, 7, 10},
                                                   -open_local.get("218100", 0.0))
        # --- prepaid: annual policies paid at renewal, then amortised ---------
        if cash_opex.sum() > 0:
            paths["140100"] = bd.prepaid_path(cash_opex * 0.055, periods)
        # --- property, plant and equipment: lumpy additions less depreciation -
        gross_open = sum(open_local.get(a, 0.0) for a in PPE_CLASSES)
        accum_open = open_local.get("155100", 0.0)
        gross_ye = sum(ye.get(a, 0.0) for a in PPE_CLASSES)
        capex_total = max(gross_ye - gross_open + dep.sum(), 0.0)
        if gross_open > 0 or gross_ye > 0:
            capex = np.full(n, capex_total / max(n, 1))
            gross, accum = bd.ppe_path(gross_open, accum_open, capex, dep, g)
            denom = max(gross[-1], 1e-9)
            for acct, share in PPE_CLASSES.items():
                paths[acct] = gross * share
            paths["155100"] = accum
        # --- investment in subsidiaries: a step on each acquisition date -----
        # The balance is the sum of the considerations actually paid, so it moves only when
        # a transaction completes.  Interpolating it between year ends would spread a
        # single acquisition across twelve months and make the balance unexplainable.
        # Every holding entity is USD-functional and the register carries USD cost, so no
        # translation is involved and the path needs no anchor scaling.
        inv = np.array([sum(amt for (par, sub), amt in investments_at(p.end).items()
                            if par == code and self.lb.live_at(sub, p.end))
                        for p in periods]) * 1e6      # the register is in USD millions
        if inv.any():
            assert self.ent[code].currency == "USD", (
                f"{code} holds investments but is not USD-functional")
            exact["178100"] = inv

        # --- external debt: an instrument schedule ---------------------------
        if code == "NIG-100":
            fy = 2026 if col.startswith("FY2026") else int(col[2:6])
            draws = {2023: (4, 25.0), 2024: (7, 30.0)}
            month, amount = draws.get(fy, (None, 0.0))
            rate = self.lb.close_rate(code, periods[-1].period_key, col)
            paths["230100"] = bd.debt_path(
                open_local.get("230100", 0.0), ye.get("230100", 0.0), periods,
                scheduled_quarterly=-0.575e6, draw_month=month,
                draw_amount=-amount * 1e6)
            paths["220200"] = bd.debt_path(
                open_local.get("220200", 0.0), ye.get("220200", 0.0), periods,
                scheduled_quarterly=0.0, draw_month=None, draw_amount=0.0)

        # --- assemble: driven where we have a driver, interpolated otherwise --
        excluded = {"110100", "320100", "320200"}
        accounts = sorted((set(open_local) | set(ye)) - excluded)
        factors = self._bs_factor_carry.setdefault(code, {})
        rows: list[dict[str, float]] = []
        scaled: dict[str, np.ndarray] = {}
        for a in accounts:
            target = ye.get(a, 0.0)
            if a in exact:
                scaled[a] = exact[a]
            elif a in paths and abs(target) > 1e-6:
                try:
                    path, factor = bd.apply_year_end_anchor(
                        paths[a], target, factors.get(a))
                except ValueError as exc:
                    raise ValueError(f"{code} {col} account {a}: {exc}") from None
                factors[a] = factor
                scaled[a] = path
            else:
                o, c = open_local.get(a, 0.0), target
                scaled[a] = o + (c - o) * (np.arange(1, n + 1) / n)
        for i in range(n):
            rows.append({a: float(scaled[a][i]) for a in accounts})
        return rows

    # ------------------------------------------------------------------ intercompany
    def ic_monthly(self, col: str, periods: list[Period]):
        """
        Both legs of every intercompany flow, phased monthly.

        Amounts are set in USD and each side converts at its OWN monthly average rate, so
        the pair matches exactly in USD however different the two functional currencies --
        which is what makes the elimination net to nil before any deliberate fault.
        Returns (pl_by_entity_period, legs_by_entity_period).
        """
        pl: dict[tuple[str, int], dict[str, float]] = {}
        legs: dict[tuple[str, int], list[tuple]] = {}
        rs = self.m.rate_set_for(col)
        for f in self.m.ic_flows_usd(col):
            seller, buyer = f["seller"], f["buyer"]
            live = [p for p in periods
                    if p.end >= max(self.ent[seller].effective_from,
                                    self.ent[buyer].effective_from)]
            if not live:
                continue
            g = rng("ic", f["flow_id"], seller, buyer, col)
            shape = seasonal_shape(g, len(live), 0.06 if f["kind"] == "INTEREST" else 0.14,
                                   10, noise=0.03)
            monthly_usd = f["amount_usd"] * 1_000_000.0 * shape
            for p, usd in zip(live, monthly_usd):
                for side, ent_code, pl_acct, bs_acct, partner, sign in (
                        ("S", seller, f["seller_pl"], f["seller_bs"], buyer, -1),
                        ("B", buyer, f["buyer_pl"], f["buyer_bs"], seller, +1)):
                    rate = self.m.rate(self.ent[ent_code].currency, p.period_key, "AVG", rs)
                    local = usd / rate
                    key = (ent_code, p.period_key)
                    d = pl.setdefault(key, {})
                    d[pl_acct] = d.get(pl_acct, 0.0) + sign * local
                    # journals.py posts [(debit, +amt), (credit, -amt)]
                    if side == "S":
                        legs.setdefault(key, []).append(
                            (pl_acct, bs_acct, local, partner, f["kind"]))
                    else:
                        legs.setdefault(key, []).append(
                            (bs_acct, pl_acct, local, partner, f["kind"]))
        return pl, legs

    # ------------------------------------------------------------------ treasury
    def apply_measurement_reserve(self, rows: list[EntityMonth]) -> dict[int, float]:
        """
        Reconcile layer-1 cash to the approved anchor through a disclosed equity reserve.

        Every balance sheet caption other than cash is pinned to an approved anchor, and
        retained earnings rolls forward from each entity's own locally-measured result.
        Those two facts over-determine the balance sheet, so a difference remains, and with
        everything else pinned it would otherwise fall into cash.

        The difference is an equity measurement effect.  The anchor model accumulates group
        results at the rates ruling when they were earned and carries the group's own
        cumulative translation adjustment; the entity ledgers accumulate local results and
        are translated at closing rates.  It is not a cash effect, and letting it sit in
        cash would misstate the one balance in the group that is externally verifiable and
        would leave the generated revolver drawn against a shortfall that does not exist.

        So it is posted where it belongs and named for what it is: a holding-company equity
        reserve (329100), measured at each year end when the anchor is struck, disclosed
        line by line in `data/reference/translation_difference.csv`, and carried at Topco,
        which is USD-functional so the reserve is not itself retranslated.  Phase 4 removes
        it and replaces it with a CTA computed from the entity ledgers; it must never be
        treated as a consolidation input (ADR-0004, CTL-FX-04).

        This is deliberately not a plug in a real balance.  It is a single named line whose
        whole purpose is to make the unexplained residual visible and measurable, and a
        control caps it as a share of layer-1 total assets.
        """
        TOPCO, RESERVE = "NIG-100", "329100"
        by_period: dict[int, list[EntityMonth]] = {}
        for em in rows:
            by_period.setdefault(em.period_key, []).append(em)

        def group_cash(pk: int) -> float:
            rs = "FORECAST" if pk // 100 == 2026 else "ACTUAL"
            return sum(em.bs_close["110100"] * self.m.rate(em.currency, pk, "CLOSE", rs)
                       for em in by_period[pk])

        bs = self.m.bs_anchor
        reserve: dict[int, float] = {}
        carry = 0.0
        for year in (2023, 2024, 2025, 2026):
            pk = year * 100 + 12
            col = "FY2026F" if year == 2026 else f"FY{year}A"
            if pk in by_period:
                # the reserve is struck at the year end, against the anchored cash balance
                carry = bs["cash"][col] * 1e6 - group_cash(pk)
            for p in sorted(k for k in by_period if k // 100 == year):
                reserve[p] = carry
        # 2026 closes in August, so its reserve is the one struck at December 2025
        for pk, amt in reserve.items():
            em = next(e for e in by_period[pk] if e.entity == TOPCO)
            em.bs_close["110100"] += amt
            em.bs_close[RESERVE] = em.bs_close.get(RESERVE, 0.0) - amt
        return reserve

    def apply_revolver_sweep(self, rows: list[EntityMonth]) -> dict[int, float]:
        """
        Manage the revolving credit facility against the group's monthly liquidity need.

        Cash is the residual of the balanced entity journals, so a month in which working
        capital builds faster than the business collects leaves the group short.  A real
        group draws its revolver, and repays it as soon as collections allow, because
        utilisation costs margin.  The draw is booked at Topco, which holds all external
        debt: cash up, facility utilisation up.  December is set to the approved year-end
        anchor, so every anchored balance is unchanged.
        """
        TOPCO, RCF = "NIG-100", "220200"
        by_period: dict[int, list[EntityMonth]] = {}
        for em in rows:
            by_period.setdefault(em.period_key, []).append(em)

        def group_cash(pk: int) -> float:
            rs = "FORECAST" if pk // 100 == 2026 else "ACTUAL"
            return sum(em.bs_close["110100"] * self.m.rate(em.currency, pk, "CLOSE", rs)
                       for em in by_period[pk])

        topco_of = {pk: next(em for em in g if em.entity == TOPCO)
                    for pk, g in by_period.items()}
        drawn_now = {pk: -topco_of[pk].bs_close.get(RCF, 0.0) for pk in by_period}
        # the position the ledgers produce with the facility undrawn
        pre = {pk: group_cash(pk) - drawn_now[pk] for pk in by_period}
        year_end = {pk // 100: drawn_now[pk] for pk in by_period if pk % 100 == 12}
        activity = {pk: sum(em.context.get("activity", 0.0)
                            * self.m.rate(em.currency, pk, "AVG",
                                          "FORECAST" if pk // 100 == 2026 else "ACTUAL")
                            for em in g) for pk, g in by_period.items()}
        target = bd.revolver_path(pre, year_end, activity, MIN_GROUP_CASH_USD,
                                  CASH_BUFFER_USD, RCF_COMMITMENT_USD)
        for pk, want in target.items():
            move = want - drawn_now[pk]
            if abs(move) < 1e-6:
                continue
            em = topco_of[pk]
            em.bs_close["110100"] += move
            em.bs_close[RCF] = em.bs_close.get(RCF, 0.0) - move
        return target

    def apply_cash_pooling(self, rows: list[EntityMonth]) -> None:
        """
        Group cash pooling: operating entities sweep surplus cash to Topco through an
        intercompany treasury current account.

        Without this, every operating entity accumulates cash while Topco -- which carries
        all the external debt, pays for the acquisitions and funds the subsidiaries -- runs
        a large negative bank balance, which no real group would tolerate.  Pooling only
        redistributes cash: the group total is untouched and both legs of the current
        account are in the operating entity's currency, so the pair eliminates exactly.
        """
        TOPCO, RECV, PAY = "NIG-100", "125100", "225100"
        by_period: dict[int, list[EntityMonth]] = {}
        for em in rows:
            by_period.setdefault(em.period_key, []).append(em)

        for pk, group in by_period.items():
            rs = "FORECAST" if pk // 100 == 2026 else "ACTUAL"
            rate = {em.entity: self.m.rate(em.currency, pk, "CLOSE", rs) for em in group}
            total_usd = sum(em.bs_close["110100"] * rate[em.entity] for em in group)
            opcos = [em for em in group if em.entity != TOPCO]
            act = {em.entity: max(em.context.get("activity", 0.0) * rate[em.entity], 1.0)
                   for em in opcos}
            act_sum = sum(act.values()) or 1.0
            # Topco keeps a quarter of group cash; the rest sits where the trading happens
            topco_share = 0.25
            sweep_total = 0.0
            for em in opcos:
                target_usd = total_usd * (1 - topco_share) * act[em.entity] / act_sum
                target_local = target_usd / rate[em.entity]
                sweep = em.bs_close["110100"] - target_local
                em.bs_close["110100"] = target_local
                em.bs_close[RECV] = em.bs_close.get(RECV, 0.0) + sweep
                sweep_total += sweep * rate[em.entity]
            topco = next(em for em in group if em.entity == TOPCO)
            topco.bs_close["110100"] += sweep_total
            topco.bs_close[PAY] = topco.bs_close.get(PAY, 0.0) - sweep_total

        # re-chain openings so each month opens on the prior month's restated close
        prev: dict[str, dict[str, float]] = {}
        for em in sorted(rows, key=lambda r: (r.entity, r.period_key)):
            if em.entity in prev:
                em.bs_open = prev[em.entity]
            prev[em.entity] = dict(em.bs_close)

    # ------------------------------------------------------------------ build
    def build_actuals(self, pool: bool = True) -> list[EntityMonth]:
        opening_usd = self.opening_bs_usd()
        out: list[EntityMonth] = []
        for code, e in sorted(self.ent.items()):
            # opening local position
            if code in opening_usd:
                # The 2022 closing rate is an anchor, not part of the generated series,
                # which starts in January 2023.
                from .fx import _anchor_rates
                r0 = _anchor_rates()[(e.currency, 2022, "ACTUAL")][1]
                open_local = {a: v * 1_000_000.0 / r0 for a, v in opening_usd[code].items()}
                start_pk = 202301
            else:
                eff = e.effective_from
                start_pk = eff.year * 100 + eff.month
                r0 = self.m.rate(e.currency, start_pk, "CLOSE", "ACTUAL")
                open_local = {a: v * 1_000_000.0 / r0
                              for a, v in self.acquisition_opening_usd(code).items()}

            carry = dict(open_local)
            for year in (2023, 2024, 2025, 2026):
                col = "FY2026F" if year == 2026 else f"FY{year}A"
                periods = [p for p in build_periods((year, 1), (year, 12))
                           if p.period_key >= start_pk]
                if year == 2026:
                    periods = [p for p in periods if p.period_key <= 202608]
                    full = [p for p in build_periods((2026, 1), (2026, 12))
                            if p.period_key >= start_pk]
                else:
                    full = periods
                if not periods:
                    continue
                pl_full = self._pl_local_monthly(code, col, full)
                ic_pl, ic_legs = self._ic_cache.setdefault(
                    (col, tuple(p.period_key for p in full)),
                    self.ic_monthly(col, full))
                for i, p in enumerate(full):
                    for a, v in ic_pl.get((code, p.period_key), {}).items():
                        arr = pl_full.setdefault(a, np.zeros(len(full)))
                        arr[i] += v
                act = np.array([sum(-pl_full[a][i] for a in pl_full if a.startswith("4"))
                                for i in range(len(full))])
                if act.sum() <= 0:
                    act = np.ones(len(full))
                bs_full = self._bs_driver_path(code, col, full, carry, pl_full)

                re_account = "320200" if e.erp == "KESTREL" else "320100"
                re_open = carry.get(re_account, 0.0) + carry.get(
                    "320100" if re_account == "320200" else "320200", 0.0)
                ytd = 0.0
                year_total = sum(float(v.sum()) for v in pl_full.values())
                for i, p in enumerate(full):
                    if year == 2026 and p.period_key > 202608:
                        break
                    em = EntityMonth(entity=code, period_key=p.period_key, currency=e.currency)
                    em.pl = {a: float(v[i]) for a, v in pl_full.items() if abs(v[i]) > 1e-6}
                    ytd += sum(em.pl.values())
                    is_year_end = (p.month == 12)
                    close = dict(bs_full[i])
                    close[re_account] = re_open + (year_total if is_year_end else 0.0)
                    close["110100"] = -(sum(bs_full[i].values())
                                        + close[re_account]
                                        + (0.0 if is_year_end else ytd))
                    em.bs_open = dict(carry)
                    em.bs_close = close
                    em.context = {"activity": float(act[i]),
                                  "ytd_pl": ytd, "year_end": float(is_year_end)}
                    self.ic_legs[(code, p.period_key)] = ic_legs.get((code, p.period_key), [])
                    out.append(em)
                    carry = dict(close)
                if year == 2026:
                    break
        if pool:
            self.measurement_reserve = self.apply_measurement_reserve(out)
            self.revolver_draws = self.apply_revolver_sweep(out)
            self.apply_cash_pooling(out)
        return out
