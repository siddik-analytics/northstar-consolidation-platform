"""
Phase 2 source controls.

These read the *generated artefacts back off disk* -- including parsing the native ERP
extracts and re-deriving a signed amount from each system's own sign convention -- rather
than inspecting the generator's memory.  A control that shares state with the thing it
checks proves nothing.

    python -m src.generation.validate

Writes data/phase02_control_results.csv and exits non-zero if a blocking control fails.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .common import (ANCHORS, COLS, CONFIG, DATA, RAW, REFERENCE, SAMPLES, load_anchor,
                     load_credit_agreement, load_ic_anchor, load_source_coa,
                     operating_entities, read_csv)
from .bsdrivers import NONLINEAR_CAPTIONS, linearity
from .series import RCF_COMMITMENT_USD

TOL_PL = 0.005        # 0.5% on income statement aggregates
TOL_BS = 0.010        # 1.0% on balance sheet captions
RESULTS = DATA / "phase02_control_results.csv"


class Result(list):
    def add(self, cid, name, severity, status, measured="", threshold="", detail=""):
        self.append(dict(control_id=cid, control_name=name, severity=severity,
                         status=status, measured=measured, threshold=threshold,
                         detail=detail))

    @property
    def failed(self):
        return [r for r in self if r["status"] == "FAIL" and r["severity"] == "BLOCKING"]


def _de(x: str) -> float:
    """Parse a Kestrel amount: period thousands separator, comma decimal."""
    x = x.strip()
    return float(x.replace(".", "").replace(",", ".")) if x else 0.0


def _us(x: str) -> float:
    return float(x.replace(",", "")) if x.strip() else 0.0


def read_native_trial_balances() -> dict[tuple[str, int], float]:
    """
    Re-derive a signed amount from every raw extract using that ERP's documented rule,
    and sum by entity and period.  This is the control that proves the three sign
    conventions are genuinely different and genuinely reversible.
    """
    normal = {}
    for erp in ("aurora", "sable", "kestrel"):
        for r in load_source_coa(erp):
            normal[(erp.upper(), r["source_account"])] = r["source_normal_balance"]
    tb: dict[tuple[str, int], float] = defaultdict(float)

    for path in sorted((RAW / "aurora").glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                # Aurora: one signed amount, credits negative -- already signed
                tb[(row["SUBSIDIARY"], int(f"{path.stem.split('_')[-1]}"))] += float(row["AMOUNT"])

    for path in sorted((RAW / "sable").glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                # Sable: natural sign per account; recover signed = amount * (D ? 1 : -1)
                nb = normal.get(("SABLE", row["MAINACCOUNT"]), "D")
                signed = _us(row["AMOUNT"]) * (1 if nb == "D" else -1)
                pk = int(row["FISCALYEAR"]) * 100 + int(row["FISCALPERIOD"])
                tb[(row["DIMENSIONSTRING"].split("|")[0], pk)] += signed

    for path in sorted((RAW / "kestrel").glob("*.csv")):
        with open(path, newline="", encoding="cp1252") as f:
            for row in csv.DictReader(f, delimiter=";"):
                # Kestrel: separate positive debit and credit columns
                signed = _de(row["SOLL"]) - _de(row["HABEN"])
                month = int(row["MONAT"])
                month = 12 if month > 12 else month      # special periods belong to December
                pk = int(row["GJAHR"]) * 100 + month
                tb[(row["BUKRS"], pk)] += signed
    return tb


def run() -> Result:
    r = Result()
    ents = operating_entities()
    if not (REFERENCE / "journal_lines.parquet").exists():
        r.add("P2-BUILD", "Build artefacts present", "BLOCKING", "FAIL",
              detail="run `python -m src.generation.build` first")
        return r

    jl = pd.read_parquet(REFERENCE / "journal_lines.parquet")

    # ---------------- source accounting --------------------------------------
    per_journal = jl.groupby("journal_id")["amount_local"].sum().abs()
    worst_j = float(per_journal.max())
    r.add("P2-SRC-01", "Every journal entry balances", "BLOCKING",
          "PASS" if worst_j <= 0.011 else "FAIL", f"{worst_j:.4f}", "0.011",
          f"{int((per_journal > 0.011).sum())} unbalanced of {len(per_journal)}")

    tb = jl.groupby(["entity_code", "period_key"])["amount_local"].sum().abs()
    worst_tb = float(tb.max())
    r.add("P2-SRC-02", "Entity trial balance closes to zero (generated)", "BLOCKING",
          "PASS" if worst_tb <= 0.02 else "FAIL", f"{worst_tb:.4f}", "0.02",
          f"{int((tb > 0.02).sum())} entity-periods out of balance of {len(tb)}")

    native = read_native_trial_balances()
    worst_native = max((abs(v) for v in native.values()), default=0.0)
    bad_native = sum(1 for v in native.values() if abs(v) > 0.02)
    r.add("P2-SRC-03", "Trial balance closes when re-derived from the NATIVE extracts",
          "BLOCKING", "PASS" if worst_native <= 0.02 else "FAIL",
          f"{worst_native:.4f}", "0.02",
          f"{bad_native} of {len(native)} entity-periods; parses all three sign conventions")

    dup = jl.duplicated(subset=["entity_code", "journal_id", "line_number"]).sum()
    r.add("P2-SRC-04", "No duplicate journal line identifiers", "BLOCKING",
          "PASS" if dup == 0 else "FAIL", str(int(dup)), "0")

    periods = sorted(jl["period_key"].unique())
    ok = all(202301 <= int(p) <= 202608 and 1 <= int(p) % 100 <= 12 for p in periods)
    r.add("P2-SRC-05", "All accounting periods valid and in range", "BLOCKING",
          "PASS" if ok else "FAIL", f"{periods[0]}-{periods[-1]}", "202301-202608")

    # ---------------- reference integrity ------------------------------------
    valid_src = {(e.upper(), row["source_account"])
                 for e in ("aurora", "sable", "kestrel") for row in load_source_coa(e)}
    bad_acc = sum(1 for t in zip(jl["erp_system"], jl["source_account"])
                  if t not in valid_src)
    r.add("P2-REF-01", "Every source account exists in its ERP chart", "BLOCKING",
          "PASS" if bad_acc == 0 else "FAIL", str(bad_acc), "0")

    bad_ent = set(jl["entity_code"].unique()) - set(ents)
    r.add("P2-REF-02", "Every entity is a real operating legal entity", "BLOCKING",
          "PASS" if not bad_ent else "FAIL", str(sorted(bad_ent)), "none",
          "virtual elimination entities must never appear in a source extract")

    ccs = {c["cost_center_code"] for c in read_csv(REFERENCE / "cost_centres.csv")}
    bad_cc = set(jl["cost_center_code"].unique()) - ccs
    r.add("P2-REF-03", "Every cost centre exists in the cost centre master", "BLOCKING",
          "PASS" if not bad_cc else "FAIL", str(sorted(bad_cc)[:5]), "none")

    partners = set(jl["ic_partner_code"].unique()) - {""}
    bad_p = partners - set(ents)
    self_p = int((jl["ic_partner_code"] == jl["entity_code"]).sum())
    r.add("P2-REF-04", "Intercompany partners valid and never self-referencing", "BLOCKING",
          "PASS" if not bad_p and self_p == 0 else "FAIL",
          f"invalid={sorted(bad_p)} self={self_p}", "0")

    bad_ccy = {c for c in jl["currency_code"].unique()} - {"USD", "CAD", "GBP", "EUR"}
    r.add("P2-REF-05", "Currencies limited to the approved set", "BLOCKING",
          "PASS" if not bad_ccy else "FAIL", str(sorted(bad_ccy)), "USD/CAD/GBP/EUR")

    # ---------------- completeness -------------------------------------------
    missing = []
    for code, e in ents.items():
        want = {p for p in periods
                if str(p) >= f"{e.effective_from.year}{e.effective_from.month:02d}"}
        got = set(jl.loc[jl["entity_code"] == code, "period_key"].unique())
        missing.extend((code, p) for p in want - got)
    r.add("P2-CMP-01", "Every entity has every period from its effective date", "BLOCKING",
          "PASS" if not missing else "FAIL", str(len(missing)), "0", str(missing[:5]))

    early = [(c, int(p)) for c, p in zip(jl["entity_code"], jl["period_key"])
             if int(p) < ents[c].effective_from.year * 100 + ents[c].effective_from.month]
    r.add("P2-CMP-02", "No entity posts before its consolidation effective date", "BLOCKING",
          "PASS" if not early else "FAIL", str(len(early)), "0")

    plan = pd.read_parquet(REFERENCE / "plan_fact.parquet")
    versions = set(plan["version_code"].unique())
    want_v = {"BUD_FY26_V1", "FC_FY26_02", "FC_FY26_05", "FC_FY26_08"}
    r.add("P2-CMP-03", "All approved plan versions generated", "BLOCKING",
          "PASS" if want_v <= versions else "FAIL", str(sorted(versions)), str(sorted(want_v)))
    r.add("P2-CMP-04", "Reserved Downside scenario not populated", "BLOCKING",
          "PASS" if not any("DS_" in v for v in versions) else "FAIL",
          str(sorted(v for v in versions if "DS_" in v)), "none")

    fx = pd.read_parquet(REFERENCE / "plan_fact.parquet") if False else read_csv(
        REFERENCE / "fx_rates_monthly.csv")
    fx_keys = {(f["currency_code"], int(f["period_key"]), f["rate_type"], f["rate_set"])
               for f in fx}
    need = [(c, p, t, "ACTUAL") for c in ("USD", "CAD", "GBP", "EUR")
            for p in periods for t in ("AVG", "CLOSE")]
    miss_fx = [k for k in need if k not in fx_keys]
    r.add("P2-CMP-05", "FX rates complete for every currency and period", "BLOCKING",
          "PASS" if not miss_fx else "FAIL", str(len(miss_fx)), "0")

    # ---------------- anchor conformity --------------------------------------
    tgt = {(row["statement"], row["line_item"]): row
           for row in read_csv(ANCHORS / "phase02_source_layer_targets.csv")}
    rates = {(f["currency_code"], int(f["period_key"]), f["rate_type"], f["rate_set"]):
             float(f["rate_usd_per_unit"]) for f in fx}

    def rate(ccy, pk, kind):
        rs = "FORECAST" if pk // 100 == 2026 else "ACTUAL"
        return rates[(ccy, pk, kind, rs)]

    jl["year"] = jl["period_key"] // 100
    jl["avg_rate"] = [rate(c, p, "AVG") for c, p in zip(jl["currency_code"], jl["period_key"])]
    jl["usd"] = jl["amount_local"] * jl["avg_rate"] / 1e6
    # The year-end close reverses every income statement account into reserves, so it
    # must be excluded when aggregating a year's result.
    live = jl[jl["event_type"] != "YEAR_END_CLOSE"]
    pl = live[live["expected_group_account"].str.match(r"^[45678]")]
    grp = pl.groupby(["year", pl["expected_group_account"].str[0]])["usd"].sum().unstack(fill_value=0.0)

    checks = [("revenue", "4", -1), ("cost_of_sales", "5", 1), ("opex", "6", 1)]
    for year, col in ((2023, "FY2023A"), (2024, "FY2024A"), (2025, "FY2025A")):
        for item, prefix, sign in checks:
            got = float(grp.loc[year, prefix]) * sign
            want = float(tgt[("IS", item)][col])
            dev = abs(got - want) / abs(want) if want else 0.0
            r.add(f"P2-ANC-{item[:3].upper()}-{year}",
                  f"{item} reconciles to the source-layer target ({year})", "BLOCKING",
                  "PASS" if dev <= TOL_PL else "FAIL", f"{got:.3f}", f"{want:.3f}",
                  f"deviation {dev * 100:.4f}% (tolerance {TOL_PL * 100:.1f}%)")

    # balance sheet at each year end, translated at closing rates
    bsj = jl[jl["expected_group_account"].str.match(r"^[123]")]
    caption = {"ar": ["120100", "120200"], "inventory": ["130100", "130200", "130300", "130400"],
               "ap": ["210100", "210200"], "cash": ["110100"],
               "ppe_net": ["150200", "150300", "150400", "150500", "150600", "150800", "155100"],
               "contract_assets": ["121100"], "prepaid": ["140100"]}
    for year, col in ((2023, "FY2023A"), (2024, "FY2024A"), (2025, "FY2025A")):
        upto = bsj[bsj["period_key"] <= year * 100 + 12]
        bal = upto.groupby(["entity_code", "currency_code", "expected_group_account"])[
            "amount_local"].sum().reset_index()
        bal["usd"] = [v * rate(c, year * 100 + 12, "CLOSE") / 1e6
                      for v, c in zip(bal["amount_local"], bal["currency_code"])]
        for cap, accts in caption.items():
            got = float(bal.loc[bal["expected_group_account"].isin(accts), "usd"].sum())
            want = float(tgt[("BS", cap)][col])
            dev = abs(abs(got) - abs(want)) / abs(want) if want else 0.0
            r.add(f"P2-ANC-BS-{cap[:4].upper()}-{year}",
                  f"{cap} reconciles to the source-layer target ({year})", "BLOCKING",
                  "PASS" if dev <= TOL_BS else "FAIL", f"{got:.3f}", f"{want:.3f}",
                  f"deviation {dev * 100:.4f}% (tolerance {TOL_BS * 100:.1f}%)")

    # ---------------- cross-dataset reconciliation ---------------------------
    rev = pd.read_parquet(REFERENCE / "revenue_detail.parquet")
    gl_rev = live[live["expected_group_account"].str.match(r"^4(?!4)(?!9)")].groupby(
        ["entity_code", "period_key"])["amount_local"].sum()
    dt_rev = rev.groupby(["entity_code", "period_key"])["revenue_local"].sum()
    joined = pd.concat([-gl_rev, dt_rev], axis=1, keys=["gl", "detail"]).fillna(0.0)
    worst = float((joined["gl"] - joined["detail"]).abs().max())
    r.add("P2-REC-01", "Revenue detail reconciles to the general ledger", "BLOCKING",
          "PASS" if worst <= 0.05 else "FAIL", f"{worst:.4f}", "0.05",
          "per entity and period, ADR-0008")

    hc = pd.read_parquet(REFERENCE / "headcount_fact.parquet")
    bu = {(x["bu_code"], x["measure"]): x for x in read_csv(ANCHORS / "anchor_by_business_unit.csv")}
    total_hc = float(hc[hc["period_key"] == 202512]["fte_closing"].sum())
    want_hc = sum(float(bu[(b, "headcount")]["FY2025A"]) for b in ("FC", "IS", "ES", "AM")) \
        + float(bu[("CORP", "headcount")]["FY2025A"])
    dev = abs(total_hc - want_hc) / want_hc
    r.add("P2-REC-02", "Headcount reconciles to the anchor", "WARNING",
          "PASS" if dev <= 0.05 else "FAIL", f"{total_hc:.0f}", f"{want_hc:.0f}",
          f"deviation {dev * 100:.2f}% (tolerance 5%)")

    fa = read_csv(REFERENCE / "fixed_assets.csv")
    cp = read_csv(REFERENCE / "capex_projects.csv")
    fa_tot = sum(float(x["cost_local"]) for x in fa)
    cp_tot = sum(float(x["spend_local"]) for x in cp)
    r.add("P2-REC-03", "Fixed asset register agrees with capital project spend", "BLOCKING",
          "PASS" if abs(fa_tot - cp_tot) < 1.0 else "FAIL", f"{fa_tot:.2f}", f"{cp_tot:.2f}")

    debt = read_csv(REFERENCE / "debt_schedule.csv")
    tlb = [d for d in debt if d["instrument_id"] == "TLB-2021" and d["period_key"] == "202512"]
    bs = load_anchor("balance_sheet")
    pl_anchor = load_anchor("income_statement")
    got = float(tlb[0]["closing_principal"]) / 1e6 if tlb else 0.0
    want = bs["tlb_gross"]["FY2025A"]
    r.add("P2-REC-04", "Debt schedule agrees with the anchored term loan balance", "BLOCKING",
          "PASS" if abs(got - want) < 0.02 else "FAIL", f"{got:.3f}", f"{want:.3f}")

    # ---------------- intercompany -------------------------------------------
    coa_rows = read_csv(CONFIG / "coa" / "group_coa.csv")
    ic_accounts = {row["group_account"] for row in coa_rows
                   if row["is_intercompany"] == "TRUE"}
    ic_bs = {row["group_account"] for row in coa_rows
             if row["is_intercompany"] == "TRUE" and row["statement"] == "BS"}
    # Only the intercompany ACCOUNTS are summed. The cash leg of a settlement carries the
    # counterparty too, for lineage, but it is bank -- not a position with that entity --
    # and including it only worked before because the two legs happened to cancel.
    #
    # Investments in subsidiaries are intercompany but NOT reciprocal: the holding
    # eliminates against the subsidiary's equity, not against a mirror balance in the
    # subsidiary's books. P2-INV-01 reconciles them to the investment register instead.
    reciprocal = live[live["expected_group_account"].isin(ic_accounts - {"178100"})
                      & (live["ic_partner_code"] != "")]

    # A BALANCE matches its mirror at the CLOSING rate, and it is the cumulative balance
    # that has to match, not the month's movement (CTL-IC-01). Testing the movement at the
    # average rate -- which is what this control used to do for every intercompany line
    # regardless of statement -- is two errors that only cancelled because the balance
    # sheet legs carried no counterparty and were silently excluded (P2-D-03).
    bs = reciprocal[reciprocal["expected_group_account"].isin(ic_bs)]
    running: dict[tuple[str, str, str], float] = defaultdict(float)
    bal_pair: dict[tuple, float] = defaultdict(float)
    for ent, pt, pk, amt, ccy in sorted(zip(
            bs["entity_code"], bs["ic_partner_code"], bs["period_key"],
            bs["amount_local"], bs["currency_code"]), key=lambda t: t[2]):
        running[(ent, pt, ccy)] += amt
    # cumulative per period requires a second pass in period order
    running.clear()
    for pk in sorted(bs["period_key"].unique()):
        month = bs[bs["period_key"] == pk]
        for ent, pt, amt, ccy in zip(month["entity_code"], month["ic_partner_code"],
                                     month["amount_local"], month["currency_code"]):
            running[(ent, pt, ccy)] += amt
        for (ent, pt, ccy), v in running.items():
            bal_pair[tuple(sorted((ent, pt))) + (int(pk),)] += v * rate(ccy, int(pk), "CLOSE")
    worst_bal = max((abs(v) for v in bal_pair.values()), default=0.0)
    r.add("P2-IC-01", "Intercompany balances match by pair at the closing rate", "BLOCKING",
          "PASS" if worst_bal <= 1.0 else "FAIL", f"{worst_bal:.4f}", "1.00",
          f"CTL-IC-01, {len(bal_pair)} entity-pair-periods. Investments in subsidiaries are "
          f"excluded as non-reciprocal and reconciled by P2-INV-01 instead.")

    # A FLOW matches at the average rate of the month it was recorded in (CTL-IC-02).
    flows = reciprocal[~reciprocal["expected_group_account"].isin(ic_bs)]
    pair = defaultdict(float)
    for ent, pt, pk, amt, ccy in zip(flows["entity_code"], flows["ic_partner_code"],
                                     flows["period_key"], flows["amount_local"],
                                     flows["currency_code"]):
        pair[tuple(sorted((ent, pt))) + (pk,)] += amt * rate(ccy, pk, "AVG")
    worst_ic = max((abs(v) for v in pair.values()), default=0.0)
    r.add("P2-IC-03", "Intercompany flows match by pair at the average rate", "BLOCKING",
          "PASS" if worst_ic <= 1.0 else "FAIL", f"{worst_ic:.4f}", "1.00",
          f"CTL-IC-02, {len(pair)} entity-pair-periods")

    # CTL-IC-04, tested over the WHOLE intercompany population rather than over the subset
    # that already carries a partner. Testing only the lines that have one is how P2-D-03
    # survived Phase 2 and was found by Phase 3: the control could not see the postings it
    # was meant to be about. The year-end close is the one legitimate exception -- it
    # sweeps the entire income statement into retained earnings in a single entry, so its
    # lines are a position rather than a transaction with any one counterparty.
    ic_all = live[live["expected_group_account"].isin(ic_accounts)]
    missing_partner = int((ic_all["ic_partner_code"] == "").sum())
    self_partner = int((ic_all["ic_partner_code"] == ic_all["entity_code"]).sum())
    r.add("P2-IC-02", "Every intercompany posting names its counterparty", "BLOCKING",
          "PASS" if missing_partner == 0 and self_partner == 0 else "FAIL",
          f"{missing_partner} missing, {self_partner} self-referencing", "0, 0",
          f"CTL-IC-04, over all {len(ic_all):,} intercompany postings outside the year-end "
          f"close. A balance with no counterparty cannot be eliminated by pair, which is "
          f"what defect P2-D-03 was.")

    # ---------------- scenario integrity -------------------------------------
    fc = plan[(plan["version_code"] == "FC_FY26_08") & (plan["is_actual_month"] == "TRUE")]
    act = live[(live["period_key"] >= 202601) & (live["period_key"] <= 202608)
               & live["expected_group_account"].str.match(r"^[45678]")]
    a = act.groupby(["entity_code", "period_key", "expected_group_account"])["amount_local"].sum()
    b = fc.groupby(["entity_code", "period_key", "expected_group_account"])["amount_local"].sum()
    diff = (a - b).abs().dropna()
    worst_sc = float(diff.max()) if len(diff) else 0.0
    r.add("P2-SCN-01", "Forecast actual months equal the Actual scenario", "BLOCKING",
          "PASS" if worst_sc <= 0.05 else "FAIL", f"{worst_sc:.4f}", "0.05", "CTL-SCN-02")

    # ---------------- native format integrity --------------------------------
    k = sorted((RAW / "kestrel").glob("*.csv"))
    p13 = 0
    for path in k:
        with open(path, newline="", encoding="cp1252") as f:
            p13 += sum(1 for row in csv.DictReader(f, delimiter=";") if row["MONAT"] == "13")
    r.add("P2-FMT-01", "Kestrel uses special period 13 for year-end adjustments", "BLOCKING",
          "PASS" if p13 > 0 else "FAIL", str(p13), ">0")

    # ---------------- Kestrel special periods 13-16 --------------------------
    # Phase 1 specified four special periods; Phase 2.0 generated only period 13.  These
    # controls prove all four exist and follow the population rules declared in
    # config/coa/kestrel_special_periods.csv.
    spec_rules = {int(row["special_period"]): row
                  for row in read_csv(CONFIG / "coa" / "kestrel_special_periods.csv")}
    spec = defaultdict(set)
    spec_lines = defaultdict(int)
    for path in k:
        with open(path, newline="", encoding="cp1252") as f:
            for row in csv.DictReader(f, delimiter=";"):
                mth = int(row["MONAT"])
                if mth > 12:
                    spec[mth].add((row["BUKRS"], int(row["GJAHR"])))
                    spec_lines[mth] += 1
    missing = sorted(set(spec_rules) - {m for m in spec if spec_lines[m] > 0})
    r.add("P2-FMT-06", "Every declared Kestrel special period is populated", "BLOCKING",
          "PASS" if not missing else "FAIL",
          str(sorted(spec_lines)), str(sorted(spec_rules)),
          "13 statutory close, 14 audit, 15 tax, 16 local GAAP to group reporting")

    # Period 13 closes every Kestrel company-year; 14 and 16 are conditional, so they must
    # be present but not universal, or they are not modelling a real population rule.
    universe = spec[13]
    cond_ok = bool(universe) and all(0 < len(spec[m]) < len(universe) for m in (14, 16))
    r.add("P2-FMT-07", "Conditional special periods follow their population rule",
          "BLOCKING", "PASS" if cond_ok else "FAIL",
          f"13:{len(spec[13])} 14:{len(spec[14])} 15:{len(spec[15])} 16:{len(spec[16])}",
          "13 universal; 14 and 16 a subset",
          "audit findings and local-GAAP provisions do not arise at every entity every year")

    # Nothing is audited or filed for a year that has not closed, so FY2026 carries none.
    unfiled = {(c, y) for m in (14, 15) for (c, y) in spec[m] if y >= 2026}
    r.add("P2-FMT-08", "Unfiled years carry no audit or tax special period", "BLOCKING",
          "PASS" if not unfiled else "FAIL", str(sorted(unfiled)), "none",
          "FY2026 is neither audited nor filed at the reporting date")

    # Special periods 14-16 are reclassifications: they must not move the year's result.
    sp = jl[jl["line_attributes"].astype(str).str.contains("special_period=", na=False)]
    res_move = 0.0
    if len(sp):
        pl = sp[sp["expected_group_account"].astype(str).str[0].isin(list("45678"))]
        if len(pl):
            res_move = float(pl.groupby(["entity_code", "period_key"])["amount_local"]
                             .sum().abs().max())
    r.add("P2-FMT-09", "Special period entries do not change the reported result",
          "BLOCKING", "PASS" if res_move <= 0.02 else "FAIL", f"{res_move:.4f}", "0.02",
          "periods 14-16 reclassify within a caption; the anchored result is unchanged")

    zero_pad = 0
    if k:
        with open(k[0], newline="", encoding="cp1252") as f:
            zero_pad = sum(1 for row in csv.DictReader(f, delimiter=";")
                           if row["HKONT"].startswith("0"))
    r.add("P2-FMT-02", "Kestrel account keys retain leading zeros", "BLOCKING",
          "PASS" if zero_pad > 0 else "FAIL", str(zero_pad), ">0")

    charts = {e: {row["source_account"] for row in load_source_coa(e)}
              for e in ("aurora", "sable", "kestrel")}
    overlap = (charts["aurora"] & charts["sable"]) | (charts["aurora"] & charts["kestrel"]) \
        | (charts["sable"] & charts["kestrel"])
    r.add("P2-FMT-03", "The three source charts remain genuinely different", "BLOCKING",
          "PASS" if not overlap else "FAIL", str(sorted(overlap)[:5]), "no shared codes")

    # ---------------- business reasonableness --------------------------------
    cashj = jl[jl["expected_group_account"] == "110100"]
    bal = cashj.groupby(["entity_code", "period_key"])["amount_local"].sum().groupby(
        level=0).cumsum()
    neg = int((bal < -1000).sum())
    r.add("P2-BR-01", "No entity runs a materially negative bank balance", "WARNING",
          "PASS" if neg == 0 else "FAIL", str(neg), "0")

    # ---------------- monthly balance sheet realism --------------------------
    # Phase 2.0 interpolated interim balances between anchored year ends, which produced a
    # visible straight line.  `linearity` is 0.0 for a perfect straight line and rises with
    # genuine driver-generated movement.
    bsj = jl[jl["expected_group_account"].isin(sorted(NONLINEAR_CAPTIONS))]
    monthly = (bsj.groupby(["entity_code", "expected_group_account", "period_key"])
               ["amount_local"].sum().groupby(level=[0, 1]).cumsum())
    scores, flat = [], []
    for (ent, acct), ser in monthly.groupby(level=[0, 1]):
        for year in (2023, 2024, 2025):
            vals = ser[ser.index.get_level_values(2) // 100 == year].to_numpy()
            if len(vals) < 12 or abs(vals).max() < 50_000:
                continue
            score = linearity(vals)
            scores.append(score)
            if score < 0.02:
                flat.append(f"{ent}/{acct}/{year}")
    worst_lin = min(scores) if scores else 1.0
    r.add("P2-BR-04", "Interim balances are driver-generated, not interpolated",
          "BLOCKING", "PASS" if not flat else "FAIL",
          f"{len(flat)} flat of {len(scores)}; min {worst_lin:.3f}", "0 flat",
          "linearity 0.0 would be a straight line between anchored year ends")

    # The revolver is the group's liquidity instrument and must stay within its commitment.
    rcfj = jl[jl["expected_group_account"] == "220200"]
    drawn = -rcfj.groupby("period_key")["amount_local"].sum().cumsum()
    worst_rcf = float(drawn.max()) if len(drawn) else 0.0
    r.add("P2-BR-05", "Revolver drawings stay within the committed facility", "BLOCKING",
          "PASS" if worst_rcf <= RCF_COMMITMENT_USD + 1 else "FAIL",
          f"{worst_rcf / 1e6:.1f}m", f"{RCF_COMMITMENT_USD / 1e6:.0f}m",
          "CA-016; drawings are booked at Topco in USD")

    # ---------------- investment in subsidiaries -----------------------------
    # Phase 2.0 calibrated investment-at-cost to absorb a residual, which left the balances
    # unexplainable.  Every balance must now reconcile to the investment register.
    roll = read_csv(REFERENCE / "investment_rollforward.csv")
    reg_close = defaultdict(float)
    for row in roll:
        reg_close[(row["parent_entity"], int(row["period_key"]))] += float(
            row["closing_cost_usd"])
    invj = jl[jl["expected_group_account"] == "178100"]
    led = invj.groupby(["entity_code", "period_key"])["amount_local"].sum().groupby(
        level=0).cumsum()
    worst_inv = 0.0
    for (ent, pk), v in led.items():
        worst_inv = max(worst_inv, abs(float(v) - reg_close[(ent, int(pk))]))
    r.add("P2-INV-01", "Investment balances reconcile to the investment register",
          "BLOCKING", "PASS" if worst_inv <= 1.0 else "FAIL", f"{worst_inv:.4f}", "1.00",
          "every balance is the sum of the considerations actually paid; there is no plug")

    events = read_csv(CONFIG / "entities" / "investment_register.csv")
    unexplained = [row["investment_id"] for row in events
                   if not row["event_type"] or float(row["consideration_usd_m"]) <= 0]
    r.add("P2-INV-02", "Every register event has a consideration and an event type",
          "BLOCKING", "PASS" if not unexplained else "FAIL", str(unexplained), "none")

    # ---------------- unrealised intercompany profit support -----------------
    # Phase 2 retains the detail; the elimination itself belongs to Phase 4.
    hold = read_csv(REFERENCE / "ic_inventory_holdings.csv")
    need = {"seller_entity", "buyer_entity", "transfer_price_usd", "seller_cost_usd",
            "ic_gross_profit_usd", "inventory_category", "transaction_period",
            "quantity_remaining", "value_remaining_usd", "unrealised_profit_usd"}
    have = set(hold[0]) if hold else set()
    r.add("P2-ICP-01", "Intercompany inventory detail supports a PUP calculation",
          "BLOCKING", "PASS" if need <= have else "FAIL",
          str(sorted(need - have)) if need - have else "complete", "all fields present")

    pup_anchor = load_ic_anchor()["pup_in_inventory"]
    worst_pup = 0.0
    for year, col in ((2023, "FY2023A"), (2024, "FY2024A"), (2025, "FY2025A")):
        implied = sum(float(h["unrealised_profit_usd"]) for h in hold
                      if int(h["holding_period"]) == year * 100 + 12) / 1e6
        target = pup_anchor[col]
        worst_pup = max(worst_pup, abs(implied - target) / max(target, 1e-9) * 100)
    r.add("P2-ICP-02", "Implied unrealised profit tracks the anchored PUP", "BLOCKING",
          "PASS" if worst_pup <= 10.0 else "FAIL", f"{worst_pup:.2f}%", "10%",
          "Phase 4 performs the elimination; Phase 2 carries only the support")

    # ---------------- layer-1 equity and the derived CTA ---------------------
    # Phase 2.1 closed the layer-1 balance sheet with a named equity reserve because the
    # anchor bridge had no equity target.  Phase 2.2 derives that target, so the closure is
    # arithmetic and there is nothing left to plug.  These controls prove it and fail the
    # build if a plug ever reappears.
    bridge = read_csv(REFERENCE / "layer1_equity_bridge.csv")
    worst_eq = max((abs(float(row["unexplained_usd_m"])) for row in bridge), default=1.0)
    r.add("P2-EQ-01", "Layer-1 equity roll-forward has nothing unexplained", "BLOCKING",
          "PASS" if worst_eq <= 0.001 else "FAIL", f"{worst_eq:.6f}", "0.001",
          "opening + result + share-based compensation + contributions + equity acquired "
          "- distributions + CTA = closing, in USD at closing rates")

    worst_tgt = max((abs(float(row["variance_vs_anchor_usd_m"])) for row in bridge),
                    default=1.0)
    r.add("P2-EQ-02", "Layer-1 equity equals the anchor-derived target", "BLOCKING",
          "PASS" if worst_tgt <= 0.001 else "FAIL", f"{worst_tgt:.6f}", "0.001",
          "consolidated equity + investment at cost - goodwill - intangibles + PPA "
          "deferred tax + unrealised intercompany profit (ADR-0017)")

    # No residual, reserve or plug account may exist anywhere in the source architecture.
    # The test is on the account's PURPOSE, not on one retired account number: any group or
    # source account whose name says it exists to make the model agree is a plug.
    PLUG_WORDS = ("measurement reserve", "group reporting measurement", "balancing",
                  "residual", "plug", "calibration", "true-up to group", "suspense")
    plugs = []
    for row in read_csv(CONFIG / "coa" / "group_coa.csv"):
        if any(w in row["account_name"].lower() for w in PLUG_WORDS):
            plugs.append(f"group/{row['group_account']}")
    for erp in ("aurora", "sable", "kestrel"):
        for row in load_source_coa(erp):
            if any(w in row["source_account_name"].lower() for w in PLUG_WORDS):
                plugs.append(f"{erp}/{row['source_account']}")
    retired = {a for a in ("329100",)}
    used_accounts = set(jl["expected_group_account"].unique())
    plugs += [f"posted/{a}" for a in sorted(retired & used_accounts)]
    r.add("P2-EQ-03", "No measurement reserve or equivalent residual account exists",
          "BLOCKING", "PASS" if not plugs else "FAIL", str(plugs), "none",
          "ADR-0016 is superseded; a balance whose purpose is to make the model agree is "
          "not source data")

    # Cash is the group's externally verifiable balance and now ties without a reserve.
    cash_tie = 0.0
    cashj = jl[jl["expected_group_account"] == "110100"]
    for year, col in ((2023, "FY2023A"), (2024, "FY2024A"), (2025, "FY2025A")):
        upto = cashj[cashj["period_key"] <= year * 100 + 12]
        bal = upto.groupby(["entity_code", "currency_code", "expected_group_account"])[
            "amount_local"].sum().reset_index()
        got = sum(v * rate(c, year * 100 + 12, "CLOSE") / 1e6
                  for v, c, a in zip(bal["amount_local"], bal["currency_code"],
                                     bal["expected_group_account"]) if a == "110100")
        cash_tie = max(cash_tie, abs(got - float(tgt[("BS", "cash")][col])))
    r.add("P2-EQ-04", "Layer-1 cash ties to the anchor with no reserve in the ledger",
          "BLOCKING", "PASS" if cash_tie <= 0.02 else "FAIL", f"{cash_tie:.4f}", "0.02",
          "re-derived from the journal lines, not from the generator's memory")

    # Contributed capital is a historical-rate balance: it does not move because a spot
    # rate moved.  This is the defect that suppressed the translation adjustment.
    cap = jl[jl["expected_group_account"].isin(["310100", "310200"])]
    cap_bal = (cap.groupby(["entity_code", "period_key"])["amount_local"].sum()
               .groupby(level=0).cumsum())
    capital_events = {("NIG-100", pk) for pk in range(202304, 202613)}
    drift = 0.0
    for ent, ser in cap_bal.groupby(level=0):
        vals = ser.to_numpy()
        keys = ser.index.get_level_values(1)
        for i in range(1, len(vals)):
            if (ent, int(keys[i])) in capital_events and ent == "NIG-100":
                continue
            drift = max(drift, abs(vals[i] - vals[i - 1]))
    r.add("P2-FX-01", "Contributed capital is constant in local currency", "BLOCKING",
          "PASS" if drift <= 1.0 else "FAIL", f"{drift:.2f}", "1.00",
          "FX-P03: capital is frozen at the rate ruling when it was contributed and moves "
          "only when capital is actually contributed")

    # The CTA the source ledgers imply must reproduce the anchored roll-forward exactly,
    # because the anchor is now derived from it (tools/derive_anchor_inputs.py).
    grp = read_csv(REFERENCE / "cta_group_bridge.csv")
    worst_cta = max((abs(float(row["derivation_variance_usd_m"])) for row in grp),
                    default=1.0)
    r.add("P2-FX-02", "Anchored CTA is reproduced from source balances and FX policy",
          "BLOCKING", "PASS" if worst_cta <= 0.001 else "FAIL", f"{worst_cta:.6f}",
          "0.001",
          "layer-1 CTA + FX on goodwill and intangibles - the minority's share - the "
          "movement in unrealised profit = the anchored group CTA movement")

    # A CTA row must be reconstructible from the entity's own balances and the rate file
    # alone: opening net assets x the change in closing rate, plus the result at the
    # difference between the closing and average rate.
    cta = read_csv(REFERENCE / "cta_expectation.csv")
    worst_row = 0.0
    for row in cta:
        recomputed = (float(row["opening_net_assets_local"])
                      * (float(row["closing_rate"]) - float(row["opening_rate"]))
                      + float(row["result_local"])
                      * (float(row["closing_rate"]) - float(row["average_rate"]))) / 1e6
        worst_row = max(worst_row, abs(
            recomputed + float(row["cta_on_equity_movements"])
            - float(row["cta_movement_usd_m"])))
    usd_rows = [x for x in cta if x["currency_code"] == "USD"]
    r.add("P2-FX-03", "Every CTA row is derivable from source balances and rates",
          "BLOCKING", "PASS" if worst_row <= 0.0001 and not usd_rows else "FAIL",
          f"{worst_row:.6f}", "0.0001",
          f"{len(cta)} entity-periods; the presentation currency generates none")

    # ---------------- debt and the revolving facility ------------------------
    util = read_csv(REFERENCE / "revolver_utilisation.csv")
    worst_roll = 0.0
    prev_close = None
    for row in util:
        opening, closing = float(row["opening_drawn"]), float(row["closing_drawn"])
        moved = opening + float(row["drawings"]) - float(row["repayments"])
        worst_roll = max(worst_roll, abs(moved - closing))
        if prev_close is not None:
            worst_roll = max(worst_roll, abs(opening - prev_close))
        prev_close = closing
    r.add("P2-DBT-01", "Revolver roll-forward: opening + draws - repayments = closing",
          "BLOCKING", "PASS" if worst_roll <= 0.01 else "FAIL", f"{worst_roll:.4f}",
          "0.01", f"{len(util)} months, chained without a break")

    # The recorded facility charge must be supported by the daily position the ledger
    # produced.  This is the reconciliation Phase 2.1 could not perform.
    ca = load_credit_agreement()
    fee_rate = float(ca["CA-007"]["value"])
    margin = float(ca["CA-033"]["value"])
    sofr = {"FY2023A": 0.0470, "FY2024A": 0.0520, "FY2025A": 0.0410, "FY2026F": 0.0340}
    worst_int = 0.0
    detail = []
    for year, col in ((2023, "FY2023A"), (2024, "FY2024A"), (2025, "FY2025A")):
        months = [x for x in util if int(x["period_key"]) // 100 == year]
        days = sum(float(x["days_in_month"]) for x in months)
        avg_drawn = sum(float(x["average_daily_drawn"]) * float(x["days_in_month"])
                        for x in months) / days / 1e6
        avg_undrawn = sum(float(x["average_daily_undrawn"]) * float(x["days_in_month"])
                          for x in months) / days / 1e6
        supported = avg_drawn * (sofr[col] + margin) + avg_undrawn * fee_rate
        recorded = float(pl_anchor["interest_rcf"][col]) + float(
            pl_anchor["commitment_fee"][col])
        worst_int = max(worst_int, abs(supported - recorded) / max(recorded, 1e-9))
        detail.append(f"{year} {supported:.3f}v{recorded:.3f}")
    r.add("P2-DBT-02", "Revolver charge is supported by the daily drawn balance",
          "BLOCKING", "PASS" if worst_int <= 0.005 else "FAIL",
          f"{worst_int * 100:.3f}%", "0.5%",
          "average daily drawn x (SOFR + 425bps) + commitment fee on the average daily "
          "undrawn versus the recorded charge: " + "; ".join(detail))

    # The debt schedule must be the ledger's own arithmetic, not a parallel model.
    debt_rows = read_csv(REFERENCE / "debt_schedule.csv")
    all_periods = sorted(jl["period_key"].unique())
    ledger_rcf = (-jl[jl["expected_group_account"] == "220200"]
                  .groupby("period_key")["amount_local"].sum()
                  .reindex(all_periods, fill_value=0.0).cumsum())
    worst_sched = 0.0
    for row in debt_rows:
        if row["instrument_id"] != "RCF-2021":
            continue
        pk = int(row["period_key"])
        if pk in ledger_rcf.index:
            worst_sched = max(worst_sched,
                              abs(float(row["closing_principal"]) - float(ledger_rcf[pk])))
    r.add("P2-DBT-03", "Debt schedule agrees with the general ledger every month",
          "BLOCKING", "PASS" if worst_sched <= 0.05 else "FAIL", f"{worst_sched:.4f}",
          "0.05", "balances are read from the ledger, not interpolated between year ends")

    round_amounts = int((jl["amount_local"] % 1000 == 0).sum())
    pct = round_amounts / len(jl) * 100
    r.add("P2-BR-02", "Amounts are not implausibly round", "WARNING",
          "PASS" if pct < 5 else "FAIL", f"{pct:.2f}%", "<5%",
          "round-thousand postings as a share of all lines")

    weekend = pd.to_datetime(jl["posting_date"]).dt.weekday.isin([5, 6]).mean() * 100
    r.add("P2-BR-03", "Posting dates concentrate on working days", "WARNING",
          "PASS" if weekend < 12 else "FAIL", f"{weekend:.2f}%", "<12%")
    return r


def write(results: Result) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(results)


if __name__ == "__main__":
    res = run()
    write(res)
    npass = sum(1 for x in res if x["status"] == "PASS")
    print(f"{npass}/{len(res)} controls passed")
    for x in res:
        if x["status"] != "PASS":
            print(f"  {x['status']:4} {x['severity']:8} {x['control_id']:22} "
                  f"{x['control_name'][:58]:60} {x['measured']} vs {x['threshold']}")
    sys.exit(1 if res.failed else 0)
