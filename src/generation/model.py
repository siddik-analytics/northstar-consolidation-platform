"""
The Northstar economic model: pushes the approved group anchors down to
entity x period x group account, in each entity's own functional currency.

This module produces *what each entity's ledger must say*.  `journals.py` then turns that
into balanced journal entries, and the ERP renderers dress those in each system's native
conventions.  Nothing here writes a file.

Design
------
1.  Annual USD amounts are allocated to entities using economic drivers, with
    `allocate_exact` so a pushdown never leaks a rounding difference.
2.  Each entity-year is converted to local currency using a *revenue-weighted* average
    rate, so that translating the resulting monthly local series back at monthly average
    rates reproduces the USD anchor exactly.  Local amounts therefore carry no FX
    artefact -- the seasonality is genuine local seasonality.
3.  Balance sheet targets come from local drivers (days ratios, roll-forwards), then a
    per-caption calibration scalar ties the group total to the anchor at each fiscal year
    end.  Scalars are interpolated across the year so the path stays smooth.
4.  Cash is never targeted.  It is the residual of balanced journals, and the layer-1
    group cash lands on the anchor because every other caption does.

Phase 2 generates LAYER 1 ONLY (entity as-reported).  Goodwill, acquired intangibles,
their deferred tax and amortisation, and unrealised intercompany profit are Phase 4
layer-3 constructs and deliberately do not exist in any source ledger.  The bridge from
the consolidated anchor to the expected source-layer aggregate is built in `targets.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .common import (ACTUAL_COLS, ACTUAL_PERIODS, COLS, Entity, MILLIONS, Period,
                     allocate_exact, load_addbacks, load_anchor, load_bu_anchor,
                     load_entity_revenue, load_opening_bs, operating_entities,
                     plan_periods, rng, seasonal_shape)
from .fx import build_rate_series, rate_lookup

# --------------------------------------------------------------------------- mix tables
# Revenue mix by business unit: {group_account: share of gross revenue}
REVENUE_MIX = {
    "FC": {"410100": 0.690, "410200": 0.255, "430100": 0.055},
    "IS": {"420100": 0.545, "420200": 0.200, "420300": 0.255},
    "ES": {"425100": 0.855, "425200": 0.145},
    "AM": {"415100": 0.920, "430100": 0.080},
}
# Contra-revenue as a share of gross revenue, by BU
REVENUE_CONTRA = {
    "FC": {"440100": 0.008, "440200": 0.014},
    "IS": {"440100": 0.004, "440200": 0.005},
    "ES": {"440100": 0.003, "440200": 0.004},
    "AM": {"440100": 0.011, "440200": 0.022},
}

# Cost of sales mix by business unit: {group_account: share of cost of sales}
COS_MIX = {
    "FC": {"510100": 0.420, "510200": 0.180, "510300": 0.060, "515100": 0.140,
           "515300": 0.040, "520100": 0.060, "520200": 0.030, "520300": 0.025,
           "525100": 0.025, "530100": 0.005, "530200": 0.015},
    "IS": {"515200": 0.460, "515300": 0.130, "510300": 0.160, "520400": 0.080,
           "520300": 0.070, "510100": 0.050, "520100": 0.040, "525100": 0.010},
    "ES": {"510200": 0.340, "510300": 0.200, "515200": 0.280, "515300": 0.080,
           "520300": 0.040, "535100": 0.030, "525100": 0.030},
    "AM": {"510200": 0.680, "510100": 0.080, "515100": 0.080, "520100": 0.050,
           "520300": 0.030, "525100": 0.050, "525200": 0.030},
}

# Recurring operating expense mix (normalised in code)
OPEX_MIX = {
    "610100": 0.360, "610200": 0.078, "610300": 0.040, "610400": 0.050, "610500": 0.020,
    "610600": 0.020, "610700": 0.010, "610800": 0.010,
    "620100": 0.060, "620200": 0.015, "620300": 0.015, "620400": 0.020,
    "630100": 0.015, "630200": 0.015, "630300": 0.020,
    "640100": 0.015, "640200": 0.010, "640300": 0.030, "640400": 0.007,
    "650100": 0.030, "650200": 0.020, "650300": 0.008,
    "660100": 0.030, "660200": 0.015,
    "670100": 0.008, "670200": 0.004, "670300": 0.003, "670400": 0.010,
}
CORPORATE_OPEX_TILT = {  # corporate entities are professional-services and IT heavy
    "610100": 1.15, "620100": 0.55, "630100": 3.2, "630200": 3.0, "630300": 3.5,
    "650100": 2.2, "650200": 2.4, "640100": 0.25, "640200": 0.20, "640300": 0.05,
    "660200": 0.35, "620400": 0.5, "610800": 1.6,
}

# Share of group recurring opex borne by the corporate entities
CORPORATE_OPEX_SHARE = {"NIG-100": 0.062, "NIG-110": 0.142}

# Accounts that only ever exist at the corporate entities, whatever the mix table says.
# Share-based compensation is granted by Topco and its reserve (315100) sits there, so no
# operating entity's ERP carries either account.
CORPORATE_ONLY_ACCOUNTS = {"610500": {"NIG-100": 0.55, "NIG-110": 0.45}}

# Which entities bear each non-recurring add-back account, and in what proportion
ADDBACK_BEARERS = {
    "630400": {"NIG-100": 1.0},                                        # sponsor monitoring fee
    "680300": {"NIG-100": 0.75, "NIG-110": 0.25},                      # transaction costs
    "680400": {"NIG-110": 0.55, "NIG-220": 0.15, "NIG-320": 0.12,
               "NIG-300": 0.10, "NIG-410": 0.08},                      # ERP / integration
    "680100": {"NIG-220": 0.30, "NIG-200": 0.22, "NIG-320": 0.16,
               "NIG-410": 0.12, "NIG-300": 0.10, "NIG-210": 0.10},     # severance
    "680200": {"NIG-220": 0.40, "NIG-200": 0.25, "NIG-320": 0.20, "NIG-410": 0.15},
    "680600": {"NIG-300": 0.45, "NIG-400": 0.35, "NIG-200": 0.20},     # legal settlements
    "680700": {"NIG-100": 0.60, "NIG-200": 0.40},                      # retention bonuses
}

# Entity gross-margin tilt within its business unit (relative, mean-neutral)
GM_TILT = {"NIG-200": 1.03, "NIG-210": 0.94, "NIG-220": 1.02,
           "NIG-300": 1.02, "NIG-310": 0.95, "NIG-320": 0.99,
           "NIG-400": 1.01, "NIG-410": 0.96,
           "NIG-500": 1.02, "NIG-510": 0.95}

# Working capital days by entity -- services carry more unbilled, distribution collects faster
DSO_TILT = {"NIG-200": 0.98, "NIG-210": 1.02, "NIG-220": 1.14, "NIG-300": 1.06,
            "NIG-310": 1.08, "NIG-320": 1.12, "NIG-400": 1.10, "NIG-410": 1.16,
            "NIG-500": 0.80, "NIG-510": 0.86}
DPO_TILT = {"NIG-200": 1.00, "NIG-210": 0.96, "NIG-220": 1.10, "NIG-300": 0.94,
            "NIG-310": 0.92, "NIG-320": 1.06, "NIG-400": 1.08, "NIG-410": 1.12,
            "NIG-500": 1.02, "NIG-510": 1.04}
# Inventory only exists where goods are held
INVENTORY_WEIGHT = {"NIG-200": 1.00, "NIG-210": 0.85, "NIG-220": 0.95,
                    "NIG-400": 0.35, "NIG-410": 0.30,
                    "NIG-500": 1.35, "NIG-510": 1.25,
                    "NIG-300": 0.06, "NIG-310": 0.05, "NIG-320": 0.05}
# Capital intensity relative to revenue
CAPEX_WEIGHT = {"NIG-200": 1.35, "NIG-210": 1.10, "NIG-220": 1.45,
                "NIG-300": 1.25, "NIG-310": 1.15, "NIG-320": 1.05,
                "NIG-400": 0.65, "NIG-410": 0.55,
                "NIG-500": 0.55, "NIG-510": 0.45,
                "NIG-100": 0.10, "NIG-110": 0.55}

SEASONALITY = {  # (amplitude, peak month) by business unit
    "FC": (0.13, 11), "IS": (0.19, 9), "ES": (0.10, 12), "AM": (0.08, 10),
    "CORP": (0.04, 12),
}

BU_OF_ACCOUNT_GROUP = {"revenue": "R", "cos": "C", "opex": "O"}


@dataclass
class EntityPeriod:
    """One entity, one period, local currency. Debit-positive throughout."""
    entity: str
    period_key: int
    currency: str
    pl: dict[str, float] = field(default_factory=dict)          # group_account -> amount
    bs_close: dict[str, float] = field(default_factory=dict)    # group_account -> balance
    drivers: dict[str, float] = field(default_factory=dict)     # non-financial context


# --------------------------------------------------------------------------- allocation
class EconomicModel:
    def __init__(self):
        self.entities = operating_entities()
        self.rev_anchor = load_entity_revenue()
        self.bu_anchor = load_bu_anchor()
        self.pl_anchor = load_anchor("income_statement")
        self.bs_anchor = load_anchor("balance_sheet")
        self.cf_anchor = load_anchor("cash_flow")
        self.kpi_anchor = load_anchor("kpi", key="metric")
        self.ic_anchor = load_anchor("intercompany", key="measure")
        self.addbacks = load_addbacks()
        self.opening = load_opening_bs()
        self.rates = rate_lookup(build_rate_series())
        self.opcos = [c for c in self.rev_anchor]                     # 10 revenue entities
        self.corp = ["NIG-100", "NIG-110"]

    # ---------------------------------------------------------------- rates
    def rate(self, ccy: str, period_key: int, kind: str, rate_set: str) -> float:
        return self.rates[(ccy, period_key, kind, rate_set)]

    def rate_set_for(self, col: str) -> str:
        return {"FY2026B": "BUDGET", "FY2026F": "FORECAST"}.get(col, "ACTUAL")

    # ---------------------------------------------------------------- annual USD pushdown
    def entity_revenue_usd(self, col: str) -> dict[str, float]:
        return {e: self.rev_anchor[e][col] for e in self.opcos}

    def entity_gross_profit_usd(self, col: str) -> dict[str, float]:
        """BU gross profit split across its entities with a mean-neutral margin tilt."""
        out: dict[str, float] = {}
        for bu in ["FC", "IS", "ES", "AM"]:
            members = [e for e in self.opcos if self.entities[e].bu == bu]
            members = [e for e in members if self.rev_anchor[e][col] > 0]
            if not members:
                continue
            bu_gp = self.bu_anchor[(bu, "gross_profit")][col]
            w = np.array([self.rev_anchor[e][col] * GM_TILT[e] for e in members])
            for e, v in zip(members, allocate_exact(bu_gp, w, 6)):
                out[e] = v
        return out

    def entity_headcount_weight(self, col: str) -> dict[str, float]:
        """Headcount proxy: BU headcount split by entity revenue share within the BU."""
        out = {}
        for bu in ["FC", "IS", "ES", "AM"]:
            members = [e for e in self.opcos if self.entities[e].bu == bu
                       and self.rev_anchor[e][col] > 0]
            if not members:
                continue
            hc = self.bu_anchor[(bu, "headcount")][col]
            rev = np.array([self.rev_anchor[e][col] for e in members])
            # services entities carry more heads per dollar than distribution
            intensity = np.array([1.0 if bu != "AM" else 0.75 for _ in members])
            for e, v in zip(members, allocate_exact(hc, rev * intensity, 2)):
                out[e] = v
        corp_hc = self.bu_anchor[("CORP", "headcount")][col]
        out["NIG-100"] = round(corp_hc * 0.30, 2)
        out["NIG-110"] = round(corp_hc - out["NIG-100"], 2)
        return out

    def entity_opex_usd(self, col: str) -> dict[str, dict[str, float]]:
        """
        Returns {entity: {group_account: annual USD}} covering recurring opex and add-backs.
        Recurring opex is a revenue/headcount blend; add-backs follow the business story.
        """
        total_opex = self.pl_anchor["opex"][col]
        one_time = self.pl_anchor["one_time_in_opex"][col]
        recurring = total_opex - one_time
        hc = self.entity_headcount_weight(col)
        rev = self.entity_revenue_usd(col)

        corp_amt = {e: recurring * CORPORATE_OPEX_SHARE[e] for e in self.corp}
        opco_pool = recurring - sum(corp_amt.values())
        active = [e for e in self.opcos if rev[e] > 0]
        w = np.array([0.60 * rev[e] / max(sum(rev.values()), 1e-9)
                      + 0.40 * hc.get(e, 0) / max(sum(hc.values()), 1e-9) for e in active])
        opco_amt = dict(zip(active, allocate_exact(opco_pool, w, 6)))
        entity_recurring = {**corp_amt, **opco_amt}

        out: dict[str, dict[str, float]] = {e: {} for e in self.entities}
        mix_total = sum(OPEX_MIX.values())
        for e, amt in entity_recurring.items():
            tilt = CORPORATE_OPEX_TILT if e in self.corp else {}
            mix = {a: OPEX_MIX[a] * tilt.get(a, 1.0) for a in OPEX_MIX}
            s = sum(mix.values())
            accounts = list(mix)
            vals = allocate_exact(amt, np.array([mix[a] / s * mix_total for a in accounts]), 6)
            for a, v in zip(accounts, vals):
                out[e][a] = out[e].get(a, 0.0) + v

        # Centrally-held accounts are swept to the corporate entities.  Share-based
        # compensation is not a free output of the cost mix: it is an approved anchor, it
        # is equity-settled, and the anchored contributed capital grows by exactly that
        # amount every year.  It is therefore set to the anchor and the remaining recurring
        # cost mix is normalised around it, so total recurring opex is unchanged.
        for acct, split in CORPORATE_ONLY_ACCOUNTS.items():
            pooled = sum(out[e].pop(acct, 0.0) for e in out)
            target = self.cf_anchor["sbc"][col] if acct == "610500" else pooled
            if pooled and abs(recurring - pooled) > 1e-9:
                factor = (recurring - target) / (recurring - pooled)
                for e in out:
                    for a in out[e]:
                        out[e][a] *= factor
            if target:
                vals = allocate_exact(target, np.array(list(split.values())), 6)
                for e, v in zip(split, vals):
                    out[e][acct] = out[e].get(acct, 0.0) + v

        # Non-recurring add-backs, by account, to the entities that actually bore them
        for acct, series in self.addbacks.items():
            if acct == "TOTAL":
                continue
            amount = series[col]
            if amount == 0:
                continue
            bearers = {e: w for e, w in ADDBACK_BEARERS[acct].items()
                       if self._entity_live(e, col)}
            vals = allocate_exact(amount, np.array(list(bearers.values())), 6)
            for e, v in zip(bearers, vals):
                out[e][acct] = out[e].get(acct, 0.0) + v
        return out

    def _entity_live(self, code: str, col: str) -> bool:
        year = 2026 if col.startswith("FY2026") else int(col[2:6])
        e = self.entities[code]
        return e.effective_from.year <= year

    def entity_depreciation_usd(self, col: str) -> dict[str, float]:
        dep = self.pl_anchor["depreciation"][col]
        rev = self.entity_revenue_usd(col)
        w = np.array([rev.get(e, 0.0) * CAPEX_WEIGHT[e] if e in rev
                      else max(sum(rev.values()), 1.0) * 0.004 * CAPEX_WEIGHT[e]
                      for e in self.entities if self._entity_live(e, col)])
        live = [e for e in self.entities if self._entity_live(e, col)]
        return dict(zip(live, allocate_exact(dep, w, 6)))

    def entity_capex_usd(self, col: str) -> dict[str, float]:
        capex = -self.cf_anchor["capex"][col]
        rev = self.entity_revenue_usd(col)
        live = [e for e in self.entities if self._entity_live(e, col)]
        w = np.array([rev.get(e, max(sum(rev.values()), 1.0) * 0.004) * CAPEX_WEIGHT[e]
                      for e in live])
        return dict(zip(live, allocate_exact(capex, w, 6)))

    def entity_current_tax_usd(self, col: str) -> dict[str, float]:
        """
        Source ledgers carry current tax only. Deferred tax is a Phase 4 consolidation
        item (OQ-05: the group's deferred tax is dominated by PPA fair-value differences).
        """
        total = self.pl_anchor["tax"][col] - self.cf_anchor["deferred_tax"][col]
        rev = self.entity_revenue_usd(col)
        gp = self.entity_gross_profit_usd(col)
        opex = {e: sum(v.values()) for e, v in self.entity_opex_usd(col).items()}
        live = [e for e in self.entities if self._entity_live(e, col)]
        pbt = {e: gp.get(e, 0.0) - opex.get(e, 0.0) for e in live}
        w = np.array([max(pbt[e], 0.0) + 0.02 * rev.get(e, 0.0) for e in live])
        return dict(zip(live, allocate_exact(total, w, 6)))

    # ---------------------------------------------------------------- intercompany
    def ic_flows_usd(self, col: str) -> list[dict]:
        """
        Intercompany flows for the year, in USD, derived from the approved matrix and the
        intercompany anchors.  Both legs of every flow are returned, so the pair matches
        by construction before any deliberate fault is injected.
        """
        rev = self.entity_revenue_usd(col)
        flows: list[dict] = []

        # Management fee: 2.5% of each buyer's external revenue, tied to the anchor
        fee_total = self.ic_anchor["mgmt_fee"][col]
        buyers = [e for e in self.opcos if rev[e] > 0 and self._entity_live(e, col)]
        amts = allocate_exact(fee_total, np.array([rev[e] for e in buyers]), 6)
        for b, a in zip(buyers, amts):
            flows.append(dict(flow_id="IC-MF", kind="MGMT_FEE", seller="NIG-110", buyer=b,
                              amount_usd=a, seller_pl="490300", buyer_pl="695100",
                              seller_bs="120500", buyer_bs="210500"))

        # Product sales
        prod_total = self.ic_anchor["ic_product_sales"][col]
        legs = [("NIG-200", "NIG-210", 0.42), ("NIG-200", "NIG-500", 0.26),
                ("NIG-200", "NIG-510", 0.19), ("NIG-220", "NIG-200", 0.13)]
        legs = [(s, b, w) for s, b, w in legs
                if self._entity_live(s, col) and self._entity_live(b, col)]
        amts = allocate_exact(prod_total, np.array([w for _, _, w in legs]), 6)
        for (s, b, _), a in zip(legs, amts):
            flows.append(dict(flow_id="IC-PR", kind="PRODUCT", seller=s, buyer=b,
                              amount_usd=a, seller_pl="490100", buyer_pl="590100",
                              seller_bs="120500", buyer_bs="210500"))
        # Vector consumes flow components into project WIP once it is in the group
        if self._entity_live("NIG-400", col):
            pass

        # Service recharges
        svc_total = self.ic_anchor["ic_service_sales"][col]
        legs = [("NIG-310", "NIG-300", 0.48), ("NIG-300", "NIG-400", 0.34),
                ("NIG-320", "NIG-410", 0.18)]
        legs = [(s, b, w) for s, b, w in legs
                if self._entity_live(s, col) and self._entity_live(b, col)]
        amts = allocate_exact(svc_total, np.array([w for _, _, w in legs]), 6)
        for (s, b, _), a in zip(legs, amts):
            flows.append(dict(flow_id="IC-SV", kind="SERVICE", seller=s, buyer=b,
                              amount_usd=a, seller_pl="490200", buyer_pl="590200",
                              seller_bs="120500", buyer_bs="210500"))

        # Technology royalty
        roy = self.ic_anchor["ic_royalty"][col]
        if roy and self._entity_live("NIG-220", col):
            flows.append(dict(flow_id="IC-RY", kind="ROYALTY", seller="NIG-200",
                              buyer="NIG-220", amount_usd=roy, seller_pl="490400",
                              buyer_pl="695300", seller_bs="120500", buyer_bs="210500"))

        # Loan interest
        int_total = self.ic_anchor["ic_interest"][col]
        legs = [("NIG-100", "NIG-220", 0.30), ("NIG-100", "NIG-320", 0.24),
                ("NIG-100", "NIG-300", 0.22), ("NIG-100", "NIG-410", 0.15),
                ("NIG-100", "NIG-510", 0.09)]
        legs = [(s, b, w) for s, b, w in legs if self._entity_live(b, col)]
        amts = allocate_exact(int_total, np.array([w for _, _, w in legs]), 6)
        for (s, b, _), a in zip(legs, amts):
            flows.append(dict(flow_id="IC-LN", kind="INTEREST", seller=s, buyer=b,
                              amount_usd=a, seller_pl="795100", buyer_pl="795200",
                              seller_bs="120500", buyer_bs="210500"))
        return flows

    # ---------------------------------------------------------------- monthly phasing
    def seasonality(self, entity: str, col: str, n: int, stream: str) -> np.ndarray:
        bu = self.entities[entity].bu
        amp, peak = SEASONALITY.get(bu, SEASONALITY["CORP"])
        if stream != "revenue":
            amp *= 0.45                      # costs are smoother than revenue
        g = rng("season", entity, col, stream)
        return seasonal_shape(g, n, amp, peak, noise=0.055 if stream == "revenue" else 0.035)

    def weighted_rate(self, entity: str, col: str, shape: np.ndarray,
                      periods: list[Period]) -> float:
        ccy = self.entities[entity].currency
        rs = self.rate_set_for(col)
        rates = np.array([self.rate(ccy, p.period_key, "AVG", rs) for p in periods])
        return float((shape * rates).sum())
