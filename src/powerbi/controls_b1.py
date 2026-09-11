"""
The Phase 6B.1 control family: hierarchy sort grain and layer-bridge scope.

    python -m src.powerbi.controls_b1              run and write data/phase06b1_control_results.csv
    python -m src.powerbi.controls_b1 --no-write

Two corrections the owner held Phase 6B for, each with the control that keeps it corrected:

``P6B1-HS``  **hierarchy sort grain.** A reportable caption has exactly one sort value at its
            own grain, the sort keeps the chart's statement order, nothing falls back to the
            alphabet, and the engine resolves the hierarchy without a duplicated caption.
``P6B1-SC``  **layer-bridge scope.** The consolidation bridge and the consolidated measure it
            claims to reconcile are read in the same period context: same slicers, no
            interaction switched off between them, a title that states the scope.
``P6B1-BR``  **layer-bridge reconciliation.** The statutory layers sum to the governed
            consolidated measure on every period basis, the month-grain publication sums
            to the Phase 5 bridge by fiscal year, and the bridge is blank after the close.

The family has its own register so the Phase 6A register -- which the frozen Excel workbook
reads -- keeps its 68 rows.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import duckdb

from . import config as C
from . import dax
from .controls import Result
from .report import build as BUILD
from .report import controls as RK

RESULTS = C.DATA / "phase06b1_control_results.csv"
FAULT_RESULTS = C.DATA / "phase06b1_fault_results.csv"
REPORT_PERIOD = C.REPORT_PERIOD
STATUTORY_LAYERS = "'Consolidation Layer'[in_statutory_view] = TRUE ()"
ACT = "'Scenario'[scenario_code] = \"ACT\""
STAT = "'Reporting Basis'[basis] = \"STATUTORY\""


def _published(con, spec: dict):
    """The published Parquet a table's partition reads -- what the engine actually loads."""
    folder = "35_semantic" if spec["folder"] == "semantic" else "30_marts"
    path = (C.DATA / folder / f"{spec['source']}.parquet").as_posix()
    return f"read_parquet('{path}')"


# ------------------------------------------------------------------ P6B1-HS
def _hierarchy(r: Result, con, live: bool, why: str) -> None:
    # ---- HS-01 one caption, one sort value -- for every sort declaration in the model
    bad = []
    declared = 0
    for spec in C.TABLES:
        src = _published(con, spec)
        for col, key in spec.get("sort", {}).items():
            declared += 1
            captions, pairs, keys = con.execute(f"""
                SELECT count(DISTINCT "{col}"), count(DISTINCT ("{col}", "{key}")),
                       count(DISTINCT "{key}")
                FROM {src}""").fetchone()
            if not (captions == pairs == keys):
                bad.append(f"{spec['name']}[{col}] by [{key}]: {captions} values, "
                           f"{pairs} pairs, {keys} keys")
    r.ok("P6B1-HS-01", "Every sorted column maps one value to exactly one sort key, and back",
         "BLOCKING", not bad, bad or 0, 0,
         f"{declared} sort declarations across the model; a caption with two keys is what "
         f"P6B-D-06 was")

    # ---- HS-02 the account hierarchy's keys are at their own grain and keep statement order
    src = _published(con, next(t for t in C.TABLES if t["name"] == "Account"))
    l1, l2 = con.execute(f"""
        SELECT count(DISTINCT (fs_caption_l1, fs_caption_l1_sort)) - count(DISTINCT fs_caption_l1),
               count(DISTINCT (fs_caption_l2, fs_caption_l2_sort)) - count(DISTINCT fs_caption_l2)
        FROM {src}""").fetchone()
    # statement order: level-1 captions in the chart's order, level-2 captions contiguous
    # under their level-1 caption when sorted by their own key, and neither alphabetical
    rows = con.execute(f"""
        SELECT DISTINCT fs_caption_l1, fs_caption_l1_sort, fs_caption_l2, fs_caption_l2_sort
        FROM {src} ORDER BY fs_caption_l2_sort""").fetchall()
    l1_sequence = []
    for l1_name, *_ in rows:
        if not l1_sequence or l1_sequence[-1] != l1_name:
            l1_sequence.append(l1_name)
    contiguous = len(l1_sequence) == len(set(l1_sequence))
    l1_by_key = [x[0] for x in sorted({(a, b) for a, b, _, _ in rows}, key=lambda t: t[1])]
    same_order = l1_by_key == l1_sequence
    l2_names = [x[2] for x in rows]
    alphabetical = l2_names == sorted(l2_names) or l1_by_key == sorted(l1_by_key)
    expected_first = ("Current Assets", "Revenue")
    firsts = (l1_by_key[0], next(a for a in l1_by_key if a in ("Revenue", "Cost of Sales")))
    r.ok("P6B1-HS-02", "The statement hierarchy sorts at caption grain, in the chart's order, "
         "never alphabetically", "BLOCKING",
         l1 == 0 and l2 == 0 and contiguous and same_order and not alphabetical
         and firsts == expected_first,
         dict(l1_extra_keys=l1, l2_extra_keys=l2, contiguous=contiguous, same_order=same_order,
              alphabetical=alphabetical, first=firsts),
         dict(l1_extra_keys=0, l2_extra_keys=0, contiguous=True, same_order=True,
              alphabetical=False, first=expected_first),
         "each caption's key is the smallest account sort order beneath it, so a caption "
         "sits where its first account sits on the governed chart")

    # ---- HS-03 the engine resolves the hierarchy: no duplicated caption, drill intact
    name = "The engine groups each caption once and drills to the accounts beneath it"
    if not live:
        r.add("P6B1-HS-03", name, "BLOCKING", "NOT_EXECUTED", "-", "0 duplicates",
              f"Not executed: {why}")
        return
    sql_l2, sql_accounts = con.execute(f"""
        SELECT count(DISTINCT fs_caption_l2), count(*) FROM {src}""").fetchone()
    dup = dax.scalar("COUNTROWS ( SUMMARIZE ( 'Account', 'Account'[fs_caption_l1], "
                     "'Account'[fs_caption_l2] ) ) - DISTINCTCOUNT ( 'Account'[fs_caption_l2] )")
    accounts = dax.scalar("COUNTROWS ( SUMMARIZE ( 'Account', 'Account'[fs_caption_l1], "
                          "'Account'[fs_caption_l2], 'Account'[account_name] ) )")
    first = dax.query("EVALUATE TOPN ( 1, VALUES ( 'Account'[fs_caption_l2] ), "
                      "CALCULATE ( MIN ( 'Account'[fs_caption_l2_sort] ) ), ASC )")
    first = first[0][0] if first else None
    r.ok("P6B1-HS-03", name, "BLOCKING",
         dup == 0 and accounts == sql_accounts and first == "Cash and cash equivalents",
         dict(duplicates=dup, accounts=accounts, first=first),
         dict(duplicates=0, accounts=sql_accounts, first="Cash and cash equivalents"),
         f"{sql_l2} level-2 captions, {sql_accounts} accounts, the balance sheet first")


# ------------------------------------------------------------------ P6B1-SC
def _scope(r: Result, rep: RK.Report) -> None:
    page = next(p for p in rep.pages if p["name"] == "p09_controls")
    names = {v["name"] for v in page["visuals"]}
    bridge = next((v for v in page["visuals"] if v["name"] == "p09_controls_layer_bridge"), None)
    off = {(i["source"], i["target"]) for i in page["page"].get("visualInteractions", [])
           if i["type"] == "NoFilter"}
    problems = []
    for slicer in ("p09_controls_sl_period", "p09_controls_sl_basis"):
        if slicer not in names:
            problems.append(f"{slicer} absent: the bridge cannot follow the headline's scope")
        elif bridge and (slicer, bridge["name"]) in off:
            problems.append(f"{slicer} switched off for the bridge")
    if bridge is None:
        problems.append("no layer bridge on the page")
    else:
        if any(t == "Layer Bridge" or c in ("fiscal_year", "fiscal_year_label")
               for t, c, _ in rep.filters(bridge)):
            problems.append("the bridge pins its own period with a visual filter")
        title = (bridge["visual"].get("visualContainerObjects", {}).get("title", [{}])[0]
                 .get("properties", {}).get("text", {}))
        if title.get("expr", {}).get("Measure", {}).get("Property") != "Consolidation Bridge Title":
            problems.append("the bridge's title is not the governed scope title")
        measures = rep.measures_used(bridge)
        if not {"Layer EBITDA", "Layer Net Income"} <= measures:
            problems.append(f"the bridge binds {sorted(measures)}")
    # the headline the bridge reconciles to, on the Executive Overview, follows the same slicers
    exec_page = next(p for p in rep.pages if p["name"] == "p01_executive")
    exec_off = {(i["source"], i["target"]) for i in exec_page["page"].get("visualInteractions", [])
                if i["type"] == "NoFilter"}
    for slicer in ("p01_executive_sl_period", "p01_executive_sl_basis"):
        if (slicer, "p01_executive_p_ebitda_v") in exec_off:
            problems.append(f"the headline EBITDA ignores {slicer}")
    r.ok("P6B1-SC-01", "The consolidation bridge and the headline it reconciles to are read in "
         "the same period context", "BLOCKING", not problems, problems or 0, 0,
         "same synced period and basis slicers, no interaction switched off, no pinned year, "
         "a title that states the basis and month")


# ------------------------------------------------------------------ P6B1-BR
def _bridge(r: Result, con, live: bool, why: str) -> None:
    spec = next(t for t in C.TABLES if t["name"] == "Layer Bridge")
    src = _published(con, spec)
    diff = con.execute(f"""
        SELECT max(abs(coalesce(m.ebitda_usd, 0) - coalesce(b.ebitda_usd, 0))),
               max(abs(coalesce(m.net_income_usd, 0) - coalesce(b.net_income_usd, 0))),
               max(abs(coalesce(m.entries, 0) - coalesce(b.entries, 0))), count(*)
        FROM mart_consolidation_bridge m
        FULL JOIN (SELECT layer_id, fiscal_year, round(sum(ebitda_usd), 2) AS ebitda_usd,
                          round(sum(net_income_usd), 2) AS net_income_usd,
                          sum(entries) AS entries
                   FROM {src} GROUP BY ALL) b USING (layer_id, fiscal_year)""").fetchone()
    r.ok("P6B1-BR-01", "The month-grain bridge sums to the Phase 5 consolidation bridge for "
         "every layer and fiscal year", "BLOCKING",
         diff[0] <= C.TOL_XAR_USD and diff[1] <= C.TOL_XAR_USD and diff[2] == 0,
         dict(ebitda=float(diff[0]), net_income=float(diff[1]), entries=int(diff[2]),
              rows=diff[3]),
         dict(ebitda=C.TOL_XAR_USD, net_income=C.TOL_XAR_USD, entries=0),
         "the same definitions as rpt_layer_bridge, at month grain; the mart stays frozen")

    cases = [("P6B1-BR-02", "MTD", "EBITDA"), ("P6B1-BR-03", "YTD", "EBITDA"),
             ("P6B1-BR-04", "FY", "EBITDA"), ("P6B1-BR-05", "MTD", "Net Income"),
             ("P6B1-BR-06", "YTD", "Net Income"), ("P6B1-BR-07", "FY", "Net Income")]
    for cid, basis, concept in cases:
        layer_m = "Layer EBITDA" if concept == "EBITDA" else "Layer Net Income"
        headline = "Statutory EBITDA" if concept == "EBITDA" else "Net Income"
        name = f"The statutory layers' {concept} sums to [{headline}] on the {basis} basis"
        if not live:
            r.add(cid, name, "BLOCKING", "NOT_EXECUTED", "-", C.TOL_XAR_USD,
                  f"Not executed: {why}")
            continue
        ctx = (f"'Date'[period_key] = {REPORT_PERIOD}, "
               f"'Period Basis'[basis_code] = \"{basis}\"")
        layers = dax.scalar(f"CALCULATE ( [{layer_m}], {ctx}, {STATUTORY_LAYERS} )") or 0.0
        pinned = f", {STAT}" if headline == "Net Income" else ""
        governed = dax.scalar(f"CALCULATE ( [{headline}], {ctx}, {ACT}{pinned} )") or 0.0
        gap = abs(layers - governed)
        r.ok(cid, name, "BLOCKING", gap <= C.TOL_XAR_USD, f"{gap:,.4f}", C.TOL_XAR_USD,
             f"layers 1+2+3+5 {layers:,.2f} vs [{headline}] {governed:,.2f} at "
             f"{REPORT_PERIOD} {basis}; the bridge and the statement round at different "
             f"grains, hence the cent tolerance")

    name = "The bridge is blank after the reporting close on every basis, like every Actual measure"
    if not live:
        r.add("P6B1-BR-08", name, "BLOCKING", "NOT_EXECUTED", "-", "blank",
              f"Not executed: {why}")
        return
    leaks = []
    for basis in ("MTD", "YTD", "FY"):
        for pk in (REPORT_PERIOD + 1, REPORT_PERIOD + 4):
            v = dax.scalar(f"CALCULATE ( [Layer EBITDA], 'Date'[period_key] = {pk}, "
                           f"'Period Basis'[basis_code] = \"{basis}\" )")
            if v not in (None, 0, 0.0):
                leaks.append(f"{basis}@{pk}={v}")
    r.ok("P6B1-BR-08", name, "BLOCKING", not leaks, leaks or 0, 0,
         f"{REPORT_PERIOD + 1}..{REPORT_PERIOD + 4} on MTD, YTD and FY")


# ------------------------------------------------------------------ the run
def run(con, report_dir: Path | None = None, pages: list | None = None) -> Result:
    r = Result()
    live, why = dax.available()
    if live and not dax.model_loaded():
        live, why = False, "the engine is reachable but the Northstar model is not loaded"
    _hierarchy(r, con, live, why)
    _scope(r, RK.Report(report_dir, pages))
    _bridge(r, con, live, why)
    return r


def write(res: Result, path: Path = RESULTS) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys()))
        w.writeheader()
        w.writerows(res)


def report(res: Result) -> None:
    for row in res:
        if row["status"] != "PASS":
            print(f"  {row['status']:12} {row['control_id']:12} {row['control_name']}")
            print(f"      measured {row['measured']} vs {row['threshold']} -- {row['detail']}")
    print(f"{sum(r['status'] == 'PASS' for r in res)}/{len(res)} Phase 6B.1 controls passed, "
          f"{len(res.not_executed)} not executed, {len(res.failed)} blocking failures")


def main(argv: list[str]) -> int:
    con = duckdb.connect(str(C.DUCKDB_PATH), read_only=True)
    res = run(con)
    con.close()
    if "--no-write" not in argv:
        write(res)
    report(res)
    return 1 if res.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
