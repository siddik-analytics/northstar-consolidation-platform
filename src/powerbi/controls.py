"""
The Phase 6A semantic control suite.

    python -m src.powerbi.controls

Three families, and the split between them is the point.

``P6-SEM``  the model is structurally sound: keys unique, relationships resolving at the
            cardinality declared, no blank members, no ambiguous path, and the presentation
            metadata a reader depends on actually present.
``P6-XAR``  **Power BI reconciles to the marts.** The Power BI side is the real DAX evaluated
            by the real engine; the mart side is recomputed independently in SQL. Neither side
            is derived from the other.
``P6-XLS``  Power BI reconciles to the Excel workbook, through the workbook's own QA evidence.

## Why the DAX has to be real

Phase 4C's rule carries forward: *different artefacts expressing the same financial measure
must reconcile to one authoritative definition*, and Power BI is another artefact. A control
that re-implemented each measure in SQL and compared the two would be comparing two things
written by the same hand on the same afternoon -- it would agree, and it would prove nothing.

So `P6-XAR` executes the model's own measures against Analysis Services and compares the
result with SQL over the governed marts. That is what caught the two defects the WIP carried:
a relationship on a column that does not exist, and every statement measure summing both
reporting bases and reporting exactly twice the truth. Neither is visible in TMDL text.

When the engine is unavailable the DAX families report `NOT_EXECUTED` and say why. They never
fall back to a SQL re-implementation and call the answer a Power BI value.
"""

from __future__ import annotations

import csv
import sys

import duckdb

from . import config as C
from . import dax
from . import desktop
from .measures import MEASURES

#: Whether `P6-PBIP-03` should open the generated project in Power BI Desktop. Off by default
#: because the fault suite runs the controls a dozen times and a Desktop open is a ten-second
#: UI round trip; `run.py` turns it on for the phase run, and the PBIP fixtures turn it on
#: for themselves.
DESKTOP_OPEN = False

REPORT_PERIOD = C.REPORT_PERIOD
ACT = "'Scenario'[version_code] = \"ACTUAL\""
STAT = "'Reporting Basis'[basis] = \"STATUTORY\""
MGMT = "'Reporting Basis'[basis] = \"MANAGEMENT\""


class Result(list):
    def add(self, cid, name, severity, status, measured="", threshold="", detail=""):
        self.append(dict(control_id=cid, control_name=name, severity=severity, status=status,
                         measured=str(measured), threshold=str(threshold), detail=detail))

    def ok(self, cid, name, severity, condition, measured, threshold, detail=""):
        self.add(cid, name, severity, "PASS" if condition else "FAIL", measured, threshold,
                 detail)

    @property
    def failed(self):
        return [r for r in self if r["status"] == "FAIL" and r["severity"] == "BLOCKING"]

    @property
    def not_executed(self):
        return [r for r in self if r["status"] == "NOT_EXECUTED"]


def _one(con, sql):
    row = con.execute(sql).fetchone()
    return row[0] if row and row[0] is not None else 0


# ============================================================== P6-XAR: the reconciliations
#: (control, measure, dax filter, description, sql over the governed marts)
#:
#: Every SQL below is written against the marts or the consolidated fact -- never against a
#: transcription of the DAX. Where a figure exists upstream of the mart it is taken from there,
#: so the chain being proved is Power BI -> mart -> ledger and not Power BI -> Power BI.
XAR: tuple[tuple[str, str, str, str, str], ...] = (
    ("P6-XAR-01", "Revenue", f"{ACT}, {STAT}", "Revenue, year to date", """
        SELECT round(sum(ytd_usd), 2) FROM mart_financial_ytd
        WHERE version_code = 'ACTUAL' AND basis = 'STATUTORY'
          AND measure_code = 'REVENUE' AND period_key = {p}"""),

    ("P6-XAR-02", "Gross Profit", f"{ACT}, {STAT}", "Gross profit, year to date", """
        SELECT round(sum(ytd_usd), 2) FROM mart_financial_ytd
        WHERE version_code = 'ACTUAL' AND basis = 'STATUTORY'
          AND measure_code = 'GROSS_PROFIT' AND period_key = {p}"""),

    ("P6-XAR-03", "Statutory EBITDA", ACT, "Statutory EBITDA, pinned to the statutory basis",
     """SELECT round(sum(ytd_usd), 2) FROM mart_financial_ytd
        WHERE version_code = 'ACTUAL' AND basis = 'STATUTORY'
          AND measure_code = 'EBITDA' AND period_key = {p}"""),

    ("P6-XAR-04", "Management Adjusted EBITDA", ACT,
     "Adjusted EBITDA, pinned to the management basis", """
        SELECT round(sum(ytd_usd), 2) FROM mart_financial_ytd
        WHERE version_code = 'ACTUAL' AND basis = 'MANAGEMENT'
          AND measure_code = 'ADJ_EBITDA' AND period_key = {p}"""),

    ("P6-XAR-05", "EBIT", f"{ACT}, {STAT}", "EBIT, year to date", """
        SELECT round(sum(ytd_usd), 2) FROM mart_financial_ytd
        WHERE version_code = 'ACTUAL' AND basis = 'STATUTORY'
          AND measure_code = 'EBIT' AND period_key = {p}"""),

    ("P6-XAR-06", "Net Income", f"{ACT}, {STAT}", "Net income, year to date", """
        SELECT round(sum(ytd_usd), 2) FROM mart_financial_ytd
        WHERE version_code = 'ACTUAL' AND basis = 'STATUTORY'
          AND measure_code = 'NET_INCOME' AND period_key = {p}"""),

    ("P6-XAR-07", "Cash", "", "Cash, from the balance sheet caption", """
        SELECT round(sum(balance_usd), 2) FROM mart_balance_sheet
        WHERE caption = 'Cash and cash equivalents' AND period_key = {p}"""),

    ("P6-XAR-08", "Total Assets", "", "Total assets", """
        SELECT round(sum(balance_usd), 2) FROM mart_balance_sheet
        WHERE account_class = 'ASSET' AND period_key = {p}"""),

    ("P6-XAR-09", "Total Equity", "", "Total equity", """
        SELECT round(-sum(balance_usd), 2) FROM mart_balance_sheet
        WHERE account_class = 'EQUITY' AND period_key = {p}"""),

    ("P6-XAR-10", "Operating Cash Flow", "", "Operating cash flow for the month", """
        SELECT round(operating_cash_flow_usd, 2) FROM mart_cash_flow
        WHERE period_key = {p}"""),

    ("P6-XAR-11", "Closing Cash", "", "Closing cash on the cash flow statement", """
        SELECT round(closing_cash_usd, 2) FROM mart_cash_flow WHERE period_key = {p}"""),

    ("P6-XAR-12", "Gross Debt", "", "Gross debt", """
        SELECT round(gross_debt_usd, 2) FROM mart_covenants WHERE period_key = {p}"""),

    ("P6-XAR-13", "Covenant Net Debt", "", "Covenant net debt", """
        SELECT round(net_debt_usd, 2) FROM mart_covenants WHERE period_key = {p}"""),

    ("P6-XAR-14", "Covenant EBITDA", "", "Covenant EBITDA on the rolling twelve months", """
        SELECT round(covenant_ebitda_usd, 2) FROM mart_covenants WHERE period_key = {p}"""),

    ("P6-XAR-15", "Covenant Net Leverage", "", "Covenant net leverage", """
        SELECT round(net_leverage, 6) FROM mart_covenants WHERE period_key = {p}"""),

    ("P6-XAR-16", "Closing FTE", "", "Closing full-time equivalents", """
        SELECT round(sum(fte_closing), 4) FROM mart_headcount WHERE period_key = {p}"""),

    ("P6-XAR-17", "Actual CapEx", "", "Capital spend in the month", """
        SELECT round(sum(spend_usd), 2) FROM mart_capex WHERE period_key = {p}"""),

    ("P6-XAR-18", "Capital Projects", "", "How many capital projects -- the corrected key", """
        SELECT count(DISTINCT project_id) FROM mart_capex WHERE period_key = {p}"""),
)

#: Reconciliations that go one step further upstream than the mart, to the consolidated fact
#: itself. A mart agreeing with Power BI proves the model reads the mart; this proves the mart
#: it reads still agrees with the ledger.
XAR_LEDGER: tuple[tuple[str, str, str, str, str], ...] = (
    ("P6-XAR-19", "Revenue", f"{ACT}, {STAT}",
     "Revenue recomputed from the consolidated fact, not the mart", """
        SELECT round(-sum(f.amount_usd), 2)
        FROM vw_statutory_fact f JOIN dim_account a USING (group_account)
        WHERE a.fs_caption_l1 = 'Revenue' AND f.counts_in_result
          AND NOT a.is_statistical
          AND f.group_account NOT IN (SELECT group_account FROM ref_ic_side)
          AND f.fiscal_year = {fy} AND f.period_key <= {p}"""),
)

#: Power BI against the Excel workbook, through the workbook's own committed QA evidence.
#: The workbook side is a value read out of the rendered workbook by `src/excel/qa.py`, so
#: neither side of this comparison is a fresh calculation made to satisfy the control.
XLS: tuple[tuple[str, str, str, str], ...] = (
    ("P6-XLS-01", "Revenue", "P&L year to date · REVENUE", f"{ACT}, {STAT}"),
    ("P6-XLS-02", "Gross Profit", "P&L year to date · GROSS_PROFIT", f"{ACT}, {STAT}"),
    ("P6-XLS-03", "Statutory EBITDA", "P&L year to date · EBITDA", ACT),
    ("P6-XLS-04", "Management Adjusted EBITDA", "P&L year to date · ADJ_EBITDA", ACT),
    ("P6-XLS-05", "EBIT", "P&L year to date · EBIT", f"{ACT}, {STAT}"),
    ("P6-XLS-06", "Net Income", "P&L year to date · NET_INCOME", f"{ACT}, {STAT}"),
    ("P6-XLS-07", "Closing Cash", "Closing cash", ""),
    ("P6-XLS-08", "Covenant Net Leverage", "Net leverage at the reporting date", ""),
)


def _excel_values() -> dict[str, float]:
    """The workbook figures, read from the Phase 5 QA evidence rather than recomputed."""
    path = C.DATA / "phase05_workbook_qa.csv"
    out: dict[str, float] = {}
    if not path.exists():
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["kind"] != "reconciliation":
                continue
            detail = row["detail"]
            if not detail.startswith("workbook "):
                continue
            try:
                out[row["check"]] = float(detail.split()[1])
            except (IndexError, ValueError):
                continue
    return out


def _reconcile(r: Result, con, live: bool, why: str) -> None:
    fy = REPORT_PERIOD // 100
    for cid, measure, filters, description, sql in XAR + XAR_LEDGER:
        expected = con.execute(sql.format(p=REPORT_PERIOD, fy=fy)).fetchone()[0]
        expected = float(expected) if expected is not None else 0.0
        if not live:
            r.add(cid, f"Power BI [{measure}] reconciles to the marts", "BLOCKING",
                  "NOT_EXECUTED", "-", f"{expected:,.2f}",
                  f"{description}. Not executed: {why}")
            continue
        actual = dax.measure_at(measure, REPORT_PERIOD, filters)
        actual = float(actual) if actual is not None else 0.0
        tol = C.TOL_RATIO if "Leverage" in measure else C.TOL_XAR_USD
        diff = abs(actual - expected)
        r.ok(cid, f"Power BI [{measure}] reconciles to the marts", "BLOCKING",
             diff <= tol, f"{diff:,.6f}", f"{tol}",
             f"{description}: DAX {actual:,.2f} vs mart {expected:,.2f}")

    excel = _excel_values()
    for cid, measure, key, filters in XLS:
        if key not in excel:
            r.add(cid, f"Power BI [{measure}] reconciles to the workbook", "BLOCKING",
                  "NOT_EXECUTED", "-", "-",
                  f"the workbook QA evidence has no row '{key}'")
            continue
        expected = excel[key]
        if not live:
            r.add(cid, f"Power BI [{measure}] reconciles to the workbook", "BLOCKING",
                  "NOT_EXECUTED", "-", f"{expected}", f"Not executed: {why}")
            continue
        actual = dax.measure_at(measure, REPORT_PERIOD, filters)
        actual = float(actual) if actual is not None else 0.0
        scaled = actual if "Leverage" in measure else actual / 1e6
        tol = 0.0006 if "Leverage" in measure else 0.0006
        diff = abs(scaled - expected)
        r.ok(cid, f"Power BI [{measure}] reconciles to the workbook", "BLOCKING",
             diff <= tol, f"{diff:.6f}", f"{tol}",
             f"workbook {expected} vs Power BI {scaled:,.3f} "
             f"(the workbook publishes millions to three decimals)")


# ============================================================== P6-SEM: structural integrity
def _semantic(r: Result, con, live: bool, why: str) -> None:
    # ---------------------------------------------------------- keys and cardinality
    dupes, orphans = [], []
    for spec in C.TABLES:
        key = ", ".join(spec["key"])
        rows, distinct = con.execute(f"""
            SELECT count(*), (SELECT count(*) FROM
                (SELECT DISTINCT {key} FROM {spec['source']}))
            FROM {spec['source']}""").fetchone()
        if rows != distinct and spec["kind"] == "dimension":
            dupes.append(f"{spec['name']} ({rows - distinct})")
    r.ok("P6-SEM-01", "Every dimension key is unique over its published population",
         "BLOCKING", not dupes, "; ".join(dupes) or 0, 0,
         "a dimension with a duplicate key silently fans out every fact that joins to it")

    by_name = {t["name"]: t for t in C.TABLES}
    for from_table, from_col, to_table, to_col in C.RELATIONSHIPS:
        child, parent = by_name[from_table], by_name[to_table]
        # A calculated column lives only in the model, so the control evaluates the declared
        # SQL equivalent rather than skipping the relationship built on it.
        expr = child.get("calculated_sql", {}).get(from_col, f"c.{from_col}")
        n = _one(con, f"""
            SELECT count(*) FROM {child['source']} c
            WHERE ({expr}) IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM {parent['source']} p WHERE p.{to_col} = ({expr}))""")
        if n:
            orphans.append(f"{from_table}[{from_col}] -> {to_table} ({n})")
    r.ok("P6-SEM-02", "Every relationship resolves: no orphan key, so no blank member",
         "BLOCKING", not orphans, "; ".join(orphans) or 0, 0,
         "an unresolved key becomes a blank member in every visual that uses the dimension")

    # The many side must actually be many-to-one: the parent column has to be unique.
    bad_cardinality = []
    for from_table, from_col, to_table, to_col in C.RELATIONSHIPS:
        parent = by_name[to_table]
        rows, distinct = con.execute(f"""
            SELECT count(*), (SELECT count(*) FROM
                (SELECT DISTINCT {to_col} FROM {parent['source']}))
            FROM {parent['source']}""").fetchone()
        if rows != distinct:
            bad_cardinality.append(f"{to_table}[{to_col}]")
    r.ok("P6-SEM-03", "Every declared many-to-one relationship is many-to-one in the data",
         "BLOCKING", not bad_cardinality, "; ".join(bad_cardinality) or 0, 0,
         "declaring a cardinality does not make the data have it; Power BI silently promotes "
         "a broken one to many-to-many and the totals stop meaning anything")

    # ---------------------------------------------------------- one path between any two tables
    paths: dict[tuple[str, str], int] = {}
    for from_table, from_col, to_table, to_col in C.RELATIONSHIPS:
        paths[(from_table, to_table)] = paths.get((from_table, to_table), 0) + 1
    ambiguous = [f"{a} -> {b}" for (a, b), n in paths.items() if n > 1]
    r.ok("P6-SEM-04", "No two tables are joined by more than one active path", "BLOCKING",
         not ambiguous, "; ".join(ambiguous) or 0, 0,
         "the reason every business-unit path is inactive: a fact reaches Business Unit "
         "through Entity, and a second direct route would make every segment total ambiguous")

    r.ok("P6-SEM-05", "Every inactive relationship carries a written reason", "BLOCKING",
         all(len(why_.strip()) > 30 for *_, why_ in C.INACTIVE_RELATIONSHIPS),
         len(C.INACTIVE_RELATIONSHIPS), len(C.INACTIVE_RELATIONSHIPS),
         "an inactive relationship is a decision; an undocumented one is a mistake nobody "
         "can tell apart from a decision")

    # ---------------------------------------------------------- presentation metadata
    missing_desc = [t["name"] for t in C.TABLES if len(t["description"].strip()) < 40]
    r.ok("P6-SEM-06", "Every table carries a description a reader can use", "BLOCKING",
         not missing_desc, "; ".join(missing_desc) or 0, 0)

    no_desc = [n for n, e, f, fo, d in MEASURES if len(d.strip()) < 30]
    r.ok("P6-SEM-07", "Every measure carries a description", "BLOCKING",
         not no_desc, "; ".join(no_desc) or 0, 0,
         "a measure whose meaning lives only in its name is a measure two people will read "
         "two ways")

    HIGH_RISK = ("Management Adjusted EBITDA", "Covenant EBITDA", "Covenant Net Debt",
                 "Covenant Net Leverage", "Cumulative Translation Adjustment",
                 "Non-controlling Interest Equity", "Closing Cash")
    thin = [n for n, e, f, fo, d in MEASURES
            if n in HIGH_RISK and not all(k in d for k in ("Definition", "Source", "Basis"))]
    r.ok("P6-SEM-08", "Every high-risk measure states its definition, source and basis",
         "BLOCKING", not thin, "; ".join(thin) or 0, 0,
         "the measures a reader is most likely to be challenged on are the ones that must "
         "answer for themselves")

    no_folder = [n for n, e, f, fo, d in MEASURES if not fo.strip()]
    r.ok("P6-SEM-09", "Every measure sits in a display folder", "BLOCKING",
         not no_folder, "; ".join(no_folder) or 0, 0)

    money_without_format = [
        n for n, e, f, fo, d in MEASURES
        if f is None and not any(w in n for w in ("Status", "Version", "Period", "Basis",
                                                 "Favourability", "Comparable", "Is "))]
    r.ok("P6-SEM-10", "Every numeric measure carries a format string", "BLOCKING",
         not money_without_format, "; ".join(money_without_format) or 0, 0,
         "an unformatted measure renders at full precision and makes a report look unfinished")

    # ---------------------------------------------------------- sort order, not alphabet
    sorted_cols = sum(len(t.get("sort", {})) for t in C.TABLES)
    r.ok("P6-SEM-11", "Statement captions sort by their governed order, not alphabetically",
         "BLOCKING",
         "measure_name" in by_name["Measure Line"].get("sort", {})
         and "caption" in by_name["Balance Sheet"].get("sort", {}),
         sorted_cols, ">= 2",
         "a P&L in alphabetical order starts at Cost of sales, and a balance sheet in "
         "alphabetical order is not a balance sheet")

    # ---------------------------------------------------------- keys are hidden
    exposed = [f"{t['name']}.{k}" for t in C.TABLES if t["kind"] == "fact"
               for k in t["key"]
               if k not in t["hide"] and k not in t.get("visible_key", ())]
    r.ok("P6-SEM-12", "No fact key column is left visible to a report author", "BLOCKING",
         not exposed, "; ".join(exposed) or 0, 0,
         "a visible key invites someone to drag it onto a visual and summarise it")

    # ---------------------------------------------------------- the live model
    if not live:
        r.add("P6-SEM-13", "The model loads in Analysis Services", "BLOCKING",
              "NOT_EXECUTED", "-", "-", why)
        r.add("P6-SEM-14", "Every measure parses and evaluates", "BLOCKING",
              "NOT_EXECUTED", "-", "-", why)
        return

    live_tables = set(dax.table_names())
    declared = {t["name"] for t in C.TABLES} | {"Period Basis", C.MEASURES_TABLE}
    r.ok("P6-SEM-13", "The model loads in Analysis Services with every declared table",
         "BLOCKING", declared <= live_tables,
         len(live_tables), len(declared),
         f"missing: {sorted(declared - live_tables)}" if declared - live_tables
         else "deployed and refreshed from the same declarations the TMDL is written from")

    broken = []
    for name, expression, fmt, folder, description in MEASURES:
        try:
            dax.measure_at(name, REPORT_PERIOD)
        except Exception as exc:
            broken.append(f"{name} ({exc.__class__.__name__})")
    r.ok("P6-SEM-14", "Every measure parses and evaluates in the engine", "BLOCKING",
         not broken, "; ".join(broken[:5]) or 0, 0,
         f"{len(MEASURES)} measures evaluated against the live model")


# ============================================================== policy controls
def _policy(r: Result, con, live: bool, why: str) -> None:
    if not live:
        for cid, name in (("P6-POL-01", "Actual is blank after the reporting close"),
                          ("P6-POL-02", "The three EBITDA definitions are distinct"),
                          ("P6-POL-03", "Covenant status is Indicative off a test date"),
                          ("P6-POL-04", "Prior Year resolves to the governed version"),
                          ("P6-POL-05", "No fact row falls to a blank Scenario member"),
                          ("P6-POL-06", "Statutory and management pin their basis"),
                          ("P6-POL-07", "The current forecast is the governed default")):
            r.add(cid, name, "BLOCKING", "NOT_EXECUTED", "-", "-", why)
        return

    # ---- the actual cutoff, tested where it actually bites
    after = dax.measure_at("Revenue", 202609, ACT)
    at = dax.measure_at("Revenue", REPORT_PERIOD, ACT)
    r.ok("P6-POL-01", "Actual is BLANK after the reporting close, never zero", "BLOCKING",
         after is None and at is not None, f"Sep-26 = {after!r}", "BLANK",
         "the mart publishes ACTUAL rows for the whole fiscal year carrying 0.00; without the "
         "guard September reads as a month the group earned nothing")

    # ---- three EBITDA definitions, distinct by construction
    stat = dax.measure_at("Statutory EBITDA", REPORT_PERIOD, ACT)
    adj = dax.measure_at("Management Adjusted EBITDA", REPORT_PERIOD, ACT)
    cov = dax.measure_at("Covenant EBITDA", REPORT_PERIOD, ACT)
    distinct_sources = len({
        m[1].split("\n")[0] for m in MEASURES
        if m[0] in ("Statutory EBITDA", "Management Adjusted EBITDA", "Covenant EBITDA")})
    r.ok("P6-POL-02", "Statutory, Adjusted and Covenant EBITDA are three separate definitions",
         "BLOCKING",
         stat != adj and adj != cov and stat != cov,
         f"{stat:,.0f} / {adj:,.0f} / {cov:,.0f}", "three different values",
         "Covenant EBITDA reads the covenant bridge on a rolling twelve months, not an alias "
         "of Adjusted EBITDA. Even where two happened to agree they would still be separate "
         "measures with separate lineage")

    # ---- covenant test dates
    off_date = dax.scalar('CALCULATE ( [Covenant Status], \'Date\'[period_key] = 202608 )')
    on_date = dax.scalar('CALCULATE ( [Covenant Status], \'Date\'[period_key] = 202512 )')
    r.ok("P6-POL-03", "A month the agreement does not test is labelled Indicative",
         "BLOCKING", off_date == "Indicative" and on_date in ("Compliant", "Breach"),
         f"Aug-26 = {off_date!r}, Dec-25 = {on_date!r}",
         "Indicative / a real status",
         "the credit agreement tests at fiscal year ends (CA-009..012). Stamping BREACH on a "
         "date nobody tests is the Phase 5 defect, and it must not come back in DAX")

    # ---- prior year resolves
    py_version = dax.scalar("[Prior Year Version]")
    py_value = dax.measure_at("Prior Year Revenue", REPORT_PERIOD)
    r.ok("P6-POL-04", "Prior Year resolves to the governed derived version", "BLOCKING",
         py_version == "PY_DERIVED" and py_value is not None,
         f"{py_version!r}, revenue {py_value}", "PY_DERIVED with a value",
         "P7-D-01 seen from the semantic layer: a version code that resolves to nothing "
         "becomes a blank member here")

    blank_members = _one(con, """
        SELECT count(*) FROM mart_financial_ytd m
        WHERE NOT EXISTS (SELECT 1 FROM dim_report_scenario d
                          WHERE d.version_code = m.version_code)""")
    r.ok("P6-POL-05", "No fact row falls to a blank Scenario member", "BLOCKING",
         blank_members == 0, blank_members, 0,
         "measured on the published data the model loads, so it is the model's own exposure")

    # ---- statutory and management read the basis they are named for
    #
    # This one has to be checked on the DEFINITION, not on the values, and the reason is worth
    # recording: in this baseline layer 4 posts no legs at all and both approved management
    # adjustments carry 0.00, so the two bases hold identical figures everywhere. A measure
    # secretly reading the wrong basis would therefore agree with every number in the platform.
    # The separation is real architecture -- Phase 4's F4-MGT-LEAK fixture proves it by
    # injecting a real adjustment -- but it cannot be proved from these values, so the control
    # reads the deployed DAX out of the engine and checks what it actually filters.
    definitions = {}
    try:
        for name, expression in dax.query(
                'EVALUATE SELECTCOLUMNS ( INFO.MEASURES (), "n", [Name], "e", [Expression] )'):
            definitions[name] = expression
    except Exception:
        definitions = {}
    expected_basis = {"Statutory EBITDA": "STATUTORY",
                      "Management Adjusted EBITDA": "MANAGEMENT",
                      "Approved Add-backs": "MANAGEMENT"}
    wrong = [f"{n} does not pin {b}" for n, b in expected_basis.items()
             if f'"{b}"' not in definitions.get(n, "")]
    r.ok("P6-POL-06", "Statutory and management measures pin the basis they are named for",
         "BLOCKING", bool(definitions) and not wrong, "; ".join(wrong) or 0, 0,
         "read from the deployed model rather than from the source that generated it. Checked "
         "on the definition because in this baseline layer 4 is unpopulated and the two bases "
         "hold identical values, so a measure reading the wrong one would agree with "
         "everything")

    # ---- the current forecast is the governed default, not a name someone typed
    governed = con.execute("""
        SELECT version_code FROM ref_default_version WHERE scenario_code = 'FC'""").fetchone()
    governed = governed[0] if governed else None
    reported = dax.scalar("[Current Forecast Version]")
    r.ok("P6-POL-07", "The current forecast version is the one the master marks as default",
         "BLOCKING", reported == governed, f"model {reported!r}", f"governed {governed!r}",
         "three forecasts are retained and only one is current; a superseded forecast "
         "presented as the forecast is an error nobody would notice from the number alone")




# ---------------------------------------------------------------------------- P6-PBIP
#: TMDL objects that carry a Description in the tabular object model, and so may take a `///`
#: doc comment. A `///` above anything else is a property the parser does not know, and
#: Desktop rejects the whole project for it (P6B-D-01: relationships).
DOCUMENTABLE = frozenset({
    "model", "table", "column", "measure", "hierarchy", "level", "partition", "expression",
    "role", "perspective", "calculationGroup", "calculationItem", "dataSource",
})


def _tmdl_files() -> list:
    definition = C.MODEL_DIR / "definition"
    return sorted(definition.rglob("*.tmdl")) if definition.exists() else []


def _doc_comment_targets() -> list[tuple[str, int, str]]:
    """Every `///` block in the generated project and the object keyword that follows it."""
    out = []
    for path in _tmdl_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            if lines[i].strip().startswith("///"):
                start = i
                while i < len(lines) and lines[i].strip().startswith("///"):
                    i += 1
                keyword = lines[i].strip().split(" ")[0] if i < len(lines) else "EOF"
                out.append((path.name, start + 1, keyword))
            else:
                i += 1
    return out


def _declared_tables() -> list[str]:
    """Table names as the generated TMDL declares them (`table X` / `table 'X Y'`)."""
    names = []
    for path in _tmdl_files():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("table "):
                names.append(line[6:].strip().strip("'"))
    return names


def _project_counts() -> dict:
    """Object counts read from the generated TMDL text -- the native project's own claim."""
    measures = relationships = active = 0
    for path in _tmdl_files():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("\tmeasure "):
                measures += 1
            elif line.startswith("relationship "):
                relationships += 1
                active += 1
            elif line.strip() == "isActive: false":
                active -= 1
    return dict(tables=len(_declared_tables()), measures=measures,
                relationships=relationships, active_relationships=active)


def _engine_counts() -> dict | None:
    try:
        return dict(
            tables=len(dax.table_names()),
            measures=int(dax.query('EVALUATE ROW ( "n", COUNTROWS ( INFO.MEASURES () ) )')[0][0]),
            relationships=int(dax.query(
                'EVALUATE ROW ( "n", COUNTROWS ( INFO.RELATIONSHIPS () ) )')[0][0]),
            active_relationships=int(dax.query(
                'EVALUATE ROW ( "n", COUNTROWS ( FILTER ( INFO.RELATIONSHIPS (), [IsActive] ) ) )'
            )[0][0]))
    except Exception:
        return None


def _pbip(r: Result, con, live: bool, why: str) -> None:
    """
    Native project compatibility.

    A model can be valid in the engine and invalid as a project on disk: the engine has no
    reserved table names and TMSL carries no doc comments, so the TMSL deployment that
    validates the DAX proves nothing about whether Desktop will open the `.pbip`. Phase 6A
    passed every engine control and the project did not open (P6B-D-01, P6B-D-02). These
    controls read the generated text the way the parser does, and `P6-PBIP-03` hands the
    project to Desktop itself.
    """
    bad = [(f, n, k) for f, n, k in _doc_comment_targets() if k not in DOCUMENTABLE]
    r.ok("P6-PBIP-01", "Doc comments only on objects that carry a Description", "BLOCKING",
         not bad, "; ".join(f"{f}:{n} -> {k}" for f, n, k in bad[:5]) or 0, 0,
         "a `///` above a relationship is a Description property the parser rejects "
         "(P6B-D-01); rationale travels as an annotation instead")

    tables = _declared_tables()
    reserved = [t for t in tables if t.lower() in C.RESERVED_TABLE_NAMES]
    r.ok("P6-PBIP-02", "No table name Power BI Desktop reserves", "BLOCKING",
         not reserved and bool(tables), reserved or 0, 0,
         f"{len(tables)} tables declared; reserved list {sorted(C.RESERVED_TABLE_NAMES)} "
         f"confirmed against Desktop, not assumed (P6B-D-02)")

    native = None
    if not DESKTOP_OPEN:
        r.add("P6-PBIP-03", "Power BI Desktop opens the generated project", "BLOCKING",
              "NOT_EXECUTED", "-", "-",
              "Desktop open not requested for this run (run.py requests it)")
    else:
        pbip = C.PBIP_DIR / f"{C.PROJECT}.pbip"
        result = desktop.open_project(pbip)
        if result["why"] and not result["refusal"] and not result["opened"]:
            r.add("P6-PBIP-03", "Power BI Desktop opens the generated project", "BLOCKING",
                  "NOT_EXECUTED", "-", "-", result["why"])
        else:
            detail = (f"opened in {result['seconds']}s as {result['title']!r}"
                      if result["opened"] else f"refused: {result['refusal'][:300]}")
            loaded = None
            if result["opened"]:
                refreshed = desktop.refresh(result["pid"])
                native = desktop.session_counts(result["pid"])
                loaded = refreshed["done"]
                detail += ("; native refresh loaded every partition" if loaded
                           else f"; native refresh incomplete: {refreshed['why']} "
                                f"{refreshed['dialogs']}")
                desktop.screenshot(C.DATA / "90_exports" / "powerbi_desktop_open.png",
                                   result["pid"])
            r.ok("P6-PBIP-03", "Power BI Desktop opens the generated project and loads it",
                 "BLOCKING", bool(result["opened"] and loaded),
                 "opened" if result["opened"] else "refused", "opened", detail)
            spawned = result["pid"] and result["pid"] != (desktop._pids() or [None])[0]
            if spawned:
                desktop.close_instance(result["pid"])

    project = _project_counts()
    engine = _engine_counts() if live else None
    if engine is None:
        r.add("P6-PBIP-04", "Native project and deployed engine agree on structure", "BLOCKING",
              "NOT_EXECUTED", str(project), "-", why)
    else:
        forms = {"project": project, "engine": engine}
        if native:
            forms["desktop"] = {k: (len(v) if isinstance(v, list) else v)
                                for k, v in native.items() if k != "catalog"}
        agree = all(forms[f][k] == project[k] for f in forms for k in project)
        r.ok("P6-PBIP-04", "Native project, deployed engine"
             + (" and Desktop session" if native else "") + " agree on structure",
             "BLOCKING", agree, {k: v for k, v in forms.items() if k != "project"}, project,
             "tables, measures, relationships and active relationships counted in each form")


def run(con: duckdb.DuckDBPyConnection) -> Result:
    r = Result()
    live, why = dax.available()
    if live and not dax.model_loaded():
        live, why = False, ("Analysis Services is reachable but the Northstar model is not "
                            "loaded; run `python -m src.powerbi.run --deploy` first")
    r.add("P6-SEM-00", "The semantic model is available for execution", "INFO",
          "PASS" if live else "NOT_EXECUTED", "live" if live else "not live", "live", why)
    _semantic(r, con, live, why)
    _reconcile(r, con, live, why)
    _policy(r, con, live, why)
    _pbip(r, con, live, why)
    return r


def write(res: Result) -> None:
    C.CONTROL_RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with open(C.CONTROL_RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys()))
        w.writeheader()
        w.writerows(res)


def report(res: Result) -> None:
    for row in res:
        if row["status"] not in ("PASS",):
            print(f"  {row['status']:12} {row['control_id']:12} {row['control_name']}")
            print(f"      measured {row['measured']} vs {row['threshold']} -- {row['detail']}")
    families: dict[str, list[int]] = {}
    for row in res:
        fam = "-".join(row["control_id"].split("-")[:2])
        seen = families.setdefault(fam, [0, 0])
        seen[0] += 1
        seen[1] += row["status"] == "PASS"
    for fam, (total, passed) in sorted(families.items()):
        print(f"  {fam:10} {passed:>3}/{total:<3} passed")
    print(f"{sum(r['status'] == 'PASS' for r in res)}/{len(res)} semantic controls passed, "
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
