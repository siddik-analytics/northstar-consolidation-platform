"""
Planning and subledger datasets: budget, forecast versions, headcount, capital projects
and fixed assets, instrument-level debt, and customer/product revenue detail.

These are *source and reference* datasets, not consolidated output.  Each is built so a
later phase can reconcile it to the general ledger: revenue detail to GL revenue accounts,
capex to fixed assets to depreciation, debt to interest and to the balance sheet, headcount
to the statistical accounts.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from .common import (REFERENCE, allocate_exact, build_periods, load_anchor,
                     load_credit_agreement, plan_periods, rng, stable_id, write_csv)
from .mapping import SourceMap
from .masters import ACCOUNT_DEPTS, DEFAULT_DEPT, build_cost_centres, build_employees
from .series import SeriesBuilder

ASSET_CLASSES = {
    "150200": ("BUILDING", "Buildings and improvements", 30),
    "150300": ("PLANT", "Machinery and equipment", 10),
    "150400": ("VEHICLE", "Vehicles", 6),
    "150500": ("IT", "Computer hardware and software", 4),
    "150600": ("LEASEHOLD", "Leasehold improvements", 8),
    "150800": ("FINANCE_LEASE", "Finance lease right-of-use assets", 6),
}


# --------------------------------------------------------------------------- plan
def build_plan(sb: SeriesBuilder) -> list[dict]:
    """
    FY2026 budget and three forecast versions at the approved planning grain.

    The forecast's actual months are the Actual scenario itself, so `CTL-SCN-02` holds by
    construction.  The two superseded forecasts were issued before the European softness
    and the Vector slippage were recognised, so they sit between budget and outturn -- which
    is what makes forecast accuracy measurable rather than asserted.
    """
    actual = {(em.entity, em.period_key): em for em in sb.build_actuals()}
    periods = plan_periods(2026)
    rows: list[dict] = []
    cc_lookup = {}
    for cc in build_cost_centres():
        cc_lookup.setdefault(cc["entity_code"], {})[cc["department_code"]] = cc["cost_center_code"]

    def cost_centre(entity: str, account: str) -> str:
        d = cc_lookup.get(entity, {})
        for dep in ACCOUNT_DEPTS.get(account, []):
            if dep in d:
                return d[dep]
        return d.get(DEFAULT_DEPT, next(iter(d.values())) if d else "0-950")

    sm = SourceMap()

    def expected(entity: str, account: str) -> str:
        return sm.expected_group(sb.ent[entity].erp, account)

    series_by_col = {}
    for col in ("FY2026B", "FY2026F"):
        out = {}
        for code, e in sorted(sb.ent.items()):
            if not sb.lb.live(code, col):
                continue
            pl = sb._pl_local_monthly(code, col, periods)
            ic_pl, _ = sb.ic_monthly(col, periods)
            for i, p in enumerate(periods):
                for a, v in ic_pl.get((code, p.period_key), {}).items():
                    pl.setdefault(a, np.zeros(len(periods)))[i] += v
            out[code] = pl
        series_by_col[col] = out

    versions = [
        ("BUD", "BUD_FY26_V1", "FY2026B", 0, None),
        ("FC", "FC_FY26_02", "FY2026F", 1, 0.995),
        ("FC", "FC_FY26_05", "FY2026F", 4, 0.985),
        ("FC", "FC_FY26_08", "FY2026F", 8, None),
    ]
    for scenario, version, col, actual_months, blend in versions:
        base = series_by_col["FY2026F" if scenario == "FC" else "FY2026B"]
        budget = series_by_col["FY2026B"]
        for code, pl in base.items():
            for a, arr in pl.items():
                for i, p in enumerate(periods):
                    if scenario == "FC" and i < actual_months:
                        em = actual.get((code, p.period_key))
                        amt = em.pl.get(a, 0.0) if em else 0.0
                    elif blend is not None:
                        b = budget.get(code, {}).get(a)
                        amt = (b[i] * blend) if b is not None else float(arr[i])
                    else:
                        amt = float(arr[i])
                    if abs(amt) < 0.005:
                        continue
                    rows.append(dict(
                        scenario_code=scenario, version_code=version, entity_code=code,
                        period_key=p.period_key, group_account=a,
                        expected_group_account=expected(code, a),
                        cost_center_code=cost_centre(code, a),
                        currency_code=sb.ent[code].currency,
                        amount_local=round(amt, 2),
                        is_actual_month="TRUE" if (scenario == "FC" and i < actual_months)
                        else "FALSE"))
    return rows


# --------------------------------------------------------------------------- headcount
def build_headcount(sb: SeriesBuilder, employees: list[dict]) -> list[dict]:
    """Monthly workforce movement derived from the employee master's own dates."""
    rows = []
    periods = build_periods((2023, 1), (2026, 8))
    by_group: dict[tuple, list[dict]] = {}
    for e in employees:
        by_group.setdefault((e["entity_code"], e["cost_center_code"],
                             e["job_family_code"]), []).append(e)
    for (entity, cc, jf), emps in sorted(by_group.items()):
        hires = [(date.fromisoformat(e["hire_date"]),
                  date.fromisoformat(e["termination_date"]) if e["termination_date"] else None,
                  float(e["fte"]), float(e["annual_base_salary_local"])) for e in emps]
        for p in periods:
            if sb.ent[entity].effective_from > p.end:
                continue
            active = [(h, t, f, s) for h, t, f, s in hires
                      if h <= p.end and (t is None or t > p.end)]
            opening = [(h, t, f, s) for h, t, f, s in hires
                       if h < p.start and (t is None or t >= p.start)]
            joined = [x for x in hires if p.start <= x[0] <= p.end]
            left = [x for x in hires if x[1] and p.start <= x[1] <= p.end]
            if not active and not joined and not left:
                continue
            rows.append(dict(
                entity_code=entity, cost_center_code=cc, job_family_code=jf,
                period_key=p.period_key,
                fte_opening=round(sum(f for _, _, f, _ in opening), 2),
                hires=len(joined), leavers=len(left),
                fte_closing=round(sum(f for _, _, f, _ in active), 2),
                fte_average=round((sum(f for _, _, f, _ in opening)
                                   + sum(f for _, _, f, _ in active)) / 2, 2),
                headcount_closing=len(active),
                annual_base_salary_local=round(sum(s * f for _, _, f, s in active), 2),
                currency_code=sb.ent[entity].currency))
    return rows


# --------------------------------------------------------------------------- capex
def build_capex(sb: SeriesBuilder) -> tuple[list[dict], list[dict]]:
    """Capital projects and the fixed asset register they create."""
    rows_proj, rows_asset = [], []
    actual = sb.build_actuals()
    by_ent: dict[str, list] = {}
    for em in actual:
        by_ent.setdefault(em.entity, []).append(em)
    for entity, months in sorted(by_ent.items()):
        e = sb.ent[entity]
        g = rng("capex", entity)
        prev = None
        for em in sorted(months, key=lambda m: m.period_key):
            additions = {a: em.bs_close.get(a, 0.0) - (prev.bs_close.get(a, 0.0)
                                                       if prev else em.bs_open.get(a, 0.0))
                         for a in ASSET_CLASSES}
            prev = em
            p_year, p_month = divmod(em.period_key, 100)
            for acct, amt in additions.items():
                if amt <= 1000:
                    continue
                cls, name, life = ASSET_CLASSES[acct]
                n = int(np.clip(amt / 250_000, 1, 12))
                for i, part in enumerate(allocate_exact(amt, g.lognormal(0, 0.6, n), 2)):
                    if part < 500:
                        continue
                    pid = f"CP-{entity[-3:]}-{em.period_key}-{i + 1:02d}"
                    in_service = date(p_year, p_month, min(28, 10 + i))
                    rows_proj.append(dict(
                        project_id=pid, entity_code=entity, project_name=f"{name} programme",
                        asset_class=cls, bu_code=e.bu, period_key=em.period_key,
                        approved_amount_local=round(part * float(g.uniform(1.0, 1.18)), 2),
                        spend_local=round(part, 2), currency_code=e.currency,
                        status="COMPLETE" if g.random() < 0.85 else "IN_PROGRESS"))
                    rows_asset.append(dict(
                        asset_id=f"FA-{stable_id(entity, em.period_key, acct, i, width=10)}",
                        entity_code=entity, project_id=pid, asset_class=cls,
                        asset_description=f"{name} - {pid}", group_account=acct,
                        cost_centre_code="", acquisition_date=in_service.isoformat(),
                        in_service_date=in_service.isoformat(),
                        useful_life_years=life,
                        depreciation_method="STRAIGHT_LINE",
                        cost_local=round(part, 2), residual_value_local=0.0,
                        currency_code=e.currency, status="ACTIVE"))
    return rows_proj, rows_asset


# --------------------------------------------------------------------------- debt
def build_debt(sb: SeriesBuilder) -> list[dict]:
    """Instrument-level debt: external facilities at Topco, leases at the lessee."""
    ca = load_credit_agreement()
    pl = load_anchor("income_statement")
    bs = load_anchor("balance_sheet")
    rows = []
    periods = build_periods((2023, 1), (2026, 8))
    actual = sb.build_actuals()
    fl_by_ent: dict[tuple[str, int], float] = {}
    for em in actual:
        fl = -(em.bs_close.get("220300", 0.0) + em.bs_close.get("230300", 0.0))
        fl_by_ent[(em.entity, em.period_key)] = fl

    OPENING_2022 = {"tlb_gross": 178.2, "rcf": 8.0, "dff": 4.6}

    def col_of(pk: int) -> str:
        y = pk // 100
        return "FY2026F" if y == 2026 else f"FY{y}A"

    def year_end(cap: str, year: int) -> float:
        if year <= 2022:
            return OPENING_2022[cap]
        return bs[cap]["FY2026F" if year >= 2026 else f"FY{year}A"]

    def interp(cap: str, pk: int) -> float:
        """Straight-line within the year between anchored year-end balances."""
        y, m = divmod(pk, 100)
        start, cur = year_end(cap, y - 1), year_end(cap, y)
        return start + (cur - start) * m / 12.0

    swap_end = date(2026, 12, 31)
    for p in periods:
        pk, col = p.period_key, col_of(p.period_key)
        months = 12.0
        for iid, name, cap, acct, rate_key, kind in [
            ("TLB-2021", "Term Loan B (2021)", "tlb_gross", "230100", "interest_tlb", "TERM_LOAN"),
            ("RCF-2021", "Revolving Credit Facility", "rcf", "220200", "interest_rcf", "RCF"),
        ]:
            bal = interp(cap, pk)
            prev = interp(cap, pk - 1 if pk % 100 > 1 else (pk // 100 - 1) * 100 + 12)
            interest = pl[rate_key][col] / months
            rows.append(dict(
                instrument_id=iid, instrument_name=name, borrower_entity="NIG-100",
                instrument_type=kind, group_account=acct, currency_code="USD",
                period_key=pk,
                opening_principal=round(prev * 1e6, 2), drawings=round(max(bal - prev, 0) * 1e6, 2),
                repayments=round(max(prev - bal, 0) * 1e6, 2),
                closing_principal=round(bal * 1e6, 2),
                interest_rate_basis="SOFR + 425bps" if kind == "TERM_LOAN" else "SOFR + 450bps",
                rate_type="FLOATING", is_hedged="TRUE" if kind == "TERM_LOAN" else "FALSE",
                hedge_notional_usd=100e6 if kind == "TERM_LOAN" else 0.0,
                hedge_maturity=swap_end.isoformat() if kind == "TERM_LOAN" else "",
                maturity_date=ca["CA-004"]["value"] if kind == "TERM_LOAN" else "2027-06-15",
                interest_expense_local=round(interest * 1e6, 2),
                commitment_fee_local=round(pl["commitment_fee"][col] / months * 1e6, 2)
                if kind == "RCF" else 0.0,
                unamortised_fees=round(interp("dff", pk) * 1e6, 2) if kind == "TERM_LOAN" else 0.0,
                undrawn_commitment=round((60.0 - bal) * 1e6, 2) if kind == "RCF" else 0.0,
                counts_toward_covenant_debt="TRUE",
                covenant_reference="CA-015" if kind == "TERM_LOAN" else "CA-016"))
        for code, e in sorted(sb.ent.items()):
            fl = fl_by_ent.get((code, pk))
            if not fl or fl <= 0:
                continue
            prev_pk = pk - 1 if pk % 100 > 1 else (pk // 100 - 1) * 100 + 12
            prev = fl_by_ent.get((code, prev_pk), fl)
            rows.append(dict(
                instrument_id=f"FL-{code[-3:]}", instrument_name=f"Finance leases - {e.short_name}",
                borrower_entity=code, instrument_type="FINANCE_LEASE",
                group_account="230300", currency_code=e.currency, period_key=pk,
                opening_principal=round(prev, 2), drawings=round(max(fl - prev, 0), 2),
                repayments=round(max(prev - fl, 0), 2), closing_principal=round(fl, 2),
                interest_rate_basis="6.4% fixed", rate_type="FIXED", is_hedged="FALSE",
                hedge_notional_usd=0.0, hedge_maturity="", maturity_date="2030-12-31",
                interest_expense_local=round(fl * 0.064 / 12, 2), commitment_fee_local=0.0,
                unamortised_fees=0.0, undrawn_commitment=0.0,
                counts_toward_covenant_debt="TRUE", covenant_reference="CA-017"))
    return rows


# --------------------------------------------------------------------------- revenue detail
def build_revenue_detail(sb: SeriesBuilder, customers: list[dict],
                         products: list[dict]) -> list[dict]:
    """
    Customer x product revenue that reconciles to the GL revenue accounts (ADR-0008).

    Split exactly, so the detail fact sums back to the ledger's external revenue for every
    entity and period -- the reconciliation `CTL-REC-02` will test.
    """
    cust_by_entity: dict[str, list[dict]] = {}
    for c in customers:
        cust_by_entity.setdefault(c["billing_entity"], []).append(c)
    prod_by_bu: dict[str, list[dict]] = {}
    for p in products:
        prod_by_bu.setdefault(p["bu_code"], []).append(p)

    rows = []
    for em in sb.build_actuals():
        e = sb.ent[em.entity]
        ext = {a: -v for a, v in em.pl.items()
               if a.startswith("4") and not a.startswith("44") and not a.startswith("49")}
        if not ext:
            continue
        cust = cust_by_entity.get(em.entity, [])
        prods = prod_by_bu.get(e.bu, [])
        if not cust or not prods:
            continue
        g = rng("revdetail", em.entity, em.period_key)
        for acct, total in ext.items():
            n = int(np.clip(len(cust) * 0.45, 8, 90))
            ci = g.choice(len(cust), size=n, replace=False)
            pi = g.integers(0, len(prods), size=n)
            w = g.lognormal(0, 0.9, n)
            amounts = allocate_exact(total, w, 2)
            for k in range(n):
                if abs(amounts[k]) < 0.01:
                    continue
                pr = prods[int(pi[k])]
                margin = float(pr["standard_margin_pct"])
                rows.append(dict(
                    entity_code=em.entity, period_key=em.period_key,
                    customer_code=cust[int(ci[k])]["customer_code"],
                    product_code=pr["product_code"], group_account=acct,
                    currency_code=e.currency, revenue_local=round(float(amounts[k]), 2),
                    cost_of_sales_local=round(float(amounts[k]) * (1 - margin), 2),
                    quantity=int(max(1, abs(amounts[k]) // 2500)),
                    order_count=int(max(1, g.integers(1, 5))),
                    is_intercompany="FALSE"))
    return rows
