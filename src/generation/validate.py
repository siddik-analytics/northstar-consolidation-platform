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
                     load_ic_anchor, load_source_coa, operating_entities, read_csv)
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
    got = float(tlb[0]["closing_principal"]) / 1e6 if tlb else 0.0
    want = bs["tlb_gross"]["FY2025A"]
    r.add("P2-REC-04", "Debt schedule agrees with the anchored term loan balance", "BLOCKING",
          "PASS" if abs(got - want) < 0.02 else "FAIL", f"{got:.3f}", f"{want:.3f}")

    # ---------------- intercompany -------------------------------------------
    icj = live[live["ic_partner_code"] != ""]
    pair = defaultdict(float)
    for ent, pt, pk, amt, ccy in zip(icj["entity_code"], icj["ic_partner_code"],
                                     icj["period_key"], icj["amount_local"],
                                     icj["currency_code"]):
        key = tuple(sorted((ent, pt))) + (pk,)
        pair[key] += amt * rate(ccy, pk, "AVG")
    worst_ic = max((abs(v) for v in pair.values()), default=0.0)
    r.add("P2-IC-01", "Intercompany pairs match in USD before injected faults", "BLOCKING",
          "PASS" if worst_ic <= 1.0 else "FAIL", f"{worst_ic:.4f}", "1.00",
          f"{len(pair)} entity-pair-periods")

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

    # ---------------- group reporting measurement reserve --------------------
    tdiff = read_csv(REFERENCE / "translation_difference.csv")
    worst_res = max((abs(float(row["reserve_pct_of_total_assets"])) for row in tdiff),
                    default=0.0)
    r.add("P2-RES-01", "Measurement reserve stays immaterial to layer-1 assets",
          "BLOCKING", "PASS" if worst_res <= 2.0 else "FAIL", f"{worst_res:.2f}%", "2.00%",
          "329100 is disclosed, not hidden; Phase 4 replaces it with a computed CTA")

    worst_cash = max((abs(float(row["cash_variance_vs_anchor"])) for row in tdiff),
                     default=0.0)
    r.add("P2-RES-02", "Cash carries none of the measurement difference", "BLOCKING",
          "PASS" if worst_cash <= 0.01 else "FAIL", f"{worst_cash:.4f}", "0.01",
          "cash is externally verifiable and ties to the anchor exactly")

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
