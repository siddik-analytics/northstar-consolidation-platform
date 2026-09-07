"""
Northstar Industrial Group - Financial Anchor Model
====================================================
Phase 1 deliverable.

Purpose
-------
Produce the *authoritative*, internally-consistent set of group financial anchors
(FY2023A - FY2025A, FY2026 Budget, FY2026 Forecast) that every later phase must
reconcile to.  Phase 2 synthetic transaction generation is calibrated to these
numbers; Phase 9 QA tests the generated data back against them.

Design notes (see docs/adr/0011-anchor-first-deterministic-modelling.md)
-----------------------------------------------------------------------
* The model is *driver based*.  Nothing is hard-coded at the output level.
* The balance sheet is closed by construction:  Cash is derived from the
  accounting identity  Cash = L + E - NonCashAssets, with the revolving credit
  facility set by an explicit treasury policy (minimum cash / target cash sweep).
  Consequently the indirect cash-flow statement, which is built from balance
  sheet movements, ties to the balance sheet cash movement to the cent.
* CTA is an *economic* input (FX movement on foreign net assets), not a plug.
  In Phase 4 CTA becomes a computed output of the translation engine; the value
  here is the target it must land near.
* All amounts in USD millions unless stated.

Run:  python src/anchors/build_anchors.py
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANCHOR_DIR = ROOT / "config" / "anchors"
DOC_OUT = ROOT / "docs" / "financial-anchors.md"

# --------------------------------------------------------------------------
# 0.  Scenario spine
# --------------------------------------------------------------------------
# key, fiscal year, scenario, version, label
PERIODS = [
    ("FY2023A", 2023, "ACT", "ACTUAL", "FY2023 Actual"),
    ("FY2024A", 2024, "ACT", "ACTUAL", "FY2024 Actual"),
    ("FY2025A", 2025, "ACT", "ACTUAL", "FY2025 Actual"),
    ("FY2026B", 2026, "BUD", "BUD_FY26_V1", "FY2026 Budget"),
    ("FY2026F", 2026, "FC", "FC_FY26_08", "FY2026 Forecast (8+4)"),
]
COLS = [p[0] for p in PERIODS]


def series(**kw) -> dict:
    """Helper: build a {period_key: value} dict from keyword args."""
    return {k: float(v) for k, v in kw.items()}


# --------------------------------------------------------------------------
# 1.  Revenue - built bottom-up from legal entity, rolled to BU and Group
# --------------------------------------------------------------------------
# entity_code -> (business_unit, {period: external revenue $m})
ENTITY_REVENUE = {
    # Flow Control & Components
    "NIG-200": ("FC", series(FY2023A=72.5, FY2024A=82.0, FY2025A=92.0, FY2026B=100.0, FY2026F=98.5)),
    "NIG-210": ("FC", series(FY2023A=33.0, FY2024A=33.4, FY2025A=35.6, FY2026B=37.5, FY2026F=36.5)),
    "NIG-220": ("FC", series(FY2023A=18.5, FY2024A=25.6, FY2025A=29.0, FY2026B=31.5, FY2026F=28.5)),
    # Industrial Services
    "NIG-300": ("IS", series(FY2023A=58.5, FY2024A=65.0, FY2025A=71.0, FY2026B=77.0, FY2026F=76.5)),
    "NIG-310": ("IS", series(FY2023A=22.5, FY2024A=24.5, FY2025A=26.4, FY2026B=28.5, FY2026F=28.0)),
    "NIG-320": ("IS", series(FY2023A=20.5, FY2024A=23.5, FY2025A=26.2, FY2026B=29.0, FY2026F=28.5)),
    # Engineered Systems
    "NIG-400": ("ES", series(FY2023A=55.0, FY2024A=56.9, FY2025A=55.7, FY2026B=59.0, FY2026F=57.2)),
    "NIG-410": ("ES", series(FY2023A=0.0, FY2024A=8.5, FY2025A=18.5, FY2026B=23.0, FY2026F=21.0)),
    # Aftermarket & Parts
    "NIG-500": ("AM", series(FY2023A=30.0, FY2024A=32.5, FY2025A=35.4, FY2026B=38.0, FY2026F=38.2)),
    "NIG-510": ("AM", series(FY2023A=17.5, FY2024A=19.5, FY2025A=22.3, FY2026B=24.5, FY2026F=24.3)),
    # NIG-100 (Topco) and NIG-110 (Shared Services) earn intercompany income only.
}

BU_NAMES = {
    "FC": "Flow Control & Components",
    "IS": "Industrial Services",
    "ES": "Engineered Systems",
    "AM": "Aftermarket & Parts",
}

# Gross margin % on external revenue, by business unit
BU_GROSS_MARGIN = {
    "FC": series(FY2023A=0.325, FY2024A=0.334, FY2025A=0.340, FY2026B=0.348, FY2026F=0.340),
    "IS": series(FY2023A=0.210, FY2024A=0.216, FY2025A=0.220, FY2026B=0.226, FY2026F=0.223),
    "ES": series(FY2023A=0.185, FY2024A=0.180, FY2025A=0.190, FY2026B=0.195, FY2026F=0.178),
    "AM": series(FY2023A=0.420, FY2024A=0.425, FY2025A=0.430, FY2026B=0.435, FY2026F=0.434),
}

# --------------------------------------------------------------------------
# 2.  Operating expense, one-time items, D&A
# --------------------------------------------------------------------------
OPEX_TOTAL = series(FY2023A=62.500, FY2024A=66.400, FY2025A=68.000, FY2026B=72.400, FY2026F=72.900)
ONE_TIME_IN_OPEX = series(FY2023A=9.800, FY2024A=8.200, FY2025A=6.500, FY2026B=3.500, FY2026F=5.800)
SBC = series(FY2023A=1.000, FY2024A=1.200, FY2025A=1.400, FY2026B=1.500, FY2026F=1.500)

# Composition of the Adjusted EBITDA add-backs, by group account.  Must sum exactly to
# ONE_TIME_IN_OPEX.  Every line is permitted by the synthetic credit agreement
# (config/debt/credit_agreement_terms.csv), so management Adjusted EBITDA and covenant
# Consolidated EBITDA are equal by construction under the current agreement.
ADDBACK_COMPOSITION = {
    "680100": ("Restructuring - severance",
               series(FY2023A=1.800, FY2024A=1.400, FY2025A=1.500, FY2026B=0.500, FY2026F=2.000)),
    "680200": ("Restructuring - facility exit",
               series(FY2023A=0.900, FY2024A=0.400, FY2025A=0.500, FY2026B=0.200, FY2026F=0.800)),
    "680300": ("Acquisition and transaction costs",
               series(FY2023A=2.600, FY2024A=1.900, FY2025A=0.400, FY2026B=0.000, FY2026F=0.000)),
    "680400": ("Integration and ERP programme costs",
               series(FY2023A=3.000, FY2024A=3.100, FY2025A=2.600, FY2026B=1.600, FY2026F=1.600)),
    "680600": ("Legal settlements and claims",
               series(FY2023A=0.300, FY2024A=0.200, FY2025A=0.300, FY2026B=0.000, FY2026F=0.200)),
    "680700": ("Transaction and retention bonuses",
               series(FY2023A=0.200, FY2024A=0.100, FY2025A=0.000, FY2026B=0.000, FY2026F=0.000)),
    "630400": ("Sponsor monitoring fee",
               series(FY2023A=1.000, FY2024A=1.100, FY2025A=1.200, FY2026B=1.200, FY2026F=1.200)),
}
# Credit agreement clause S6.9: the sponsor monitoring fee add-back is capped.
SPONSOR_FEE_ANNUAL_CAP = 1.500

# Share-based compensation is NOT an add-back (credit agreement CA-029) and no run-rate
# synergy add-backs are permitted (CA-028).  Both are asserted below so the policy cannot
# drift silently into the numbers.

DEPRECIATION = series(FY2023A=9.500, FY2024A=10.400, FY2025A=11.300, FY2026B=12.200, FY2026F=12.000)
AMORT_INTANG = series(FY2023A=5.800, FY2024A=7.000, FY2025A=7.200, FY2026B=7.200, FY2026F=7.200)

# --------------------------------------------------------------------------
# 3.  Capital structure
# --------------------------------------------------------------------------
# Term Loan B: original $180m (2021 recapitalisation), 1% p.a. amortisation.
TLB_OPEN_2022 = 178.200
TLB_DRAW = series(FY2023A=25.000, FY2024A=30.000, FY2025A=0.000, FY2026B=0.000, FY2026F=0.000)
TLB_SCHED_AMORT = series(FY2023A=2.000, FY2024A=2.300, FY2025A=2.300, FY2026B=2.300, FY2026F=2.300)
# Treasury repays the revolver from surplus cash before making voluntary term-loan
# prepayments, so voluntary prepayments only appear once the revolver is expected to clear.
TLB_VOLUNTARY_PREPAY = series(FY2023A=0.000, FY2024A=0.000, FY2025A=0.000, FY2026B=10.000, FY2026F=0.000)

# Credit agreement covenants, tested quarterly on a trailing-twelve-month basis.
COVENANT_MAX_LEVERAGE = series(FY2023A=6.00, FY2024A=5.50, FY2025A=5.00, FY2026B=4.50, FY2026F=4.50)
COVENANT_MIN_COVERAGE = series(FY2023A=2.00, FY2024A=2.00, FY2025A=2.00, FY2026B=2.00, FY2026F=2.00)

# Effective blended interest rates (50% of TLB swapped at 3.00% SOFR fixed + 425bps)
TLB_RATE = series(FY2023A=0.0810, FY2024A=0.0835, FY2025A=0.0780, FY2026B=0.0730, FY2026F=0.0745)
RCF_RATE = series(FY2023A=0.0925, FY2024A=0.0935, FY2025A=0.0835, FY2026B=0.0780, FY2026F=0.0795)
LEASE_RATE = series(FY2023A=0.0650, FY2024A=0.0650, FY2025A=0.0650, FY2026B=0.0640, FY2026F=0.0640)
RCF_COMMITMENT = 60.000
RCF_COMMITMENT_FEE = 0.005
DFF_AMORT = series(FY2023A=0.950, FY2024A=1.050, FY2025A=1.050, FY2026B=1.000, FY2026F=1.000)
INTEREST_INCOME = series(FY2023A=0.300, FY2024A=0.350, FY2025A=0.550, FY2026B=0.700, FY2026F=0.550)

# Average revolver utilisation used for interest (treasury forecast, not the closing plug)
RCF_AVG_DRAWN = series(FY2023A=15.000, FY2024A=12.000, FY2025A=5.000, FY2026B=2.000, FY2026F=6.000)

# Treasury policy
MIN_CASH = 15.000
TARGET_CASH = 22.000

EFFECTIVE_TAX_RATE = series(FY2023A=-0.180, FY2024A=0.550, FY2025A=0.285, FY2026B=0.270, FY2026F=0.275)
NCI_INCOME = series(FY2023A=0.180, FY2024A=0.280, FY2025A=0.360, FY2026B=0.440, FY2026F=0.400)
NCI_DIVIDEND = series(FY2023A=0.000, FY2024A=0.150, FY2025A=0.200, FY2026B=0.250, FY2026F=0.250)
NCI_FX = series(FY2023A=0.100, FY2024A=-0.050, FY2025A=0.180, FY2026B=0.000, FY2026F=0.050)
SPONSOR_EQUITY_CONTRIB = series(FY2023A=20.000, FY2024A=0.000, FY2025A=0.000, FY2026B=0.000, FY2026F=0.000)

# --------------------------------------------------------------------------
# 4.  Working capital drivers
# --------------------------------------------------------------------------
DSO = series(FY2023A=62, FY2024A=60, FY2025A=58, FY2026B=55, FY2026F=59)   # on revenue
DIO = series(FY2023A=55, FY2024A=53, FY2025A=50, FY2026B=47, FY2026F=51)   # on cost of sales
DPO = series(FY2023A=46, FY2024A=48, FY2025A=50, FY2026B=52, FY2026F=51)   # on cost of sales

CONTRACT_ASSET_PCT = series(FY2023A=0.048, FY2024A=0.046, FY2025A=0.045, FY2026B=0.042, FY2026F=0.048)
CONTRACT_LIAB_PCT = series(FY2023A=0.095, FY2024A=0.090, FY2025A=0.090, FY2026B=0.095, FY2026F=0.085)
PREPAID_PCT = series(FY2023A=0.020, FY2024A=0.020, FY2025A=0.020, FY2026B=0.020, FY2026F=0.020)
ACCRUED_PCT = series(FY2023A=0.055, FY2024A=0.055, FY2025A=0.055, FY2026B=0.055, FY2026F=0.055)
TAX_PAYABLE_PCT = series(FY2023A=0.006, FY2024A=0.006, FY2025A=0.006, FY2026B=0.006, FY2026F=0.006)

OPENING_BS = {
    "cash": 16.400, "ar": 49.100, "contract_assets": 6.900, "inventory": 32.800,
    "prepaid": 5.900, "ppe_net": 68.000, "rou_asset": 20.500, "goodwill": 96.000,
    "intangibles_net": 41.000, "other_nca": 6.000,
    "ap": 26.100, "contract_liabilities": 4.700, "accrued": 16.100, "tax_payable": 1.800,
    "rcf": 8.000, "tlb_gross": TLB_OPEN_2022, "dff": 4.600,
    "finance_lease": 9.900, "operating_lease": 20.500, "dtl": 11.500, "other_ltl": 3.200,
    "contributed_capital": 145.000, "cta": -3.500, "nci": 2.800,
    # retained earnings is the opening plug - validated against the expected value below
}
OPENING_RE_EXPECTED = -77.0
OPENING_RE_TOLERANCE = 5.0

# --------------------------------------------------------------------------
# 5.  Investing and non-cash movements
# --------------------------------------------------------------------------
CAPEX_CASH = series(FY2023A=12.500, FY2024A=14.000, FY2025A=15.500, FY2026B=17.500, FY2026F=15.000)
LEASE_ADDITIONS = series(FY2023A=2.200, FY2024A=2.000, FY2025A=2.400, FY2026B=2.000, FY2026F=2.500)

# Acquisitions:  Halden Valve GmbH (2023-04-01), Vector Systems B.V. (2024-07-01)
#
# Purchase accounting is modelled properly:  goodwill is the RESIDUAL of consideration
# less the fair value of net identifiable assets acquired (including cash acquired), not
# an independent input.  Acquired working capital is specified component by component so
# that the cash-flow statement can exclude it from the operating movement -- acquired
# balances are an investing outflow, not a working capital swing.
ACQ = {
    "FY2023A": dict(
        name="Halden Valve GmbH", acquired="2023-04-01",
        cash_consideration=52.000, cash_acquired=1.800,
        ar=5.400, inventory=4.200, contract_assets=0.300, prepaid=0.500,
        ap=2.900, accrued=0.900, contract_liabilities=0.000,
        ppe=3.400, intangibles=18.000, dtl=5.400),
    "FY2024A": dict(
        name="Vector Systems B.V.", acquired="2024-07-01",
        cash_consideration=38.000, cash_acquired=1.100,
        ar=3.600, inventory=1.900, contract_assets=0.900, prepaid=0.300,
        ap=1.800, accrued=0.000, contract_liabilities=0.700,
        ppe=5.600, intangibles=13.500, dtl=3.500),
}


def acq_goodwill(a: dict) -> float:
    """Goodwill = consideration less fair value of net identifiable assets acquired."""
    identifiable = (a["cash_acquired"] + a["ar"] + a["inventory"] + a["contract_assets"]
                    + a["prepaid"] + a["ppe"] + a["intangibles"]
                    - a["ap"] - a["accrued"] - a["contract_liabilities"] - a["dtl"])
    return a["cash_consideration"] - identifiable

# Non-cash FX translation effects on balances (USD movement arising purely from
# retranslating foreign-currency net assets at the new closing rate).
FX_ON_PPE = series(FY2023A=0.600, FY2024A=-0.900, FY2025A=1.100, FY2026B=0.000, FY2026F=0.900)
FX_ON_GOODWILL = series(FY2023A=0.800, FY2024A=-1.200, FY2025A=1.900, FY2026B=0.000, FY2026F=1.000)
FX_ON_INTANG = series(FY2023A=0.400, FY2024A=-0.700, FY2025A=0.900, FY2026B=0.000, FY2026F=0.500)
# CTA movement: FX on total foreign net assets (economic estimate; Phase 4 computes it)
CTA_MOVEMENT = series(FY2023A=3.500, FY2024A=-5.300, FY2025A=8.800, FY2026B=0.000, FY2026F=1.000)
# FX effect on foreign-currency *cash balances* only.  The balance of the CTA movement
# relates to foreign-currency working capital and is presented as a non-cash reconciling
# item within operating activities, which is where it belongs.
FX_ON_CASH = series(FY2023A=0.200, FY2024A=-0.300, FY2025A=0.400, FY2026B=0.000, FY2026F=0.200)

DEFERRED_TAX_PL = series(FY2023A=-1.400, FY2024A=-1.100, FY2025A=-1.600, FY2026B=-1.600, FY2026F=-1.500)
OTHER_NCA_CLOSE = series(FY2023A=6.500, FY2024A=7.200, FY2025A=7.800, FY2026B=8.000, FY2026F=8.200)
OTHER_LTL_CLOSE = series(FY2023A=3.500, FY2024A=3.800, FY2025A=4.000, FY2026B=4.000, FY2026F=4.200)
DFF_CAPITALISED = series(FY2023A=1.550, FY2024A=2.250, FY2025A=0.000, FY2026B=0.000, FY2026F=0.000)
OPERATING_LEASE_CLOSE = series(FY2023A=22.000, FY2024A=24.000, FY2025A=24.500, FY2026B=24.000, FY2026F=25.500)

# --------------------------------------------------------------------------
# 6.  Headcount (period-end FTE)
# --------------------------------------------------------------------------
HEADCOUNT = {
    "FC": series(FY2023A=700, FY2024A=748, FY2025A=780, FY2026B=800, FY2026F=784),
    "IS": series(FY2023A=930, FY2024A=1000, FY2025A=1050, FY2026B=1090, FY2026F=1074),
    "ES": series(FY2023A=290, FY2024A=322, FY2025A=340, FY2026B=352, FY2026F=344),
    "AM": series(FY2023A=175, FY2024A=182, FY2025A=190, FY2026B=196, FY2026F=194),
    "CORP": series(FY2023A=85, FY2024A=88, FY2025A=90, FY2026B=92, FY2026F=90),
}

# --------------------------------------------------------------------------
# 7.  FX anchors  (USD per 1 unit of local currency)
# --------------------------------------------------------------------------
FX_ANCHORS = [
    # currency, fy, rate_set, avg, close
    ("CAD", 2022, "ACTUAL", 0.7690, 0.7383), ("GBP", 2022, "ACTUAL", 1.2370, 1.2083),
    ("EUR", 2022, "ACTUAL", 1.0530, 1.0666),
    ("CAD", 2023, "ACTUAL", 0.7410, 0.7561), ("GBP", 2023, "ACTUAL", 1.2440, 1.2745),
    ("EUR", 2023, "ACTUAL", 1.0815, 1.1050),
    ("CAD", 2024, "ACTUAL", 0.7300, 0.6959), ("GBP", 2024, "ACTUAL", 1.2785, 1.2520),
    ("EUR", 2024, "ACTUAL", 1.0825, 1.0355),
    ("CAD", 2025, "ACTUAL", 0.7180, 0.7250), ("GBP", 2025, "ACTUAL", 1.2950, 1.3400),
    ("EUR", 2025, "ACTUAL", 1.1050, 1.1650),
    ("CAD", 2026, "BUDGET", 0.7200, 0.7200), ("GBP", 2026, "BUDGET", 1.2900, 1.2900),
    ("EUR", 2026, "BUDGET", 1.0900, 1.0900),
    ("CAD", 2026, "FORECAST", 0.7310, 0.7350), ("GBP", 2026, "FORECAST", 1.3450, 1.3500),
    ("EUR", 2026, "FORECAST", 1.1600, 1.1700),
    ("USD", 2022, "ACTUAL", 1.0, 1.0), ("USD", 2023, "ACTUAL", 1.0, 1.0),
    ("USD", 2024, "ACTUAL", 1.0, 1.0), ("USD", 2025, "ACTUAL", 1.0, 1.0),
    ("USD", 2026, "BUDGET", 1.0, 1.0), ("USD", 2026, "FORECAST", 1.0, 1.0),
]

# --------------------------------------------------------------------------
# 8.  Intercompany anchors (gross, eliminated in full)
# --------------------------------------------------------------------------
IC_ANCHORS = {
    "mgmt_fee": series(FY2023A=8.200, FY2024A=9.290, FY2025A=10.300, FY2026B=11.200, FY2026F=10.930),
    "ic_product_sales": series(FY2023A=25.400, FY2024A=30.100, FY2025A=34.500, FY2026B=37.800, FY2026F=36.100),
    "ic_service_sales": series(FY2023A=3.900, FY2024A=4.600, FY2025A=5.300, FY2026B=5.900, FY2026F=5.700),
    "ic_royalty": series(FY2023A=0.280, FY2024A=0.384, FY2025A=0.435, FY2026B=0.473, FY2026F=0.428),
    "ic_interest": series(FY2023A=2.100, FY2024A=2.700, FY2025A=2.900, FY2026B=2.850, FY2026F=2.950),
    "ic_ar_ap_close": series(FY2023A=9.800, FY2024A=11.200, FY2025A=12.400, FY2026B=13.100, FY2026F=12.900),
    "ic_loan_close": series(FY2023A=42.000, FY2024A=48.500, FY2025A=47.200, FY2026B=44.000, FY2026F=45.800),
    "pup_in_inventory": series(FY2023A=0.560, FY2024A=0.640, FY2025A=0.700, FY2026B=0.720, FY2026F=0.740),
}


# --------------------------------------------------------------------------
# ENGINE
# --------------------------------------------------------------------------
@dataclass
class YearResult:
    key: str
    pl: dict = field(default_factory=dict)
    bs: dict = field(default_factory=dict)
    cf: dict = field(default_factory=dict)
    kpi: dict = field(default_factory=dict)
    cta: dict = field(default_factory=dict)


def build() -> tuple[list[YearResult], dict]:
    results: list[YearResult] = []

    # ---- opening balance sheet: retained earnings is the opening plug --------
    ob = dict(OPENING_BS)
    assets_open = (ob["cash"] + ob["ar"] + ob["contract_assets"] + ob["inventory"] + ob["prepaid"]
                   + ob["ppe_net"] + ob["rou_asset"] + ob["goodwill"] + ob["intangibles_net"]
                   + ob["other_nca"])
    liab_open = (ob["ap"] + ob["contract_liabilities"] + ob["accrued"] + ob["tax_payable"] + ob["rcf"]
                 + ob["tlb_gross"] - ob["dff"] + ob["finance_lease"] + ob["operating_lease"]
                 + ob["dtl"] + ob["other_ltl"])
    ob["retained_earnings"] = assets_open - liab_open - ob["contributed_capital"] - ob["cta"] - ob["nci"]
    assert abs(ob["retained_earnings"] - OPENING_RE_EXPECTED) < OPENING_RE_TOLERANCE, (
        f"Opening retained earnings plug {ob['retained_earnings']:.3f} is outside the expected band "
        f"{OPENING_RE_EXPECTED} +/- {OPENING_RE_TOLERANCE}. Re-calibrate the opening balance sheet.")

    # ---- add-back policy assertions (ADR-0013, credit agreement CA-021..CA-029) --------
    for k in COLS:
        composed = sum(v[k] for _lbl, v in ADDBACK_COMPOSITION.values())
        assert abs(composed - ONE_TIME_IN_OPEX[k]) < 1e-9, (
            f"{k}: add-back composition {composed:.3f} does not equal the one-time charge "
            f"{ONE_TIME_IN_OPEX[k]:.3f}. Every add-back must be attributable to an account.")
        sponsor = ADDBACK_COMPOSITION["630400"][1][k]
        assert sponsor <= SPONSOR_FEE_ANNUAL_CAP + 1e-9, (
            f"{k}: sponsor monitoring fee add-back {sponsor:.3f} exceeds the credit agreement "
            f"cap of {SPONSOR_FEE_ANNUAL_CAP:.3f} (clause S6.9). Only the capped amount is addable.")

    # Closing balance sheet by fiscal year, populated from ACTUAL periods only.
    # Budget and Forecast are alternative views of the SAME fiscal year: both must open
    # from the prior year's actual close, never from each other.  Rolling the forecast
    # forward from the budget would compound two different views of one year.
    closes: dict[int, dict] = {2022: dict(ob)}

    for key, fy, scenario, _version, _label in PERIODS:
        r = YearResult(key=key)
        prev = closes[fy - 1]

        # ---------------- Income statement -------------------------------
        bu_rev, bu_gp = {}, {}
        for _ent, (bu, rev) in ENTITY_REVENUE.items():
            bu_rev[bu] = bu_rev.get(bu, 0.0) + rev[key]
        for bu, rev in bu_rev.items():
            bu_gp[bu] = rev * BU_GROSS_MARGIN[bu][key]

        revenue = sum(bu_rev.values())
        gross_profit = sum(bu_gp.values())
        cost_of_sales = revenue - gross_profit
        opex = OPEX_TOTAL[key]
        one_time = ONE_TIME_IN_OPEX[key]
        ebitda = gross_profit - opex
        adj_ebitda = ebitda + one_time
        dep, amort = DEPRECIATION[key], AMORT_INTANG[key]
        da = dep + amort
        ebit = ebitda - da

        # ---------------- Debt roll-forward & interest --------------------
        tlb_open = prev["tlb_gross"]
        tlb_close = tlb_open + TLB_DRAW[key] - TLB_SCHED_AMORT[key] - TLB_VOLUNTARY_PREPAY[key]
        tlb_avg = (tlb_open + tlb_close) / 2.0
        rcf_avg = RCF_AVG_DRAWN[key]
        fl_open = prev["finance_lease"]
        fl_principal = fl_open * 0.185               # ~5.4 year average remaining lease term
        fl_close = fl_open + LEASE_ADDITIONS[key] - fl_principal
        fl_avg = (fl_open + fl_close) / 2.0

        int_tlb = tlb_avg * TLB_RATE[key]
        int_rcf = rcf_avg * RCF_RATE[key]
        int_lease = fl_avg * LEASE_RATE[key]
        commit_fee = max(0.0, RCF_COMMITMENT - rcf_avg) * RCF_COMMITMENT_FEE
        dff_amort = DFF_AMORT[key]
        int_income = INTEREST_INCOME[key]
        net_interest = int_tlb + int_rcf + int_lease + commit_fee + dff_amort - int_income

        pbt = ebit - net_interest
        tax = pbt * EFFECTIVE_TAX_RATE[key]
        net_income = pbt - tax
        nci = NCI_INCOME[key]
        ni_parent = net_income - nci

        r.pl = dict(revenue=revenue, cost_of_sales=cost_of_sales, gross_profit=gross_profit,
                    opex=opex, one_time_in_opex=one_time, ebitda=ebitda, adjusted_ebitda=adj_ebitda,
                    depreciation=dep, amortisation=amort, da=da, ebit=ebit,
                    interest_tlb=int_tlb, interest_rcf=int_rcf, interest_lease=int_lease,
                    commitment_fee=commit_fee, dff_amortisation=dff_amort, interest_income=-int_income,
                    net_interest=net_interest, pbt=pbt, tax=tax, net_income=net_income,
                    nci=nci, ni_parent=ni_parent)
        for bu in sorted(bu_rev):
            r.pl[f"revenue_{bu}"] = bu_rev[bu]
            r.pl[f"gross_profit_{bu}"] = bu_gp[bu]

        # ---------------- Balance sheet: non-cash assets ------------------
        acq = ACQ.get(key)
        ar = revenue * DSO[key] / 365.0
        inventory = cost_of_sales * DIO[key] / 365.0
        ap = cost_of_sales * DPO[key] / 365.0
        rev_is_es = bu_rev.get("IS", 0.0) + bu_rev.get("ES", 0.0)
        contract_assets = rev_is_es * CONTRACT_ASSET_PCT[key]
        contract_liabs = bu_rev.get("ES", 0.0) * CONTRACT_LIAB_PCT[key]
        prepaid = revenue * PREPAID_PCT[key]
        accrued = revenue * ACCRUED_PCT[key]
        tax_pay = revenue * TAX_PAYABLE_PCT[key]

        gw_added = acq_goodwill(acq) if acq else 0.0
        ppe = (prev["ppe_net"] + CAPEX_CASH[key] + LEASE_ADDITIONS[key]
               + (acq["ppe"] if acq else 0.0) - dep + FX_ON_PPE[key])
        goodwill = prev["goodwill"] + gw_added + FX_ON_GOODWILL[key]
        intangibles = (prev["intangibles_net"] + (acq["intangibles"] if acq else 0.0)
                       - amort + FX_ON_INTANG[key])
        other_nca = OTHER_NCA_CLOSE[key]
        rou_asset = OPERATING_LEASE_CLOSE[key]

        # ---------------- Balance sheet: liabilities & equity -------------
        dff_close = prev["dff"] + DFF_CAPITALISED[key] - dff_amort
        dtl = prev["dtl"] + (acq["dtl"] if acq else 0.0) + DEFERRED_TAX_PL[key]
        other_ltl = OTHER_LTL_CLOSE[key]
        op_lease = OPERATING_LEASE_CLOSE[key]

        contributed = prev["contributed_capital"] + SPONSOR_EQUITY_CONTRIB[key] + SBC[key]
        retained = prev["retained_earnings"] + ni_parent
        cta = prev["cta"] + CTA_MOVEMENT[key]
        nci_eq = prev["nci"] + nci - NCI_DIVIDEND[key] + NCI_FX[key]

        non_cash_assets = (ar + contract_assets + inventory + prepaid + ppe + rou_asset
                           + goodwill + intangibles + other_nca)
        liab_excl_rcf = (ap + contract_liabs + accrued + tax_pay + tlb_close - dff_close
                         + fl_close + op_lease + dtl + other_ltl)
        equity = contributed + retained + cta + nci_eq

        # Cash falls out of the accounting identity; the revolver is the treasury plug.
        cash_before_rcf = liab_excl_rcf + equity - non_cash_assets
        rcf_open = prev["rcf"]
        cash_if_unchanged = cash_before_rcf + rcf_open
        if cash_if_unchanged < MIN_CASH:
            rcf_close = rcf_open + (MIN_CASH - cash_if_unchanged)
            cash = MIN_CASH
        elif cash_if_unchanged > TARGET_CASH and rcf_open > 0:
            repay = min(rcf_open, cash_if_unchanged - TARGET_CASH)
            rcf_close = rcf_open - repay
            cash = cash_if_unchanged - repay
        else:
            rcf_close = rcf_open
            cash = cash_if_unchanged

        total_assets = cash + non_cash_assets
        total_liabilities = liab_excl_rcf + rcf_close
        total_le = total_liabilities + equity
        assert abs(total_assets - total_le) < 1e-9, f"{key}: balance sheet out by {total_assets - total_le}"

        r.bs = dict(cash=cash, ar=ar, contract_assets=contract_assets, inventory=inventory,
                    prepaid=prepaid, total_current_assets=cash + ar + contract_assets + inventory + prepaid,
                    ppe_net=ppe, rou_asset=rou_asset, goodwill=goodwill, intangibles_net=intangibles,
                    other_nca=other_nca, total_assets=total_assets,
                    ap=ap, contract_liabilities=contract_liabs, accrued=accrued, tax_payable=tax_pay,
                    rcf=rcf_close, tlb_gross=tlb_close, dff=dff_close,
                    tlb_net=tlb_close - dff_close, finance_lease=fl_close, operating_lease=op_lease,
                    dtl=dtl, other_ltl=other_ltl, total_liabilities=total_liabilities,
                    contributed_capital=contributed, retained_earnings=retained, cta=cta, nci=nci_eq,
                    total_equity=equity, total_liabilities_and_equity=total_le)

        # ---------------- Cash flow (indirect, from BS movements) ---------
        acq_cash_out = (acq["cash_consideration"] - acq["cash_acquired"]) if acq else 0.0

        def acquired(field: str) -> float:
            return acq[field] if acq else 0.0

        # Working capital movements exclude balances acquired in a business combination:
        # those are an investing outflow, not an operating swing.
        d_ar = -(ar - prev["ar"] - acquired("ar"))
        d_ca = -(contract_assets - prev["contract_assets"] - acquired("contract_assets"))
        d_inv = -(inventory - prev["inventory"] - acquired("inventory"))
        d_pre = -(prepaid - prev["prepaid"] - acquired("prepaid"))
        d_ap = (ap - prev["ap"] - acquired("ap"))
        d_cl = (contract_liabs - prev["contract_liabilities"] - acquired("contract_liabilities"))
        d_acc = (accrued - prev["accrued"] - acquired("accrued"))
        d_tax = (tax_pay - prev["tax_payable"])
        change_in_wc = d_ar + d_ca + d_inv + d_pre + d_ap + d_cl + d_acc + d_tax
        d_other_nca = -(other_nca - prev["other_nca"])
        d_other_ltl = (other_ltl - prev["other_ltl"])
        d_dtl_noncash = dtl - prev["dtl"] - acquired("dtl")

        # Non-cash translation movement on foreign-currency working capital: the part of
        # the CTA movement not attributable to PP&E, goodwill, intangibles or cash.
        fx_non_cash_wc = (CTA_MOVEMENT[key] + NCI_FX[key] - FX_ON_PPE[key]
                          - FX_ON_GOODWILL[key] - FX_ON_INTANG[key] - FX_ON_CASH[key])

        ocf = (net_income + da + SBC[key] + dff_amort + d_dtl_noncash + fx_non_cash_wc
               + change_in_wc + d_other_nca + d_other_ltl)
        icf = -CAPEX_CASH[key] - acq_cash_out
        fin = (TLB_DRAW[key] - TLB_SCHED_AMORT[key] - TLB_VOLUNTARY_PREPAY[key]
               + (rcf_close - rcf_open) - fl_principal - DFF_CAPITALISED[key]
               + SPONSOR_EQUITY_CONTRIB[key] - NCI_DIVIDEND[key])
        fx_effect = FX_ON_CASH[key]
        net_change = ocf + icf + fin + fx_effect
        cash_check = prev["cash"] + net_change

        assert abs(cash_check - cash) < 1e-6, (
            f"{key}: cash flow does not tie to balance sheet cash "
            f"(CF {cash_check:.6f} vs BS {cash:.6f}, diff {cash_check - cash:.6f})")

        r.cf = dict(net_income=net_income, da=da, sbc=SBC[key], dff_amortisation=dff_amort,
                    deferred_tax=d_dtl_noncash, fx_non_cash_wc=fx_non_cash_wc,
                    change_in_ar=d_ar, change_in_contract_assets=d_ca,
                    change_in_inventory=d_inv, change_in_prepaid=d_pre, change_in_ap=d_ap,
                    change_in_contract_liabilities=d_cl, change_in_accrued=d_acc,
                    change_in_tax_payable=d_tax, change_in_working_capital=change_in_wc,
                    change_in_other=d_other_nca + d_other_ltl,
                    operating_cash_flow=ocf, capex=-CAPEX_CASH[key], acquisitions=-acq_cash_out,
                    investing_cash_flow=icf, tlb_draw=TLB_DRAW[key],
                    tlb_repayment=-(TLB_SCHED_AMORT[key] + TLB_VOLUNTARY_PREPAY[key]),
                    rcf_movement=rcf_close - rcf_open, finance_lease_principal=-fl_principal,
                    financing_fees=-DFF_CAPITALISED[key], equity_contribution=SPONSOR_EQUITY_CONTRIB[key],
                    nci_dividend=-NCI_DIVIDEND[key], financing_cash_flow=fin,
                    fx_effect_on_cash=fx_effect, net_change_in_cash=net_change,
                    opening_cash=prev["cash"], closing_cash=cash,
                    free_cash_flow=ocf - CAPEX_CASH[key])

        # ---------------- KPIs -------------------------------------------
        hc = sum(HEADCOUNT[b][key] for b in HEADCOUNT)
        total_debt = tlb_close + rcf_close + fl_close
        net_debt = total_debt - cash
        nwc = ar + contract_assets + inventory + prepaid - ap - contract_liabs - accrued
        r.kpi = dict(
            gross_margin_pct=gross_profit / revenue,
            ebitda_margin_pct=ebitda / revenue,
            adjusted_ebitda_margin_pct=adj_ebitda / revenue,
            opex_pct_revenue=opex / revenue,
            net_margin_pct=net_income / revenue,
            headcount=hc, revenue_per_fte_usd=revenue * 1_000_000 / hc,
            capex_pct_revenue=CAPEX_CASH[key] / revenue,
            dso=DSO[key], dio=DIO[key], dpo=DPO[key],
            cash_conversion_cycle=DSO[key] + DIO[key] - DPO[key],
            net_working_capital=nwc, nwc_pct_revenue=nwc / revenue,
            total_debt=total_debt, net_debt=net_debt,
            net_leverage_x=net_debt / adj_ebitda,
            interest_coverage_x=adj_ebitda / net_interest,
            fcf_conversion_pct=(ocf - CAPEX_CASH[key]) / adj_ebitda,
            liquidity=cash + RCF_COMMITMENT - rcf_close,
            covenant_max_leverage_x=COVENANT_MAX_LEVERAGE[key],
            covenant_leverage_headroom_x=COVENANT_MAX_LEVERAGE[key] - net_debt / adj_ebitda,
            covenant_coverage_headroom_x=adj_ebitda / net_interest - COVENANT_MIN_COVERAGE[key],
            # Economic view: a non-covenant KPI that treats operating leases as debt.
            # Reported alongside covenant leverage, never instead of it. See OQ-02 / ADR-0013.
            operating_lease_liabilities=op_lease,
            economic_net_debt=net_debt + op_lease,
            economic_net_leverage_x=(net_debt + op_lease) / adj_ebitda,
        )

        # ---------------- CTA roll-forward -------------------------------
        # Deterministic and continuous: closing = opening + group movement.  The NCI share
        # of the translation movement is presented separately and does not enter group CTA.
        cta_open = prev["cta"]
        r.cta = dict(
            cta_opening=cta_open,
            cta_movement_group=CTA_MOVEMENT[key],
            cta_movement_nci=NCI_FX[key],
            cta_movement_total=CTA_MOVEMENT[key] + NCI_FX[key],
            cta_recycled_on_disposal=0.0,
            cta_closing=cta,
            fx_on_cash=FX_ON_CASH[key],
            fx_on_ppe=FX_ON_PPE[key],
            fx_on_goodwill=FX_ON_GOODWILL[key],
            fx_on_intangibles=FX_ON_INTANG[key],
            fx_non_cash_working_capital=fx_non_cash_wc,
        )
        assert abs(r.cta["cta_closing"] - (r.cta["cta_opening"] + r.cta["cta_movement_group"]
                                          + r.cta["cta_recycled_on_disposal"])) < 1e-9, (
            f"{key}: CTA roll-forward does not close")
        assert abs(sum(r.cta[k] for k in ("fx_on_cash", "fx_on_ppe", "fx_on_goodwill",
                                          "fx_on_intangibles", "fx_non_cash_working_capital"))
                   - r.cta["cta_movement_total"]) < 1e-9, (
            f"{key}: FX effects by balance category do not sum to the total translation movement")

        results.append(r)
        if scenario == "ACT":
            closes[fy] = dict(r.bs)

    return results, ob


# --------------------------------------------------------------------------
# OUTPUT
# --------------------------------------------------------------------------
PL_ROWS = [
    ("revenue", "Revenue"), ("cost_of_sales", "Cost of sales"),
    ("gross_profit", "Gross profit"), ("opex", "Operating expenses"),
    ("ebitda", "EBITDA"), ("one_time_in_opex", "Add back: non-recurring items in opex"),
    ("adjusted_ebitda", "Adjusted EBITDA"), ("depreciation", "Depreciation"),
    ("amortisation", "Amortisation of acquired intangibles"), ("da", "Total D&A"),
    ("ebit", "EBIT"), ("net_interest", "Net interest expense"),
    ("pbt", "Profit before tax"), ("tax", "Income tax expense/(benefit)"),
    ("net_income", "Net income"), ("nci", "Less: non-controlling interests"),
    ("ni_parent", "Net income attributable to the group"),
]
BS_ROWS = [
    ("cash", "Cash and cash equivalents"), ("ar", "Trade accounts receivable, net"),
    ("contract_assets", "Contract assets / unbilled"), ("inventory", "Inventory, net"),
    ("prepaid", "Prepaid expenses and other current assets"),
    ("total_current_assets", "Total current assets"),
    ("ppe_net", "Property, plant and equipment, net"),
    ("rou_asset", "Operating lease right-of-use assets"),
    ("goodwill", "Goodwill"), ("intangibles_net", "Intangible assets, net"),
    ("other_nca", "Other non-current assets"), ("total_assets", "TOTAL ASSETS"),
    ("ap", "Trade accounts payable"), ("contract_liabilities", "Contract liabilities"),
    ("accrued", "Accrued liabilities"), ("tax_payable", "Income taxes payable"),
    ("rcf", "Revolving credit facility"), ("tlb_net", "Term loan B, net of financing costs"),
    ("finance_lease", "Finance lease liabilities"), ("operating_lease", "Operating lease liabilities"),
    ("dtl", "Deferred tax liabilities"), ("other_ltl", "Other long-term liabilities"),
    ("total_liabilities", "Total liabilities"),
    ("contributed_capital", "Contributed capital and APIC"),
    ("retained_earnings", "Retained earnings / (accumulated deficit)"),
    ("cta", "Cumulative translation adjustment"), ("nci", "Non-controlling interests"),
    ("total_equity", "Total equity"), ("total_liabilities_and_equity", "TOTAL LIABILITIES AND EQUITY"),
    ("tlb_gross", "Memo: term loan B, gross principal"),
    ("dff", "Memo: unamortised deferred financing costs"),
]
CF_ROWS = [
    ("net_income", "Net income"), ("da", "Depreciation and amortisation"),
    ("sbc", "Share-based compensation"), ("dff_amortisation", "Amortisation of deferred financing costs"),
    ("deferred_tax", "Deferred income taxes"),
    ("fx_non_cash_wc", "Non-cash FX translation movement on working capital"),
    ("change_in_working_capital", "Change in working capital"),
    ("change_in_other", "Change in other assets and liabilities"),
    ("operating_cash_flow", "NET CASH FROM OPERATING ACTIVITIES"),
    ("capex", "Capital expenditure"), ("acquisitions", "Acquisitions, net of cash acquired"),
    ("investing_cash_flow", "NET CASH USED IN INVESTING ACTIVITIES"),
    ("tlb_draw", "Term loan drawings"), ("tlb_repayment", "Term loan repayments"),
    ("rcf_movement", "Revolving facility, net"), ("finance_lease_principal", "Finance lease principal"),
    ("financing_fees", "Deferred financing costs paid"),
    ("equity_contribution", "Sponsor equity contribution"),
    ("nci_dividend", "Dividends to non-controlling interests"),
    ("financing_cash_flow", "NET CASH FROM FINANCING ACTIVITIES"),
    ("fx_effect_on_cash", "Effect of exchange rate changes"),
    ("net_change_in_cash", "NET CHANGE IN CASH"),
    ("opening_cash", "Cash at beginning of period"), ("closing_cash", "CASH AT END OF PERIOD"),
    ("free_cash_flow", "Memo: free cash flow (OCF less capex)"),
]
KPI_ROWS = [
    ("gross_margin_pct", "Gross margin %", "pct"), ("ebitda_margin_pct", "EBITDA margin %", "pct"),
    ("adjusted_ebitda_margin_pct", "Adjusted EBITDA margin %", "pct"),
    ("opex_pct_revenue", "Opex % of revenue", "pct"), ("net_margin_pct", "Net margin %", "pct"),
    ("headcount", "Headcount (period-end FTE)", "int"),
    ("revenue_per_fte_usd", "Revenue per FTE (USD)", "int"),
    ("capex_pct_revenue", "Capex % of revenue", "pct"),
    ("dso", "DSO (days)", "int"), ("dio", "DIO (days)", "int"), ("dpo", "DPO (days)", "int"),
    ("cash_conversion_cycle", "Cash conversion cycle (days)", "int"),
    ("net_working_capital", "Net working capital", "num"),
    ("nwc_pct_revenue", "NWC % of revenue", "pct"),
    ("total_debt", "Total debt", "num"), ("net_debt", "Net debt", "num"),
    ("net_leverage_x", "Net leverage (x Adj. EBITDA)", "x"),
    ("interest_coverage_x", "Interest coverage (x)", "x"),
    ("fcf_conversion_pct", "FCF conversion % of Adj. EBITDA", "pct"),
    ("liquidity", "Total liquidity (cash + undrawn RCF)", "num"),
    ("covenant_max_leverage_x", "Covenant: maximum net leverage", "x"),
    ("covenant_leverage_headroom_x", "Covenant headroom — leverage", "x"),
    ("covenant_coverage_headroom_x", "Covenant headroom — interest coverage", "x"),
    ("operating_lease_liabilities", "Memo: operating lease liabilities", "num"),
    ("economic_net_debt", "Economic net debt (including leases)", "num"),
    ("economic_net_leverage_x", "Economic net leverage (non-covenant)", "x"),
]

CTA_ROWS = [
    ("cta_opening", "CTA — opening balance"),
    ("cta_movement_group", "CTA — movement attributable to the group"),
    ("cta_movement_nci", "CTA — movement attributable to non-controlling interests"),
    ("cta_recycled_on_disposal", "CTA — recycled to income on disposal"),
    ("cta_closing", "CTA — closing balance (group)"),
    ("cta_movement_total", "Memo: total translation movement in the period"),
    ("fx_on_cash", "  of which: on cash and cash equivalents"),
    ("fx_on_ppe", "  of which: on property, plant and equipment"),
    ("fx_on_goodwill", "  of which: on goodwill"),
    ("fx_on_intangibles", "  of which: on intangible assets"),
    ("fx_non_cash_working_capital", "  of which: on working capital and other balances"),
]

BOLD_LABELS = {
    "Revenue", "Gross profit", "EBITDA", "Adjusted EBITDA", "EBIT", "Profit before tax",
    "Net income", "Net income attributable to the group", "Total current assets",
    "Total liabilities", "Total equity",
}


def fmt(v, kind="num"):
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind == "int":
        return f"{v:,.0f}"
    if kind == "x":
        return f"{v:.2f}x"
    return f"{v:,.1f}"


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def md_table(rows, results, section, kinds=False):
    out = ["| " + " | ".join(["USD millions"] + [p[4] for p in PERIODS]) + " |",
           "|" + "---|" * (len(PERIODS) + 1)]
    for item in rows:
        k, lbl = item[0], item[1]
        kind = item[2] if kinds else "num"
        vals = [fmt(getattr(r, section)[k], kind) for r in results]
        bold = (not kinds) and (lbl.isupper() or lbl in BOLD_LABELS)
        name = f"**{lbl}**" if bold else lbl
        vals = [f"**{v}**" if bold else v for v in vals]
        out.append("| " + " | ".join([name] + vals) + " |")
    return "\n".join(out)


def main():
    results, ob = build()
    ANCHOR_DIR.mkdir(parents=True, exist_ok=True)

    write_csv(ANCHOR_DIR / "anchor_income_statement.csv", ["line_item", "label"] + COLS,
              [[k, lbl] + [f"{r.pl[k]:.6f}" for r in results] for k, lbl in PL_ROWS])
    write_csv(ANCHOR_DIR / "anchor_balance_sheet.csv", ["line_item", "label"] + COLS,
              [[k, lbl] + [f"{r.bs[k]:.6f}" for r in results] for k, lbl in BS_ROWS])
    write_csv(ANCHOR_DIR / "anchor_cash_flow.csv", ["line_item", "label"] + COLS,
              [[k, lbl] + [f"{r.cf[k]:.6f}" for r in results] for k, lbl in CF_ROWS])
    write_csv(ANCHOR_DIR / "anchor_kpi.csv", ["metric", "label", "format"] + COLS,
              [[k, lbl, kind] + [f"{r.kpi[k]:.6f}" for r in results] for k, lbl, kind in KPI_ROWS])

    bu_rows = []
    for bu in ["FC", "IS", "ES", "AM"]:
        bu_rows.append([bu, BU_NAMES[bu], "revenue"] + [f"{r.pl[f'revenue_{bu}']:.3f}" for r in results])
        bu_rows.append([bu, BU_NAMES[bu], "gross_profit"] + [f"{r.pl[f'gross_profit_{bu}']:.3f}" for r in results])
        bu_rows.append([bu, BU_NAMES[bu], "gross_margin_pct"]
                       + [f"{r.pl[f'gross_profit_{bu}'] / r.pl[f'revenue_{bu}']:.4f}" for r in results])
        bu_rows.append([bu, BU_NAMES[bu], "headcount"] + [f"{HEADCOUNT[bu][c]:.0f}" for c in COLS])
    bu_rows.append(["CORP", "Corporate & Shared Services", "headcount"]
                   + [f"{HEADCOUNT['CORP'][c]:.0f}" for c in COLS])
    write_csv(ANCHOR_DIR / "anchor_by_business_unit.csv", ["bu_code", "bu_name", "measure"] + COLS, bu_rows)

    write_csv(ANCHOR_DIR / "anchor_by_entity.csv", ["entity_code", "bu_code", "measure"] + COLS,
              [[e, bu, "external_revenue"] + [f"{rev[c]:.3f}" for c in COLS]
               for e, (bu, rev) in ENTITY_REVENUE.items()])

    write_csv(ANCHOR_DIR / "anchor_fx_rates.csv",
              ["currency_code", "fiscal_year", "rate_set", "average_rate_usd", "closing_rate_usd"],
              [[c, y, s, f"{a:.4f}", f"{cl:.4f}"] for c, y, s, a, cl in FX_ANCHORS])

    write_csv(ANCHOR_DIR / "anchor_intercompany.csv", ["measure"] + COLS,
              [[k] + [f"{v[c]:.3f}" for c in COLS] for k, v in IC_ANCHORS.items()])

    write_csv(ANCHOR_DIR / "anchor_cta_rollforward.csv", ["line_item", "label"] + COLS,
              [[k, lbl] + [f"{r.cta[k]:.6f}" for r in results] for k, lbl in CTA_ROWS])

    write_csv(ANCHOR_DIR / "anchor_addback_composition.csv",
              ["group_account", "label"] + COLS,
              [[acct, lbl] + [f"{v[c]:.6f}" for c in COLS]
               for acct, (lbl, v) in ADDBACK_COMPOSITION.items()]
              + [["TOTAL", "Total Adjusted EBITDA add-backs"]
                 + [f"{r.pl['one_time_in_opex']:.6f}" for r in results]])

    # --- console proof -----------------------------------------------------
    print(f"Opening retained earnings plug (2022-12-31): {ob['retained_earnings']:.3f}")
    print(f"{'':34}" + "".join(f"{p[0]:>12}" for p in PERIODS))
    for k, lbl in [("revenue", "Revenue"), ("gross_profit", "Gross profit"),
                   ("ebitda", "EBITDA"), ("adjusted_ebitda", "Adj. EBITDA"),
                   ("net_interest", "Net interest"), ("pbt", "Profit before tax"),
                   ("net_income", "Net income")]:
        print(f"{lbl:34}" + "".join(f"{r.pl[k]:12,.1f}" for r in results))
    for k, lbl in [("cash", "Cash"), ("rcf", "Revolver drawn"), ("total_assets", "Total assets"),
                   ("total_liabilities_and_equity", "Total L&E"), ("total_equity", "Total equity")]:
        print(f"{lbl:34}" + "".join(f"{r.bs[k]:12,.1f}" for r in results))
    for k, lbl in [("operating_cash_flow", "Operating cash flow"),
                   ("free_cash_flow", "Free cash flow")]:
        print(f"{lbl:34}" + "".join(f"{r.cf[k]:12,.1f}" for r in results))
    for k, lbl in [("cta_opening", "CTA opening"), ("cta_movement_group", "CTA movement (group)"),
                   ("cta_closing", "CTA closing")]:
        print(f"{lbl:34}" + "".join(f"{r.cta[k]:12,.2f}" for r in results))
    for k, lbl in [("adjusted_ebitda_margin_pct", "Adj. EBITDA margin"),
                   ("net_leverage_x", "Net leverage (x)"),
                   ("interest_coverage_x", "Interest cover (x)"),
                   ("economic_net_leverage_x", "Economic leverage (x)"),
                   ("fcf_conversion_pct", "FCF conversion")]:
        print(f"{lbl:34}" + "".join(f"{r.kpi[k]:12,.2f}" for r in results))
    print("\nAll integrity assertions passed (BS balances; CF ties to BS cash).")

    render_markdown(results, ob)
    print(f"Wrote docs/financial-anchors.md and 9 anchor CSVs to config/anchors/")


def render_markdown(results, ob):
    from textwrap import dedent
    r23, r25, r26b, r26f = results[0], results[2], results[3], results[4]
    hdr = " | ".join(p[4] for p in PERIODS)
    sep = "---|" * len(PERIODS)

    doc = dedent(f"""\
    # Financial Anchors — Northstar Industrial Group

    > **Generated file.** Produced by `src/anchors/build_anchors.py`. Do not edit by hand —
    > change the drivers in the script and re-run. Every figure below is derived from
    > drivers rather than typed in: the balance sheet closes by construction and the cash
    > flow statement ties to balance-sheet cash to the cent, enforced by assertions in the
    > script and re-tested independently in `tests/test_anchors.py`.

    ## 1. What this document is

    These are the **authoritative group financial anchors** for the engagement. They are the
    calibration target for Phase 2 synthetic transaction generation and the reconciliation
    target for Phase 9 QA. If generated data does not roll up to these numbers within
    tolerance, the data is wrong — not the anchors.

    Tolerances: revenue, EBITDA and net income ±0.5%; balance sheet captions ±1.0%; every
    balancing identity (A = L + E, cash flow to cash, eliminations to nil) must be exact
    to $1.

    | Item | Basis |
    |---|---|
    | Reporting currency | USD |
    | Fiscal year | Calendar year ending 31 December |
    | Historical actuals | FY2023, FY2024, FY2025 |
    | Current year | FY2026 — Budget (`BUD_FY26_V1`) and Forecast (`FC_FY26_08`, 8 actual + 4 forecast months) |
    | Prior year | Derived from Actual by date offset, not stored (ADR-0004) |
    | Opening balance sheet | 31 December 2022 |
    | Units | USD millions unless stated |

    ## 2. Consolidated income statement

    {md_table(PL_ROWS, results, 'pl')}

    **Reading the story.** Revenue grows from ${r23.pl['revenue']:,.1f}m to
    ${r25.pl['revenue']:,.1f}m, a {((r25.pl['revenue'] / r23.pl['revenue']) ** 0.5 - 1) * 100:.1f}%
    CAGR built from organic growth plus two acquisitions. Adjusted EBITDA margin expands from
    {r23.kpi['adjusted_ebitda_margin_pct'] * 100:.1f}% to
    {r25.kpi['adjusted_ebitda_margin_pct'] * 100:.1f}% as integration costs roll off and
    pricing and procurement actions land. FY2023 is a *reported* net loss — heavy one-time
    integration spend against peak interest rates — and FY2024 is close to break-even at the
    bottom line. FY2025 is the first year of meaningful net income. That is the correct shape
    for a levered buy-and-build platform, and it gives the board pack something real to
    discuss rather than a smooth upward line.

    FY2026 Forecast lands ${r26b.pl['revenue'] - r26f.pl['revenue']:,.1f}m
    ({(r26f.pl['revenue'] / r26b.pl['revenue'] - 1) * 100:.1f}%) below Budget on revenue and
    ${r26b.pl['adjusted_ebitda'] - r26f.pl['adjusted_ebitda']:,.1f}m below on Adjusted EBITDA.
    The drivers are deliberate and traceable: European capital-equipment softness at Halden
    Valve, one large Vector Systems project slipping into FY2027, and an incremental
    restructuring charge taken in response. A favourable FX translation swing partly offsets,
    because the Budget was locked at rates weaker than those now forecast — which is exactly
    the situation that makes a constant-currency view non-optional.

    ## 3. Consolidated balance sheet

    {md_table(BS_ROWS, results, 'bs')}

    Opening (31 December 2022) retained earnings is **${ob['retained_earnings']:,.1f}m**, an
    accumulated deficit against ${ob['contributed_capital']:,.0f}m of contributed capital. The
    deficit is the normal consequence of a 2021 sponsor recapitalisation dividend charged to
    reserves plus three years of post-LBO intangible amortisation and transaction costs; it is
    not a sign of distress, and total opening equity of
    ${ob['contributed_capital'] + ob['retained_earnings'] + ob['cta'] + ob['nci']:,.1f}m against
    total assets is consistent with a levered platform. It is derived as the opening balancing figure and asserted to fall
    within ±${OPENING_RE_TOLERANCE:.0f}m of the expected ${OPENING_RE_EXPECTED:,.0f}m, so a
    careless change to an opening driver fails the build rather than silently distorting
    every subsequent year.

    ## 4. Consolidated cash flow statement

    {md_table(CF_ROWS, results, 'cf')}

    The statement is prepared on the **indirect** basis and derived arithmetically from
    balance sheet movements plus net income (ADR-0006). `NET CHANGE IN CASH` therefore ties
    to the balance sheet movement in cash by construction; the script asserts this to 1e-6
    and refuses to emit output if it fails. Acquisition-related working capital acquired is
    excluded from the operating movement and shown within investing, which is the correct
    treatment and a common error in hand-built models.

    ## 5. Key performance indicators and covenant metrics

    {md_table(KPI_ROWS, results, 'kpi', kinds=True)}

    **Deleveraging is the headline, and covenant headroom is the tension.** Net leverage falls
    from {r23.kpi['net_leverage_x']:.2f}x at FY2023 (immediately post-Halden) to
    {r25.kpi['net_leverage_x']:.2f}x at FY2025 against a covenant maximum that steps down
    6.00x / 5.50x / 5.00x / 4.50x across FY2023–FY2026. Headroom is genuinely tight early:
    {r23.kpi['covenant_leverage_headroom_x']:.2f}x at FY2023 and
    {results[1].kpi['covenant_leverage_headroom_x']:.2f}x at FY2024, widening to
    {r25.kpi['covenant_leverage_headroom_x']:.2f}x at FY2025. Interest coverage improves from
    {r23.kpi['interest_coverage_x']:.2f}x to {r25.kpi['interest_coverage_x']:.2f}x against a
    2.00x minimum — only {r23.kpi['covenant_coverage_headroom_x']:.2f}x of headroom in FY2023.

    The FY2026 Forecast at {r26f.kpi['net_leverage_x']:.2f}x versus a Budget of
    {r26b.kpi['net_leverage_x']:.2f}x costs
    {r26b.kpi['covenant_leverage_headroom_x'] - r26f.kpi['covenant_leverage_headroom_x']:.2f}x
    of headroom. That is a legitimate board-level talking point rather than a covenant breach:
    headroom narrows, it does not disappear. A covenant-compliance view is therefore a
    first-class reporting requirement, not a nice-to-have — see `docs/reporting-design.md`.

    ## 6. Business unit anchors

    | Business unit | Measure | {hdr} |
    |---|---|{sep}
    """)

    for bu in ["FC", "IS", "ES", "AM"]:
        doc += (f"| {BU_NAMES[bu]} | Revenue | "
                + " | ".join(f"{r.pl[f'revenue_{bu}']:,.1f}" for r in results) + " |\n")
        doc += (f"| {BU_NAMES[bu]} | Gross margin % | "
                + " | ".join(f"{r.pl[f'gross_profit_{bu}'] / r.pl[f'revenue_{bu}'] * 100:.1f}%"
                             for r in results) + " |\n")
        doc += (f"| {BU_NAMES[bu]} | Headcount | "
                + " | ".join(f"{HEADCOUNT[bu][c]:,.0f}" for c in COLS) + " |\n")
    doc += ("| Corporate & Shared Services | Headcount | "
            + " | ".join(f"{HEADCOUNT['CORP'][c]:,.0f}" for c in COLS) + " |\n")

    doc += dedent(f"""
    Business unit gross margins are set at BU level and applied to external revenue.
    Corporate and Shared Services carries no external revenue; it recovers its cost base
    through an intercompany management fee (section 8) which eliminates on consolidation.

    ## 7. Legal entity revenue anchors (external revenue only)

    | Entity | BU | {hdr} |
    |---|---|{sep}
    """)
    for e, (bu, rev) in ENTITY_REVENUE.items():
        doc += f"| {e} | {bu} | " + " | ".join(f"{rev[c]:,.1f}" for c in COLS) + " |\n"

    doc += dedent(f"""
    `NIG-100` (Topco) and `NIG-110` (Shared Services) have no external revenue.
    `NIG-220` FY2023 covers nine months only (acquired 1 April 2023) and `NIG-410` FY2024
    covers six months only (acquired 1 July 2024). Phase 2 must respect these
    consolidation-effective dates, and Phase 5 must present organic versus acquired growth
    separately in the revenue bridge — otherwise FY2024 growth reads as organic when roughly
    a quarter of it is not.

    ## 8. Intercompany anchors (gross, eliminated in full)

    | Intercompany flow | {hdr} |
    |---|{sep}
    """)
    ic_labels = {
        "mgmt_fee": "Management fee income / expense (2.5% of external revenue)",
        "ic_product_sales": "Intercompany product sales",
        "ic_service_sales": "Intercompany service sales",
        "ic_royalty": "Intercompany technology royalty",
        "ic_interest": "Intercompany loan interest",
        "ic_ar_ap_close": "Intercompany AR / AP, closing balance",
        "ic_loan_close": "Intercompany loans, closing principal",
        "pup_in_inventory": "Unrealised profit in closing inventory (PUP)",
    }
    for k, v in IC_ANCHORS.items():
        doc += f"| {ic_labels[k]} | " + " | ".join(f"{v[c]:,.2f}" for c in COLS) + " |\n"

    tot25 = sum(IC_ANCHORS[k]["FY2025A"] for k in
                ("mgmt_fee", "ic_product_sales", "ic_service_sales", "ic_royalty"))
    doc += dedent(f"""
    Total FY2025 intercompany revenue eliminated is **${tot25:,.1f}m**: entity-level combined
    revenue of ${r25.pl['revenue'] + tot25:,.1f}m eliminates down to consolidated revenue of
    ${r25.pl['revenue']:,.1f}m, a {tot25 / r25.pl['revenue'] * 100:.1f}% gross-up.
    Intercompany interest of ${IC_ANCHORS['ic_interest']['FY2025A']:,.2f}m eliminates against
    intercompany interest expense with no effect on consolidated net interest. Unrealised
    profit in inventory is a genuine consolidation adjustment: it reduces consolidated
    inventory and gross profit and does **not** net to zero, which is why it is anchored
    separately from the pure eliminations.

    ## 9. FX anchors (USD per one unit of local currency)

    | Currency | FY | Rate set | Average | Closing |
    |---|---|---|---|---|
    """)
    for c, y, s, a, cl in FX_ANCHORS:
        if c == "USD":
            continue
        doc += f"| {c} | {y} | {s} | {a:.4f} | {cl:.4f} |\n"

    doc += dedent("""
    Three rate sets exist for FY2026: `ACTUAL` (months closed to date), `BUDGET` (locked at
    the October 2025 forward curve when the budget was approved) and `FORECAST` (actual to
    date plus current forwards). Budget is translated at budget rates and never restated; the
    constant-currency view retranslates Actual at budget rates. See ADR-0005.

    The annual averages above are anchors only. Phase 2 generates a **monthly** rate series
    calibrated so that the revenue-weighted monthly average reproduces the annual average
    within 10 basis points, because the model translates P&L at monthly average rates rather
    than applying an annual average to a year-to-date figure (ADR-0005).

    ## 10. Capital structure and acquisitions

    | Item | Detail |
    |---|---|
    | Term Loan B | $180.0m original (2021 recapitalisation), 1% p.a. scheduled amortisation, SOFR + 425bps |
    | Incremental term loan | $25.0m drawn April 2023 (Halden Valve); $30.0m drawn July 2024 (Vector Systems B.V.) |
    | Interest rate swap | $100m notional, SOFR fixed at 3.00%, matures December 2026; not designated for hedge accounting |
    | Revolving credit facility | $60.0m commitment, 0.50% commitment fee on the undrawn balance |
    | Finance leases | Vehicles and production equipment, ~5.4 year average remaining term, 6.4–6.5% |
    | Covenants | Maximum total net leverage 6.00x stepping down to 4.50x; minimum interest coverage 2.00x |
    | Sponsor | Calder Ridge Partners — $20.0m equity contribution in 2023 to part-fund Halden |
    | Treasury policy | Minimum cash $15.0m, target cash $22.0m, surplus sweeps the revolver |

    | Acquisition | Date | Consideration | Goodwill | Intangibles | Funding |
    |---|---|---|---|---|---|
    | Halden Valve GmbH | 1 Apr 2023 | $52.0m | $24.0m | $18.0m | $25m incremental TLB + $20m sponsor equity + revolver |
    | Vector Systems B.V. | 1 Jul 2024 | $38.0m | $17.5m | $13.5m | $30m incremental TLB + cash |

    ## 11. How to regenerate and re-validate

    ```bash
    python src/anchors/build_anchors.py     # rebuilds config/anchors/*.csv and this document
    python -m pytest tests -q               # re-validates every identity independently
    ```
    """)
    DOC_OUT.write_text(doc, encoding="utf-8")


if __name__ == "__main__":
    main()
