"""
Journal generation: turns each entity-period ledger position into balanced journal entries.

Every posting has an economic origin.  Revenue arrives as invoices against receivables,
labour accrues to a payroll liability and is later paid, purchases build payables that are
later settled, depreciation charges against accumulated depreciation.  Cash is never
targeted -- it is whatever the balanced entries leave behind, which is what makes the
trial balance close by construction rather than by a plug.

The generator works in three stages per entity-period:

  1. P&L-driven events, each with its natural balance sheet counterpart.
  2. Non-cash pairings: contract-asset billing, inventory purchases, capital additions.
  3. Settlements: whatever movement each balance sheet account still needs to reach its
     target is posted against cash -- these are the receipts and payments.

Stage 3 is what guarantees the closing balances, and because every entry is balanced the
period's lines always sum to zero.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from .common import PERIOD_BY_KEY, Period, rng, stable_id
from .masters import ACCOUNT_DEPTS, DEFAULT_DEPT, DEPT_FUNCTION

# group account -> the balance sheet account its P&L posting settles against
COUNTERPART = {
    "410100": "120100", "410200": "120100", "415100": "120100", "425200": "120100",
    "420100": "120100", "420200": "120100", "430100": "120100", "435100": "120100",
    "420300": "121100", "425100": "121100",
    "440100": "120100", "440200": "120100",
    "490100": "120500", "490200": "120500", "490300": "120500", "490400": "120500",
    "510100": "130100", "510200": "130300", "510300": "210100",
    "515100": "215100", "515200": "215100", "515300": "215100", "520100": "215100",
    "520200": "210100", "520300": "210100", "520400": "210100",
    "525100": "210100", "525200": "210100",
    "530100": "130100", "530200": "215400", "535100": "211100",
    "590100": "210500", "590200": "210500",
    "610100": "215100", "610200": "215100", "610300": "215100", "610600": "215100",
    "610700": "215100", "610800": "215100",
    "610400": "215200", "610500": "315100", "640400": "120200",
    "680100": "215500", "680200": "215500",
    "695100": "210500", "695200": "210500", "695300": "210500",
    "710100": "155100", "720200": "166100",
    "730100": "216100", "730200": "216100", "730300": "216100", "730500": "216100",
    "730600": "216100", "730400": "230200", "735100": "110100",
    "795100": "120500", "795200": "210500",
    "810100": "218100", "810200": "218100", "810300": "218100", "830100": "218100",
}
DEFAULT_COUNTERPART = "210100"

# Settlement accounts that are cleared against cash in stage 3, with how many separate
# transactions each generates (scaled by entity size).
SETTLEMENT_TX = {
    "120100": ("CASH_RECEIPT", "Customer receipt", 0.54),
    "210100": ("SUPPLIER_PAYMENT", "Supplier payment", 0.60),
    "210200": ("GRNI_CLEAR", "Goods received cleared", 0.03),
    "215100": ("PAYROLL_PAYMENT", "Payroll disbursement", 0.02),
    "215200": ("BONUS_PAYMENT", "Incentive payment", 0.004),
    "215300": ("ACCRUAL_SETTLE", "Professional fee settlement", 0.004),
    "215400": ("WARRANTY_SETTLE", "Warranty claim settled", 0.004),
    "215500": ("RESTRUCT_SETTLE", "Restructuring payment", 0.004),
    "215600": ("ACCRUAL_SETTLE", "Accrual settled", 0.006),
    "216100": ("INTEREST_PAYMENT", "Interest paid", 0.002),
    "218100": ("TAX_PAYMENT", "Income tax paid", 0.002),
    "219100": ("TAX_PAYMENT", "Indirect tax paid", 0.003),
    "120500": ("IC_RECEIPT", "Intercompany receipt", 0.012),
    "210500": ("IC_PAYMENT", "Intercompany settlement", 0.012),
    "120200": ("PROVISION_MOVE", "Bad debt provision movement", 0.001),
    "130400": ("PROVISION_MOVE", "Inventory provision movement", 0.001),
    "140100": ("PREPAYMENT", "Prepayment made", 0.006),
    "180100": ("OTHER_ASSET", "Other asset movement", 0.001),
    "245100": ("OTHER_LIAB", "Other long-term liability movement", 0.001),
    "211100": ("CUSTOMER_ADVANCE", "Customer advance", 0.008),
    "220300": ("LEASE_PAYMENT", "Finance lease principal", 0.002),
    "230300": ("LEASE_PAYMENT", "Finance lease principal", 0.002),
    "175100": ("IC_LOAN", "Intercompany loan movement", 0.001),
    "235100": ("IC_LOAN", "Intercompany loan movement", 0.001),
    "225100": ("IC_LOAN", "Intercompany loan movement", 0.001),
    "230100": ("DEBT_MOVEMENT", "Term loan movement", 0.001),
    "220200": ("DEBT_MOVEMENT", "Revolving facility movement", 0.002),
    "230200": ("FINANCING_FEE", "Deferred financing cost", 0.001),
    "178100": ("INVESTMENT", "Investment in subsidiary", 0.001),
    "310100": ("EQUITY", "Share capital movement", 0.001),
    "310200": ("EQUITY", "Capital contribution", 0.001),
    "315100": ("EQUITY", "Share-based compensation reserve", 0.001),
    "320300": ("DIVIDEND", "Distribution paid", 0.001),
    "155100": ("ASSET_DISPOSAL", "Asset disposal", 0.001),
    "166100": ("ASSET_DISPOSAL", "Intangible disposal", 0.001),
    "158100": ("LEASE_REMEASURE", "Operating lease remeasurement", 0.001),
    "220400": ("LEASE_REMEASURE", "Operating lease remeasurement", 0.001),
    "230400": ("LEASE_REMEASURE", "Operating lease remeasurement", 0.001),
    "121100": ("CONTRACT_BILLING", "Contract asset billed", 0.02),
}
PPE_ACCOUNTS = ["150200", "150300", "150400", "150500", "150600", "150800"]
INVENTORY_ACCOUNTS = ["130100", "130200", "130300"]

DOC_TYPE = {
    "SALES_INVOICE": "SI", "CREDIT_NOTE": "CN", "PURCHASE_INVOICE": "PI",
    "PAYROLL_ACCRUAL": "PY", "DEPRECIATION": "DP", "ACCRUAL": "AC",
    "CASH_RECEIPT": "CR", "SUPPLIER_PAYMENT": "PM", "PAYROLL_PAYMENT": "PM",
    "IC_INVOICE": "IC", "IC_RECEIPT": "CR", "IC_PAYMENT": "PM", "CAPEX": "FA",
    "INVENTORY_PURCHASE": "PI", "YEAR_END_CLOSE": "CL",
}


class JournalGenerator:
    def __init__(self, series_builder, source_map, cost_centres):
        self.sb = series_builder
        self.sm = source_map
        self.ent = series_builder.ent
        self.cc_by_entity: dict[str, dict[str, list[dict]]] = {}
        for cc in cost_centres:
            self.cc_by_entity.setdefault(cc["entity_code"], {}).setdefault(
                cc["department_code"], []).append(cc)

    # ------------------------------------------------------------------ helpers
    def _cost_centre(self, entity: str, account: str) -> tuple[str, str, str]:
        depts = self.cc_by_entity.get(entity, {})
        for d in ACCOUNT_DEPTS.get(account, []):
            if d in depts:
                cc = depts[d][0]
                return cc["cost_center_code"], d, DEPT_FUNCTION[d]
        if DEFAULT_DEPT in depts:
            cc = depts[DEFAULT_DEPT][0]
            return cc["cost_center_code"], DEFAULT_DEPT, DEPT_FUNCTION[DEFAULT_DEPT]
        any_d = next(iter(depts)) if depts else None
        if any_d:
            return depts[any_d][0]["cost_center_code"], any_d, DEFAULT_DEPT
        return "0-950", DEFAULT_DEPT, "SGA"

    @staticmethod
    def _split(g: np.random.Generator, total: float, n: int) -> np.ndarray:
        """Split a total into n lognormally-sized pieces that sum back exactly."""
        if n <= 1 or total == 0:
            return np.array([total], dtype=float) if total else np.zeros(1)
        w = g.lognormal(mean=0.0, sigma=0.75, size=n)
        parts = np.round(total * w / w.sum(), 2)
        parts[-1] = round(total - parts[:-1].sum(), 2)
        return parts

    def _dates(self, g: np.random.Generator, p: Period, n: int,
               weekday_bias: bool = True) -> np.ndarray:
        days = g.integers(1, p.days + 1, size=n)
        if weekday_bias:
            # push weekend postings onto the following Monday, as a real ledger does
            for i in range(n):
                d = p.start + timedelta(days=int(days[i]) - 1)
                if d.weekday() >= 5:
                    days[i] = min(int(days[i]) + (7 - d.weekday()), p.days)
        return days

    # ------------------------------------------------------------------ main
    def generate(self, em, ic_pairs: dict) -> list[tuple]:
        e = self.ent[em.entity]
        p = PERIOD_BY_KEY[em.period_key]
        g = rng("journal", em.entity, em.period_key)
        lines: list[tuple] = []
        seq = [0]
        used: dict[str, float] = {}
        scale = max(sum(abs(v) for a, v in em.pl.items() if a.startswith("4")), 1.0)
        vol = float(np.clip(scale / 6.0e6, 0.25, 6.0))     # transaction volume driver

        def post(journal_type: str, date_day: int, legs: list[tuple[str, float, dict]],
                 desc: str, doc_ref: str, partner: str = "", customer: str = "",
                 product: str = "") -> None:
            """Emit one balanced journal. `legs` are (group_account, signed_amount, attrs)."""
            if all(abs(a) < 0.005 for _, a, _ in legs):
                return
            # Round every leg, then push the residual onto the largest so the entry
            # balances to the cent. Without this a three-leg split leaves a stray cent.
            legs = [(a, round(v, 2), x) for a, v, x in legs]
            residual = round(sum(v for _, v, _ in legs), 2)
            if residual:
                k = max(range(len(legs)), key=lambda i: abs(legs[i][1]))
                legs[k] = (legs[k][0], round(legs[k][1] - residual, 2), legs[k][2])
            seq[0] += 1
            jid = f"{e.erp[:2]}{em.period_key}{em.entity[-3:]}{seq[0]:06d}"
            pdate = p.start + timedelta(days=int(date_day) - 1)
            for ln, (acct, amt, attrs) in enumerate(legs, start=1):
                cc, dept, func = self._cost_centre(em.entity, acct)
                resolved = self.sm.resolve(e.erp, acct)
                if resolved is None:
                    raise KeyError(
                        f"{e.erp} has no source account for group account {acct}. "
                        f"Dropping the leg would silently unbalance journal {jid}; "
                        f"add a mapping or a NOT_AVAILABLE substitution.")
                src, req = resolved
                merged = {**req, **attrs}
                if "dept_function" in req:
                    func = req["dept_function"]
                    for d in ACCOUNT_DEPTS.get(acct, []):
                        if d in self.cc_by_entity.get(em.entity, {}) and DEPT_FUNCTION[d] == func:
                            cc = self.cc_by_entity[em.entity][d][0]["cost_center_code"]
                            dept = d
                            break
                if "cost_center_function" in req:
                    func = req["cost_center_function"]
                lines.append((
                    em.entity, e.erp, e.erp_company_code, em.period_key, jid, ln,
                    pdate.isoformat(), doc_ref, DOC_TYPE.get(journal_type, "JE"),
                    journal_type, desc, src,
                    self.sm.expected_group(e.erp, acct), cc, dept, func, e.currency,
                    round(float(amt), 2), partner, customer, product,
                    ";".join(f"{k}={v}" for k, v in sorted(merged.items())),
                ))
                used[acct] = used.get(acct, 0.0) + float(amt)

        # ---------------- stage 1: P&L-driven events -----------------------
        rev_accounts = {a: v for a, v in em.pl.items()
                        if a.startswith("4") and not a.startswith("44")
                        and not a.startswith("49")}
        n_inv = max(int(118 * vol), 8)
        if rev_accounts:
            accts = list(rev_accounts)
            weights = np.array([abs(rev_accounts[a]) for a in accts])
            counts = np.maximum((weights / weights.sum() * n_inv).astype(int), 1)
            days_all = self._dates(g, p, int(counts.sum()))
            k = 0
            for a, c in zip(accts, counts):
                parts = self._split(g, -rev_accounts[a], int(c))
                cp = COUNTERPART.get(a, "120100")
                for amt in parts:
                    # product_group only resolves Kestrel's product-revenue split; it is
                    # meaningless on a service or project revenue account.
                    attrs = ({"product_group": "EQUIPMENT" if a == "410100" else "COMPONENT"}
                             if a in ("410100", "410200") else {})
                    post("SALES_INVOICE", days_all[k % len(days_all)],
                         [(cp, amt, {}), (a, -amt, attrs)],
                         "Customer invoice", f"INV-{stable_id(em.entity, em.period_key, k, width=7)}",
                         customer=f"C{em.entity[-3:]}{(k % 200) + 1:04d}")
                    k += 1
        for a in ("440100", "440200"):
            if a in em.pl:
                for amt in self._split(g, em.pl[a], max(int(6 * vol), 2)):
                    post("CREDIT_NOTE", int(self._dates(g, p, 1)[0]),
                         [(a, amt, {}), ("120100", -amt, {})], "Credit note",
                         f"CN-{stable_id(em.entity, em.period_key, a, width=6)}")

        IC_PREFIXES = ("49", "59", "695", "795")
        for a, v in sorted(em.pl.items()):
            # Intercompany income and expense are posted by the intercompany block below,
            # which needs the partner on both legs. Posting them here as well would double
            # count every intercompany flow.
            if a.startswith("4") or a.startswith(IC_PREFIXES):
                continue
            cp = COUNTERPART.get(a, DEFAULT_COUNTERPART)
            if a.startswith("5") or a in ("610100", "610200", "610300", "610600"):
                n = max(int(38 * vol), 4)
                jt = "PURCHASE_INVOICE" if cp == "210100" else "PAYROLL_ACCRUAL"
            elif a.startswith("71") or a.startswith("72"):
                n, jt = 1, "DEPRECIATION"
            elif a.startswith("73") or a.startswith("8"):
                n, jt = 1, "ACCRUAL"
            else:
                n, jt = max(int(5 * vol), 2), "PURCHASE_INVOICE"
            attrs = {}
            if a.startswith("73"):
                attrs = {"instrument_type": {"730100": "TERM_LOAN", "730200": "RCF",
                                             "730300": "LEASE", "730400": "TERM_LOAN",
                                             "730500": "RCF"}.get(a, "OTHER")}
            if a in ("710100",):
                attrs = {"asset_class": "PLANT"}
            days = self._dates(g, p, n)
            for i, amt in enumerate(self._split(g, v, n)):
                post(jt, days[i % n], [(a, amt, attrs), (cp, -amt, {})],
                     f"{jt.replace('_', ' ').title()}",
                     f"{DOC_TYPE.get(jt,'JE')}-{stable_id(em.entity, em.period_key, a, i, width=7)}")

        # ---------------- intercompany --------------------------------------
        for leg in ic_pairs.get((em.entity, em.period_key), []):
            acct, cp, amt, partner, kind = leg
            attrs = {"partner_bu": self.ent[partner].bu} if partner in self.ent else {}
            if kind == "INTEREST":
                attrs["instrument_type"] = "AFFILIATE"
            n = max(int(2 * vol), 1)
            days = self._dates(g, p, n)
            for i, part in enumerate(self._split(g, amt, n)):
                post("IC_INVOICE", days[i % n],
                     [(cp, part, attrs), (acct, -part, attrs)],
                     f"Intercompany {kind.lower()} - {partner}",
                     f"ICI-{stable_id(em.entity, partner, em.period_key, i, width=6)}",
                     partner=partner)

        # ---------------- stage 2: non-cash pairings -------------------------
        def movement(acct: str) -> float:
            return em.bs_close.get(acct, 0.0) - em.bs_open.get(acct, 0.0)

        def residual(acct: str) -> float:
            return movement(acct) - used.get(acct, 0.0)

        # inventory replenishment: whatever consumption did not already leave behind
        for acct in INVENTORY_ACCOUNTS:
            r = residual(acct)
            if abs(r) > 0.005:
                n = max(int(12 * vol), 2)
                days = self._dates(g, p, n)
                for i, part in enumerate(self._split(g, r, n)):
                    post("INVENTORY_PURCHASE", days[i % n],
                         [(acct, part, {}), ("210100", -part, {})], "Inventory purchase",
                         f"PI-{stable_id(em.entity, em.period_key, acct, i, width=7)}")
        # capital additions
        for acct in PPE_ACCOUNTS:
            r = residual(acct)
            if abs(r) > 0.005:
                cp = "220300" if acct == "150800" else "210100"
                n = max(int(2 * vol), 1)
                days = self._dates(g, p, n)
                for i, part in enumerate(self._split(g, r, n)):
                    post("CAPEX", days[i % n],
                         [(acct, part, {"asset_class": "PLANT"}), (cp, -part, {})],
                         "Capital expenditure",
                         f"FA-{stable_id(em.entity, em.period_key, acct, i, width=7)}")
        # contract assets billed on to receivables
        r = residual("121100")
        if abs(r) > 0.005:
            n = max(int(8 * vol), 2)
            days = self._dates(g, p, n)
            for i, part in enumerate(self._split(g, r, n)):
                post("CONTRACT_BILLING", days[i % n],
                     [("121100", part, {"accrual_type": "CONTRACT"}), ("120100", -part, {})],
                     "Contract asset billed",
                     f"BL-{stable_id(em.entity, em.period_key, i, width=7)}")
        # operating lease remeasurement is non-cash on both legs
        r_rou = residual("158100")
        if abs(r_rou) > 0.005:
            post("LEASE_REMEASURE", min(28, p.days),
                 [("158100", r_rou, {}), ("220400", -r_rou * 0.22, {}),
                  ("230400", -r_rou * 0.78, {})],
                 "Operating lease remeasurement",
                 f"LR-{stable_id(em.entity, em.period_key, width=6)}")

        # ---------------- stage 3: settlements against cash ------------------
        for acct, (jt, desc, freq) in SETTLEMENT_TX.items():
            if acct in ("158100", "220400", "230400", "121100"):
                continue
            r = residual(acct)
            if abs(r) < 0.005:
                continue
            n = max(int(freq * 900 * vol), 1)
            days = self._dates(g, p, n)
            for i, part in enumerate(self._split(g, r, n)):
                post(jt, days[i % n], [(acct, part, {}), ("110100", -part, {})], desc,
                     f"{DOC_TYPE.get(jt,'JE')}-{stable_id(em.entity, em.period_key, acct, i, width=7)}")
        # anything still outstanding (lease liabilities paired above, rounding) clears to cash
        for acct in sorted(set(em.bs_close) | set(em.bs_open)):
            if acct in ("110100", "320100", "320200"):
                continue
            r = residual(acct)
            if abs(r) >= 0.005:
                post("SETTLEMENT", min(28, p.days),
                     [(acct, r, {}), ("110100", -r, {})], "Period settlement",
                     f"ST-{stable_id(em.entity, em.period_key, acct, width=7)}")
        return lines

    def opening_balance(self, entity: str, period_key: int,
                        balances: dict[str, float]) -> list[tuple]:
        """
        The conversion journal that establishes an entity's opening balance sheet.

        Without it a source extract would only contain movements, and no reader could
        derive a balance.  The entry balances because the opening trial balance does.
        """
        e = self.ent[entity]
        p = PERIOD_BY_KEY[period_key]
        legs = [(a, round(v, 2), {}) for a, v in sorted(balances.items())
                if abs(v) >= 0.005]
        if not legs:
            return []
        # The plug is derived from the ROUNDED legs, so the entry balances to the cent.
        legs.append(("320100" if e.erp != "KESTREL" else "320200",
                     round(-sum(v for _, v, _ in legs), 2), {}))
        out, jid = [], f"{e.erp[:2]}{period_key}{entity[-3:]}000000"
        for ln, (acct, amt, _) in enumerate(legs, start=1):
            resolved = self.sm.resolve(e.erp, acct)
            if resolved is None:
                raise KeyError(f"{e.erp} has no source account for {acct}")
            src, req = resolved
            cc, dept, func = self._cost_centre(entity, acct)
            out.append((entity, e.erp, e.erp_company_code, period_key, jid, ln,
                        p.start.isoformat(), f"OB-{period_key}", "OB", "OPENING_BALANCE",
                        "Opening balance brought forward", src,
                        self.sm.expected_group(e.erp, acct), cc, dept, func,
                        e.currency, round(float(amt), 2), "", "", "", ""))
        return out

    def year_end_close(self, entity: str, period_key: int, ytd_pl: dict[str, float]) -> list[tuple]:
        """Close the year's income statement accounts into retained earnings."""
        e = self.ent[entity]
        p = PERIOD_BY_KEY[period_key]
        target = "320200" if e.erp == "KESTREL" else "320100"
        legs = [(a, round(-v, 2), {}) for a, v in sorted(ytd_pl.items())
                if abs(v) >= 0.005]
        if not legs:
            return []
        legs.append((target, round(-sum(a for _, a, _ in legs), 2), {}))
        out = []
        jid = f"{e.erp[:2]}{period_key}{entity[-3:]}999999"
        for ln, (acct, amt, _) in enumerate(legs, start=1):
            resolved = self.sm.resolve(e.erp, acct)
            if resolved is None:
                raise KeyError(f"{e.erp} has no source account for {acct}")
            src, req = resolved
            cc, dept, func = self._cost_centre(entity, acct)
            out.append((entity, e.erp, e.erp_company_code, period_key, jid, ln,
                        p.end.isoformat(), f"CL-{period_key}", "CL", "YEAR_END_CLOSE",
                        "Year-end close to retained earnings", src,
                        self.sm.expected_group(e.erp, acct), cc, dept, func,
                        e.currency, round(float(amt), 2), "", "", "", ""))
        return out


COLUMNS = ["entity_code", "erp_system", "erp_company_code", "period_key", "journal_id",
           "line_number", "posting_date", "document_reference", "document_type",
           "event_type", "description", "source_account", "expected_group_account",
           "cost_center_code", "department_code", "dept_function", "currency_code",
           "amount_local", "ic_partner_code", "customer_code", "product_code",
           "line_attributes"]
