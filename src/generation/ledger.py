"""
Builds the entity x period ledger position: income statement amounts and closing balance
sheet targets, in each entity's functional currency.

Year-end balances are allocated from the approved anchors by economic driver, so they tie
exactly.  Interim months are interpolated between year ends and modulated by the entity's
own activity, so working capital breathes with the business instead of sliding linearly.

Layer 1 only.  Goodwill, acquired intangibles, their deferred tax, PPA amortisation and
unrealised intercompany profit are Phase 4 constructs and appear in no source ledger.
"""

from __future__ import annotations

import numpy as np

from .common import (ACTUAL_PERIODS, Period, allocate_exact, plan_periods, rng)
from .model import (CAPEX_WEIGHT, COS_MIX, EconomicModel, EntityPeriod, INVENTORY_WEIGHT,
                    DPO_TILT, DSO_TILT, REVENUE_CONTRA, REVENUE_MIX)

# Balance sheet captions modelled at source, mapped to the anchor caption they roll into.
# `None` means the caption has no direct anchor equivalent at layer 1.
WC_ACCOUNTS = {
    "120100": "ar", "120200": "ar", "121100": "contract_assets",
    "130100": "inventory", "130200": "inventory", "130300": "inventory", "130400": "inventory",
    "140100": "prepaid", "180100": "other_nca",
    "210100": "ap", "210200": "ap", "211100": "contract_liabilities",
    "215100": "accrued", "215200": "accrued", "215300": "accrued", "215400": "accrued",
    "215500": "accrued", "215600": "accrued", "216100": "accrued", "219100": "accrued",
    "218100": "tax_payable", "245100": "other_ltl",
}
# Split of each anchor caption across its source accounts
CAPTION_SPLIT = {
    "ar": {"120100": 1.018, "120200": -0.018},
    "contract_assets": {"121100": 1.0},
    "inventory": {"130100": 0.34, "130200": 0.21, "130300": 0.48, "130400": -0.03},
    "prepaid": {"140100": 1.0},
    "other_nca": {"180100": 1.0},
    "ap": {"210100": 0.86, "210200": 0.14},
    "contract_liabilities": {"211100": 1.0},
    "accrued": {"215100": 0.30, "215200": 0.26, "215300": 0.07, "215400": 0.08,
                "215500": 0.05, "215600": 0.10, "216100": 0.07, "219100": 0.07},
    "tax_payable": {"218100": 1.0},
    "other_ltl": {"245100": 1.0},
}
# Which entities carry each caption, and with what relative weight
CAPTION_DRIVER = {
    "ar": "revenue_dso", "contract_assets": "revenue_is_es", "inventory": "cos_inventory",
    "prepaid": "revenue", "other_nca": "revenue",
    "ap": "cost_dpo", "contract_liabilities": "revenue_es", "accrued": "opex_payroll",
    "tax_payable": "profit", "other_ltl": "headcount",
}
# Debit-positive convention: liability captions carry a credit balance.
CAPTION_SIGN = {"ar": 1, "contract_assets": 1, "inventory": 1, "prepaid": 1, "other_nca": 1,
                "ap": -1, "contract_liabilities": -1, "accrued": -1, "tax_payable": -1,
                "other_ltl": -1}

PPE_CLASSES = {"150200": 0.24, "150300": 0.46, "150400": 0.13, "150500": 0.09, "150600": 0.08}
KESTREL_ENTITIES = {"NIG-220", "NIG-320", "NIG-410", "NIG-510"}

# Intercompany loan principal, by borrower, in the borrower's currency
IC_LOAN_NOTIONAL = {"NIG-220": ("EUR", 24.0), "NIG-410": ("EUR", 12.0),
                    "NIG-320": ("GBP", 10.0), "NIG-510": ("GBP", 4.0),
                    "NIG-300": ("USD", 15.0)}

# Entity contributed capital (USD m) -- share capital plus additional paid-in capital
ENTITY_CAPITAL = {
    "NIG-100": 145.0, "NIG-110": 2.0, "NIG-200": 60.0, "NIG-210": 18.0, "NIG-220": 11.8,
    "NIG-300": 40.0, "NIG-310": 12.0, "NIG-320": 14.0, "NIG-400": 26.0, "NIG-410": 10.9,
    "NIG-500": 20.0, "NIG-510": 9.0,
}
# Investment in subsidiaries held by each parent (USD m, at cost)
INVESTMENTS = {
    ("NIG-100", "NIG-110"): 2.0, ("NIG-100", "NIG-200"): 118.0,
    ("NIG-200", "NIG-210"): 22.0, ("NIG-100", "NIG-220"): 52.0,
    ("NIG-100", "NIG-300"): 86.0, ("NIG-300", "NIG-310"): 16.0,
    ("NIG-100", "NIG-320"): 24.0, ("NIG-100", "NIG-400"): 44.0,
    ("NIG-400", "NIG-410"): 38.0, ("NIG-100", "NIG-500"): 34.0,
    ("NIG-500", "NIG-510"): 17.0,
}


class LedgerBuilder:
    def __init__(self, model: EconomicModel | None = None):
        self.m = model or EconomicModel()
        self.ent = self.m.entities
        self._cache: dict[str, dict] = {}
        # Filled by SeriesBuilder.calibrate(); see year_end_bs_usd.
        self.investment_adjustment: dict[str, float] = {}

    # ------------------------------------------------------------------ helpers
    def live(self, code: str, col: str) -> bool:
        return self.m._entity_live(code, col)

    def close_rate(self, code: str, period_key: int, col: str) -> float:
        return self.m.rate(self.ent[code].currency, period_key, "CLOSE", self.m.rate_set_for(col))

    # ------------------------------------------------------------------ annual P&L (USD)
    def annual_pl_usd(self, col: str) -> dict[str, dict[str, float]]:
        """{entity: {group_account: annual USD millions}} for external activity."""
        if ("pl", col) in self._cache:
            return self._cache[("pl", col)]
        rev = self.m.entity_revenue_usd(col)
        gp = self.m.entity_gross_profit_usd(col)
        opex = self.m.entity_opex_usd(col)
        dep = self.m.entity_depreciation_usd(col)
        tax = self.m.entity_current_tax_usd(col)

        out: dict[str, dict[str, float]] = {e: {} for e in self.ent if self.live(e, col)}
        for e in list(out):
            bu = self.ent[e].bu
            net_rev = rev.get(e, 0.0)
            if net_rev > 0:
                contra_pct = sum(REVENUE_CONTRA[bu].values())
                gross_rev = net_rev / (1.0 - contra_pct)
                for acct, share in REVENUE_MIX[bu].items():
                    out[e][acct] = out[e].get(acct, 0.0) - gross_rev * share   # credit
                for acct, share in REVENUE_CONTRA[bu].items():
                    out[e][acct] = out[e].get(acct, 0.0) + gross_rev * share   # debit
                cos = net_rev - gp[e]
                for acct, share in COS_MIX[bu].items():
                    out[e][acct] = out[e].get(acct, 0.0) + cos * share
            for acct, amt in opex.get(e, {}).items():
                out[e][acct] = out[e].get(acct, 0.0) + amt
            if dep.get(e):
                out[e]["710100"] = out[e].get("710100", 0.0) + dep[e]
            if tax.get(e):
                out[e]["810100" if self.ent[e].country == "US" else "810300"] = tax[e]
        self._cache[("pl", col)] = out
        return out

    def annual_interest_usd(self, col: str) -> dict[str, dict[str, float]]:
        """Third-party interest: term debt and facilities at Topco, leases at the lessee."""
        pl = self.m.pl_anchor
        lease_int = pl["interest_lease"][col]
        out: dict[str, dict[str, float]] = {}
        out["NIG-100"] = {
            "730100": pl["interest_tlb"][col],
            "730200": pl["interest_rcf"][col],
            "730400": pl["dff_amortisation"][col],
            "730500": pl["commitment_fee"][col],
            "735100": pl["interest_income"][col],       # already negative (credit)
        }
        live = [e for e in self.ent if self.live(e, col) and e != "NIG-100"]
        rev = self.m.entity_revenue_usd(col)
        w = np.array([rev.get(e, 0.5) for e in live])
        for e, v in zip(live, allocate_exact(lease_int, w, 6)):
            out.setdefault(e, {})["730300"] = v
        return out

    # ------------------------------------------------------------------ BS year-end (USD)
    def _driver(self, name: str, col: str) -> dict[str, float]:
        rev = self.m.entity_revenue_usd(col)
        gp = self.m.entity_gross_profit_usd(col)
        hc = self.m.entity_headcount_weight(col)
        opex = {e: sum(v.values()) for e, v in self.m.entity_opex_usd(col).items()}
        live = [e for e in self.ent if self.live(e, col)]
        cos = {e: rev.get(e, 0.0) - gp.get(e, 0.0) for e in live}
        d = {}
        for e in live:
            bu = self.ent[e].bu
            if name == "revenue_dso":
                d[e] = rev.get(e, 0.0) * DSO_TILT.get(e, 1.0)
            elif name == "revenue":
                d[e] = rev.get(e, 0.0) + 0.02 * opex.get(e, 0.0)
            elif name == "revenue_is_es":
                d[e] = rev.get(e, 0.0) if bu in ("IS", "ES") else 0.0
            elif name == "revenue_es":
                d[e] = rev.get(e, 0.0) if bu == "ES" else 0.0
            elif name == "cos_inventory":
                d[e] = cos.get(e, 0.0) * INVENTORY_WEIGHT.get(e, 0.0)
            elif name == "cost_dpo":
                d[e] = (cos.get(e, 0.0) + 0.55 * opex.get(e, 0.0)) * DPO_TILT.get(e, 1.0)
            elif name == "opex_payroll":
                d[e] = 0.45 * opex.get(e, 0.0) + 0.06 * cos.get(e, 0.0)
            elif name == "profit":
                d[e] = max(gp.get(e, 0.0) - opex.get(e, 0.0), 0.0) + 0.01 * rev.get(e, 0.0)
            elif name == "headcount":
                d[e] = hc.get(e, 0.0)
            else:
                d[e] = 1.0
        if sum(d.values()) <= 0:
            d = {e: 1.0 for e in live}
        return d

    def year_end_bs_usd(self, col: str) -> dict[str, dict[str, float]]:
        """{entity: {group_account: USD millions}} at the fiscal year end. Excludes cash."""
        if ("bs", col) in self._cache:
            return self._cache[("bs", col)]
        bs = self.m.bs_anchor
        ic = self.m.ic_anchor
        live = [e for e in self.ent if self.live(e, col)]
        out: dict[str, dict[str, float]] = {e: {} for e in live}

        # ---- working capital and other operating captions -------------------
        for caption, split in CAPTION_SPLIT.items():
            target = bs[caption][col]
            if caption == "inventory":
                target += ic["pup_in_inventory"][col]      # source inventory is gross of PUP
            drv = self._driver(CAPTION_DRIVER[caption], col)
            members = [e for e in live if drv.get(e, 0.0) > 0]
            if not members:
                continue
            sign = CAPTION_SIGN[caption]
            amounts = allocate_exact(target, np.array([drv[e] for e in members]), 6)
            for e, amt in zip(members, amounts):
                for acct, share in split.items():
                    out[e][acct] = out[e].get(acct, 0.0) + sign * amt * share

        # ---- property, plant and equipment ---------------------------------
        ppe_net = bs["ppe_net"][col]
        drv = self._driver("revenue", col)
        w = np.array([max(drv.get(e, 0.0), 0.05) * CAPEX_WEIGHT.get(e, 1.0) for e in live])
        for e, amt in zip(live, allocate_exact(ppe_net, w, 6)):
            gross = amt / 0.62                                  # ~38% depreciated on average
            for acct, share in PPE_CLASSES.items():
                out[e][acct] = out[e].get(acct, 0.0) + gross * share
            out[e]["155100"] = out[e].get("155100", 0.0) - (gross - amt)

        # ---- operating leases: not recognised in Kestrel local books --------
        rou_total = bs["rou_asset"][col]
        non_kestrel = [e for e in live if e not in KESTREL_ENTITIES]
        w = np.array([max(drv.get(e, 0.0), 0.05) for e in non_kestrel])
        natural = allocate_exact(rou_total, w, 6)
        for e, amt in zip(non_kestrel, natural):
            out[e]["158100"] = amt
            out[e]["220400"] = -amt * 0.22
            out[e]["230400"] = -amt * 0.78

        # ---- finance leases -------------------------------------------------
        fl = bs["finance_lease"][col]
        w = np.array([max(drv.get(e, 0.0), 0.05) * CAPEX_WEIGHT.get(e, 1.0) for e in live])
        for e, amt in zip(live, allocate_exact(fl, w, 6)):
            out[e]["220300"] = -amt * 0.24
            out[e]["230300"] = -amt * 0.76

        # ---- external debt sits with Topco treasury -------------------------
        out["NIG-100"]["230100"] = -bs["tlb_gross"][col]
        out["NIG-100"]["230200"] = bs["dff"][col]
        out["NIG-100"]["220200"] = -bs["rcf"][col]

        # ---- intercompany balances -----------------------------------------
        loans = {b: n for b, (c, n) in IC_LOAN_NOTIONAL.items() if self.live(b, col)}
        scale = ic["ic_loan_close"][col] / max(sum(loans.values()), 1e-9)
        for b, notional in loans.items():
            amt = notional * scale
            out[b]["235100"] = out[b].get("235100", 0.0) - amt
            out["NIG-100"]["175100"] = out["NIG-100"].get("175100", 0.0) + amt

        ic_bal = ic["ic_ar_ap_close"][col]
        flows = self.m.ic_flows_usd(col)
        by_seller: dict[str, float] = {}
        by_buyer: dict[str, float] = {}
        for f in flows:
            if f["kind"] == "INTEREST":
                continue
            by_seller[f["seller"]] = by_seller.get(f["seller"], 0.0) + f["amount_usd"]
            by_buyer[f["buyer"]] = by_buyer.get(f["buyer"], 0.0) + f["amount_usd"]
        tot = max(sum(by_seller.values()), 1e-9)
        for e, v in by_seller.items():
            out[e]["120500"] = out[e].get("120500", 0.0) + ic_bal * v / tot
        for e, v in by_buyer.items():
            out[e]["210500"] = out[e].get("210500", 0.0) - ic_bal * v / tot

        # ---- equity ---------------------------------------------------------
        for e in live:
            cap = ENTITY_CAPITAL[e]
            out[e]["310100"] = -cap * 0.10
            out[e]["310200"] = -cap * 0.90
        # Sponsor equity contributions are cumulative additional paid-in capital at Topco.
        # FY2023 carried a USD 20.0m contribution to part-fund the Halden acquisition.
        cum_contrib = sum(self.m.cf_anchor["equity_contribution"][c]
                          for c in ("FY2023A", "FY2024A", "FY2025A")
                          if int(c[2:6]) <= (2026 if col.startswith("FY2026") else int(col[2:6])))
        out["NIG-100"]["310200"] = out["NIG-100"].get("310200", 0.0) - cum_contrib

        # Investment in subsidiaries is held at cost.  The absolute level is calibrated so
        # that the difference between the parents' investment and the subsidiaries' net
        # assets equals the anchored purchase-price allocation -- which is exactly what the
        # Phase 4 investment elimination will recompute as goodwill and intangibles.
        adj = self.investment_adjustment.get(col, 0.0)
        total_inv = sum(a for (pp, ss), a in INVESTMENTS.items()
                        if self.live(pp, col) and self.live(ss, col))
        factor = 1.0 + (adj / total_inv if total_inv else 0.0)
        for (parent, sub), amt in INVESTMENTS.items():
            if self.live(parent, col) and self.live(sub, col):
                out[parent]["178100"] = out[parent].get("178100", 0.0) + amt * factor

        self._cache[("bs", col)] = out
        return out
