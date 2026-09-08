"""
Workbook quality assurance, in Excel itself.

openpyxl writes formulas; it does not evaluate them. A workbook that opens with `#REF!` in
forty cells looks perfect to the library that produced it, so the only honest check is to open
the file in Excel, force a full calculation, and look at what comes back.

This module does three things:

1. **calculates** the workbook and writes the cached values back, so a reader who opens it
   without recalculating still sees numbers;
2. **inspects** every report sheet for error values, broken references, stray formatting far
   outside the model, missing freeze panes and print areas, and reconciles the reported totals
   against the marts;
3. **renders** each sheet to a PNG so the layout can actually be looked at, rather than
   asserted.

    python -m src.excel.qa            calculate, inspect, render
    python -m src.excel.qa --inspect  inspect only
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import duckdb

from ..marts.config import DATA, DUCKDB_PATH
from .build import WORKBOOK

RENDER_DIR = DATA / "90_exports" / "workbook_render"
QA_RESULTS = DATA / "phase05_workbook_qa.csv"

ERRORS = ("#REF!", "#VALUE!", "#N/A", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!", "#SPILL!",
          "#CALC!")

#: Layout expectations every report sheet must meet. They are cheap to state and were all
#: violated at least once while this workbook was being built.
MAX_USED_ROW = 220
MAX_USED_COL = 40


def _excel():
    import win32com.client as win32
    try:
        app = win32.gencache.EnsureDispatch("Excel.Application")
    except Exception:
        app = win32.Dispatch("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    app.ScreenUpdating = False
    return app


def calculate_and_inspect(render: bool = True) -> list[dict]:
    """Open, calculate, inspect and render. Returns one row per finding."""
    import pythoncom
    pythoncom.CoInitialize()
    app = _excel()
    findings: list[dict] = []

    def add(sheet, kind, detail, severity="BLOCKING"):
        findings.append(dict(sheet=sheet, check=kind, severity=severity, detail=detail))

    wb = app.Workbooks.Open(str(WORKBOOK.resolve()))
    try:
        app.CalculateFullRebuild()
        app.CalculateUntilAsyncQueriesDone()

        if render:
            RENDER_DIR.mkdir(parents=True, exist_ok=True)
            for f in RENDER_DIR.glob("*.pdf"):
                f.unlink()

        for sheet in wb.Worksheets:
            name = sheet.Name
            if name.startswith("_"):
                continue

            used = sheet.UsedRange
            last_row, last_col = used.Row + used.Rows.Count - 1, used.Column + used.Columns.Count - 1

            # ---- error values anywhere on a report sheet
            bad = []
            for cell in used.SpecialCells(-4123) if _has(used, -4123) else []:
                text = str(cell.Text)
                if any(e in text for e in ERRORS):
                    bad.append(f"{cell.Address(False, False)}={text}")
            for cell in used.SpecialCells(2) if _has(used, 2) else []:
                text = str(cell.Text)
                if any(e in text for e in ERRORS):
                    bad.append(f"{cell.Address(False, False)}={text}")
            if bad:
                add(name, "error values", "; ".join(bad[:8]))

            # ---- layout
            if last_row > MAX_USED_ROW:
                add(name, "used range too tall",
                    f"last used row {last_row} exceeds {MAX_USED_ROW}", "WARNING")
            if last_col > MAX_USED_COL:
                add(name, "used range too wide",
                    f"last used column {last_col} exceeds {MAX_USED_COL}")
            if not sheet.PageSetup.PrintArea:
                add(name, "no print area", "a sheet without a print area prints unpredictably",
                    "WARNING")
            if name not in ("00 Cover", "15 Data & Technical") and not _frozen(sheet):
                add(name, "no freeze panes", "labels scroll away from their data", "WARNING")
            for shape in sheet.Shapes:
                if shape.Left < 0 or shape.Top < 0:
                    add(name, "object off sheet", f"{shape.Name} at ({shape.Left},{shape.Top})")
                right_col = sheet.Range(f"{_col(MAX_USED_COL)}1").Left
                if shape.Left + shape.Width > right_col:
                    add(name, "object beyond the model",
                        f"{shape.Name} extends past column {MAX_USED_COL}", "WARNING")

            # ---- render
            if render:
                _render(app, sheet, RENDER_DIR / f"{name.replace(' ', '_')}.pdf",
                        last_row, last_col)

        wb.Save()
    finally:
        wb.Close(SaveChanges=False)
        app.Quit()
        pythoncom.CoUninitialize()
    return findings


def _has(rng, kind) -> bool:
    try:
        rng.SpecialCells(kind)
        return True
    except Exception:
        return False


def _frozen(sheet) -> bool:
    try:
        sheet.Activate()
        return bool(sheet.Parent.Windows(1).FreezePanes)
    except Exception:
        return False


def _col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _render(app, sheet, path: Path, last_row: int, last_col: int):
    """
    A picture of the sheet as Excel actually draws it.

    Exported through Excel's own PDF writer rather than by copying a picture to the clipboard.
    The clipboard route -- `CopyPicture` into a temporary chart, then `Chart.Export` -- is the
    one every example on the internet uses, and it silently produced sixteen blank white
    images here: the paste had not resolved by the time the export ran, and nothing raised.
    A blank render that reports success is worse than no render at all, because the visual
    review then passes on an empty page.

    The PDF is what Excel would put on paper, at the sheet's own print settings, which is also
    the artefact a reader would circulate.
    """
    try:
        sheet.ExportAsFixedFormat(0, str(path.resolve()))     # 0 = xlTypePDF
    except Exception as exc:                                  # rendering must never fail a build
        print(f"  render failed for {sheet.Name}: {exc}")


def reconcile(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """
    The workbook's headline figures against the marts they came from.

    Read from the saved, calculated workbook with openpyxl in data-only mode, which returns
    the values Excel cached rather than the formulas — so this compares what a reader will
    actually see with what the governed layer says.
    """
    from openpyxl import load_workbook
    from .data import REPORT_FY, REPORT_PERIOD, ACT_VERSION

    wb = load_workbook(WORKBOOK, data_only=True)
    out: list[dict] = []

    def mart(measure):
        row = con.execute(f"""
            SELECT sum(ytd_usd) / 1e6 FROM mart_financial_ytd
            WHERE measure_code = '{measure}' AND basis = 'STATUTORY'
              AND version_code = '{ACT_VERSION}' AND period_key = {REPORT_PERIOD}""").fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0

    ws = wb["02 P&L"]
    measures = [r[0] for r in con.execute(
        "SELECT measure_code FROM dim_report_measure ORDER BY sort_order").fetchall()]
    # the year-to-date block starts after the monthly block; find it by its column heading
    ytd_header = next(r for r in range(1, ws.max_row + 1)
                      if ws.cell(row=r, column=3).value == "Actual")
    for i, measure in enumerate(measures):
        cell = ws.cell(row=ytd_header + 1 + i, column=3).value
        expected = mart(measure)
        got = float(cell) if isinstance(cell, (int, float)) else None
        ok = got is not None and abs(got - expected) <= 0.001
        out.append(dict(check=f"P&L year to date · {measure}",
                        workbook=f"{got:,.3f}" if got is not None else "not a number",
                        mart=f"{expected:,.3f}", status="PASS" if ok else "FAIL"))

    ws = wb["05 Balance Sheet"]
    bs_check = next((ws.cell(row=r, column=3).value for r in range(1, ws.max_row + 1)
                     if str(ws.cell(row=r, column=2).value or "").startswith("Check —")), None)
    ok = bs_check is not None and abs(float(bs_check)) <= 0.01
    out.append(dict(check="Balance sheet balances in the workbook",
                    workbook=f"{float(bs_check):,.4f}" if bs_check is not None else "missing",
                    mart="0.0000", status="PASS" if ok else "FAIL"))

    ws = wb["06 Cash Flow"]
    closing = con.execute(f"""SELECT closing_cash_usd / 1e6 FROM mart_cash_flow
                              WHERE period_key = {REPORT_PERIOD}""").fetchone()[0]
    wb_closing = next((ws.cell(row=r, column=11).value for r in range(1, ws.max_row + 1)
                       if ws.cell(row=r, column=2).value == "Closing cash"), None)
    ok = wb_closing is not None and abs(float(wb_closing) - float(closing)) <= 0.001
    out.append(dict(check="Closing cash",
                    workbook=f"{float(wb_closing):,.3f}" if wb_closing is not None else "missing",
                    mart=f"{float(closing):,.3f}", status="PASS" if ok else "FAIL"))

    ws = wb["09 Debt & Covenants"]
    # The covenant grid presents the agreement's real test dates -- the fiscal year ends --
    # and then the reporting month as an indicative column. The last numeric on the row is
    # therefore the reporting month.
    lev = con.execute(f"""SELECT net_leverage FROM mart_covenants
                          WHERE period_key <= {REPORT_PERIOD}
                          ORDER BY period_key DESC LIMIT 1""").fetchone()[0]
    wb_lev = None
    for r in range(1, ws.max_row + 1):
        if ws.cell(row=r, column=2).value == "Net leverage":
            for c in range(3, 12):
                if isinstance(ws.cell(row=r, column=c).value, (int, float)):
                    wb_lev = ws.cell(row=r, column=c).value
    ok = wb_lev is not None and abs(float(wb_lev) - float(lev)) <= 0.001
    out.append(dict(check="Net leverage at the reporting date",
                    workbook=f"{float(wb_lev):,.3f}" if wb_lev is not None else "missing",
                    mart=f"{float(lev):,.3f}", status="PASS" if ok else "FAIL"))
    return out


def main(argv: list[str]) -> int:
    render = "--inspect" not in argv
    print("opening the workbook in Excel and calculating…")
    findings = calculate_and_inspect(render=render)

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    recs = reconcile(con)
    con.close()

    rows = [dict(kind="layout", **f) for f in findings]
    rows += [dict(kind="reconciliation", sheet="", check=r["check"],
                  severity="BLOCKING" if r["status"] == "FAIL" else "INFO",
                  detail=f"workbook {r['workbook']} vs mart {r['mart']} — {r['status']}")
             for r in recs]
    with open(QA_RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["kind", "sheet", "check", "severity", "detail"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    blocking = [r for r in rows if r["severity"] == "BLOCKING"]
    warnings = [r for r in rows if r["severity"] == "WARNING"]
    failed_rec = [r for r in recs if r["status"] == "FAIL"]

    print(f"\nreconciliation: {len(recs) - len(failed_rec)}/{len(recs)} agree with the marts")
    for r in failed_rec:
        print(f"  FAIL {r['check']}: workbook {r['workbook']} vs mart {r['mart']}")
    print(f"layout: {len(blocking)} blocking, {len(warnings)} warnings")
    for r in (blocking + warnings)[:20]:
        print(f"  {r['severity']:8} {r['sheet']:26} {r['check']}: {r['detail'][:90]}")
    if render:
        print(f"rendered {len(list(RENDER_DIR.glob('*.pdf')))} sheet pages to {RENDER_DIR}")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
