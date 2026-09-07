"""
The Phase 2 anchor bridge.

Phase 2 generates LAYER 1 only -- what each entity's own ledger says.  The approved
anchors are the CONSOLIDATED result.  The two differ by known, listed amounts, and
comparing generated data straight to the consolidated anchor would be wrong in both
directions at once.

This module derives, deterministically from the approved anchors, what the sum of the
source ledgers must be.  Two kinds of difference:

  Intercompany gross-up   Layer 1 contains both legs of every intercompany transaction.
                          Revenue, cost of sales, operating expense, receivables and
                          payables are all HIGHER at source than consolidated.

  Phase 4 constructs      Goodwill, acquired intangibles, the deferred tax on them, their
                          amortisation and unrealised intercompany profit exist only at
                          layer 3.  No source ledger carries them, so source amortisation
                          is nil and source net income is correspondingly higher.

The output is the reconciliation target the Phase 2 controls test against, and the
statement a reviewer needs in order to check the numbers themselves.
"""

from __future__ import annotations

from .common import ANCHORS, COLS, load_anchor, write_csv

# Source ledgers carry current tax only; the entire deferred tax balance and movement is a
# Phase 4 consolidation item, consistent with the effective-rate scope decision in OQ-05.
BRIDGE_NOTES = {
    "revenue": "plus both legs of intercompany revenue (management fee, product, service, royalty)",
    "cost_of_sales": "plus intercompany product and service cost borne by the buying entity",
    "opex": "plus intercompany management fee and royalty expense borne by the paying entity",
    "amortisation": "nil at source: all amortisation is of acquired intangibles, a layer-3 item",
    "tax": "current tax only; deferred tax is a layer-3 item",
    "ar": "plus intercompany receivables and the treasury current account",
    "ap": "plus intercompany payables and the treasury current account",
    "inventory": "gross of unrealised intercompany profit, which is eliminated at layer 3",
    "goodwill": "nil at source: recognised only on consolidation",
    "intangibles_net": "nil at source: recognised only on consolidation",
    "dtl": "nil at source: arises on the purchase price allocation",
    "rou_asset": "excludes the Kestrel entities, which do not recognise operating leases locally",
    "operating_lease": "excludes the Kestrel entities, which do not recognise operating leases locally",
    "investments_in_subsidiaries": "held at cost at the parent; eliminated at layer 3",
}


def build_targets() -> list[dict]:
    pl = load_anchor("income_statement")
    bs = load_anchor("balance_sheet")
    cf = load_anchor("cash_flow")
    ic = load_anchor("intercompany", key="measure")

    def s(d, k, c):
        return d[k][c]

    rows: list[dict] = []

    def add(statement: str, item: str, values: dict[str, float], basis: str) -> None:
        rows.append(dict(statement=statement, line_item=item, basis=basis,
                         **{c: round(values[c], 6) for c in COLS}))

    ic_rev = {c: s(ic, "mgmt_fee", c) + s(ic, "ic_product_sales", c)
              + s(ic, "ic_service_sales", c) + s(ic, "ic_royalty", c) for c in COLS}
    ic_cos = {c: s(ic, "ic_product_sales", c) + s(ic, "ic_service_sales", c) for c in COLS}
    ic_opex = {c: s(ic, "mgmt_fee", c) + s(ic, "ic_royalty", c) for c in COLS}

    add("IS", "revenue", {c: s(pl, "revenue", c) + ic_rev[c] for c in COLS},
        BRIDGE_NOTES["revenue"])
    add("IS", "cost_of_sales", {c: s(pl, "cost_of_sales", c) + ic_cos[c] for c in COLS},
        BRIDGE_NOTES["cost_of_sales"])
    add("IS", "opex", {c: s(pl, "opex", c) + ic_opex[c] for c in COLS},
        BRIDGE_NOTES["opex"])
    add("IS", "depreciation", {c: s(pl, "depreciation", c) for c in COLS},
        "unchanged: entities own their property, plant and equipment")
    add("IS", "amortisation", {c: 0.0 for c in COLS}, BRIDGE_NOTES["amortisation"])
    add("IS", "net_interest", {c: s(pl, "net_interest", c) for c in COLS},
        "unchanged: intercompany interest income and expense net within layer 1")
    add("IS", "intercompany_revenue", ic_rev, "eliminated in full at layer 2")
    add("IS", "intercompany_interest", {c: s(ic, "ic_interest", c) for c in COLS},
        "both legs present at source; eliminated at layer 2")
    add("IS", "current_tax",
        {c: s(pl, "tax", c) - s(cf, "deferred_tax", c) for c in COLS}, BRIDGE_NOTES["tax"])

    for cap in ("cash", "contract_assets", "prepaid", "other_nca", "ppe_net",
                "contract_liabilities", "accrued", "tax_payable", "other_ltl",
                "finance_lease", "rcf"):
        add("BS", cap, {c: s(bs, cap, c) for c in COLS}, "unchanged")
    add("BS", "ar", {c: s(bs, "ar", c) for c in COLS},
        "trade receivables only; intercompany shown separately")
    add("BS", "ap", {c: s(bs, "ap", c) for c in COLS},
        "trade payables only; intercompany shown separately")
    add("BS", "inventory",
        {c: s(bs, "inventory", c) + s(ic, "pup_in_inventory", c) for c in COLS},
        BRIDGE_NOTES["inventory"])
    add("BS", "intercompany_receivables", {c: s(ic, "ic_ar_ap_close", c) for c in COLS},
        "trade intercompany only; the treasury current account is additional and nets to nil")
    add("BS", "intercompany_loans", {c: s(ic, "ic_loan_close", c) for c in COLS},
        "both legs present at source; eliminated at layer 2")
    add("BS", "tlb_gross", {c: s(bs, "tlb_gross", c) for c in COLS},
        "all external debt sits with Topco")
    add("BS", "goodwill", {c: 0.0 for c in COLS}, BRIDGE_NOTES["goodwill"])
    add("BS", "intangibles_net", {c: 0.0 for c in COLS}, BRIDGE_NOTES["intangibles_net"])
    add("BS", "dtl", {c: 0.0 for c in COLS}, BRIDGE_NOTES["dtl"])
    return rows


def write_targets() -> int:
    rows = build_targets()
    write_csv(ANCHORS / "phase02_source_layer_targets.csv",
              ["statement", "line_item", "basis"] + COLS,
              [[r["statement"], r["line_item"], r["basis"]]
               + [f"{r[c]:.6f}" for c in COLS] for r in rows])
    return len(rows)
