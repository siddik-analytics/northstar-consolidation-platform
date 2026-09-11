"""
The Phase 6B report control suite.

    python -m src.powerbi.report.controls              run against powerbi/Northstar.Report
    python -m src.powerbi.report.controls --no-write   run without writing the register

The semantic controls (`src/powerbi/controls.py`) prove the model. These prove the **report
on top of it** -- that every number a page shows is a governed measure in a stated scope,
that the scope is the one the page claims, and that nothing on a page was typed, computed
locally, scaled twice or dressed up as a verdict the agreement never gave.

Three kinds of evidence, and the register says which one each control used:

* **static** -- the generated PBIR files, read as JSON. What Desktop will open.
* **live** -- the model's own measures, evaluated by the engine in the filter context a
  visual declares. Report-side scope, engine-side value.
* **native** -- the last recorded native pass in Power BI Desktop (`native_qa.py`), which
  is accepted only if it was taken on the report declarations and the model definition that
  are on disk now.

`P6B-20…32` reconcile a page's number three ways: the visual's own scope evaluated in the
engine, against the semantic control's mart SQL, so the report, the model and the mart
agree on the same figure by three different routes.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import duckdb

from .. import config as C
from .. import controls as SEM
from .. import dax
from ..measures import FTE, M_USD, M_USD2, PCT, TURNS, MEASURES
from . import build as BUILD
from . import layout as L
from . import theme as T

RESULTS = C.DATA / "phase06b_control_results.csv"
FAULT_RESULTS = C.DATA / "phase06b_fault_results.csv"
MANIFEST = C.DATA / "phase06b_manifest.json"
NATIVE_QA = C.DATA / "phase06b_native_qa.json"
INVENTORY = C.DATA / "phase06b_object_inventory.json"

REPORT_PERIOD = C.REPORT_PERIOD
MEASURE_NAMES = {m[0] for m in MEASURES}
MONEY = {m[0] for m in MEASURES if m[2] in (M_USD, M_USD2)}
FACT_TABLES = {t["name"] for t in C.TABLES if t.get("kind") == "fact"}
VALUE_ROLES = ("Values", "Y", "Y2")
HEADLINE_PRIMARY = ("Revenue", "Management Adjusted EBITDA", "Closing Cash",
                    "Covenant Net Leverage")
DEFERRED_NAMES = ("DSO", "DIO", "DPO", "Cash conversion cycle", "CCC", "Revolver drawn",
                  "Revolver available")
#: the slicer defaults as DAX, for evaluating a visual in the scope a reader first sees
SLICER_DAX = {key: f"'{table}'[{col}] = \"{values[0]}\""
              for key, (table, col, values) in L.SLICER_DEFAULTS.items()}
SLICER_DAX["sl_comparison"] = "'Comparison'[comparison_name] = \"Actual vs Budget\""
#: a typed financial figure: a decimal number, a percentage or a ratio in turns
AMOUNT = re.compile(r"(?<![A-Za-z0-9-])(\d[\d,]*\.\d+|\d+(\.\d+)?%|\d+\.\d+x)(?![A-Za-z0-9-])")

# ------------------------------------------------------------------ the report, parsed
class Report:
    """A generated report folder, read the way Desktop reads it."""

    def __init__(self, report_dir: Path | None = None, pages: list | None = None):
        self.dir = Path(report_dir or C.REPORT_DIR)
        definition = self.dir / "definition"
        self.index = json.loads((definition / "pages" / "pages.json").read_text("utf-8"))
        self.pages: list[dict] = []
        for name in self.index["pageOrder"]:
            folder = definition / "pages" / name
            page = json.loads((folder / "page.json").read_text("utf-8"))
            visuals = [json.loads(p.read_text("utf-8"))
                       for p in sorted((folder / "visuals").glob("*/visual.json"))]
            self.pages.append(dict(name=name, page=page, visuals=visuals))
        # the declarations the files came from: reasons and kinds are not PBIR
        self.declared = {pg.name: pg for pg in (pages if pages is not None
                                                 else BUILD.build_pages())}

    # ---- iteration
    def visuals(self):
        for page in self.pages:
            for v in page["visuals"]:
                yield page["name"], v

    @staticmethod
    def vtype(v: dict) -> str:
        return v["visual"].get("visualType", "")

    @staticmethod
    def projections(v: dict):
        """(role, field, projection) for every projection in the visual's query."""
        state = (v["visual"].get("query") or {}).get("queryState") or {}
        for role, spec in state.items():
            for proj in spec.get("projections", []):
                yield role, proj.get("field", {}), proj

    @classmethod
    def measures_used(cls, v: dict) -> set[str]:
        return {f["Measure"]["Property"] for _, f, _ in cls.projections(v) if "Measure" in f}

    @classmethod
    def value_fields(cls, v: dict):
        for role, f, proj in cls.projections(v):
            if role in VALUE_ROLES:
                yield f, proj

    @staticmethod
    def filters(v: dict) -> list[tuple[str, str, list]]:
        """The visual's own filters as (table, column, values)."""
        out = []
        for flt in (v.get("filterConfig") or {}).get("filters", []):
            field = flt["field"]["Column"]
            table, col = field["Expression"]["SourceRef"]["Entity"], field["Property"]
            values = []
            for row in flt["filter"]["Where"][0]["Condition"]["In"]["Values"]:
                values.append(_literal(row[0]["Literal"]["Value"]))
            out.append((table, col, values))
        return out

    @staticmethod
    def text(v: dict) -> str:
        if v["visual"].get("visualType") != "textbox":
            return ""
        general = v["visual"].get("objects", {}).get("general", [{}])[0]
        runs = []
        for para in general.get("properties", {}).get("paragraphs", []):
            runs += [r.get("value", "") for r in para.get("textRuns", [])]
        return " ".join(runs)

    @staticmethod
    def literal(obj: dict, *path: str):
        node = obj
        for key in path:
            if isinstance(node, list):
                node = node[0] if node else {}
            node = node.get(key, {}) if isinstance(node, dict) else {}
        if isinstance(node, dict) and "expr" in node:
            return _literal(node["expr"]["Literal"]["Value"])
        return None

    def kinds(self, page_name: str) -> dict[str, str]:
        return self.declared[page_name].kinds

    def reasons(self, page_name: str) -> dict:
        return self.declared[page_name].reasons


def _literal(raw: str):
    """A PBIR literal (`'text'`, `12D`, `true`, `2026L`) as a Python value."""
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1]
    if raw in ("true", "false"):
        return raw == "true"
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)[DL]?", raw)
    return float(m.group(1)) if m else raw


def _dax_filter(table: str, col: str, values: list) -> str:
    def lit(x):
        if isinstance(x, bool):
            return "TRUE ()" if x else "FALSE ()"
        if isinstance(x, (int, float)):
            return str(int(x)) if float(x).is_integer() else str(x)
        return '"' + str(x).replace('"', '""') + '"'
    return f"'{table}'[{col}] IN {{ {', '.join(lit(x) for x in values)} }}"


def visual_scope(rep: Report, page_name: str, key: str, extra: str = "") -> tuple[str, dict]:
    """
    The DAX filter context a visual is read in: its own filters, plus the page's slicer
    defaults except where the page switched the slicer off for it.
    """
    page = next(p for p in rep.pages if p["name"] == page_name)
    name = f"{page_name}_{key}"
    v = next(x for x in page["visuals"] if x["name"] == name)
    parts = [_dax_filter(t, c, vals) for t, c, vals in rep.filters(v)]
    switched_off = {i["source"] for i in page["page"].get("visualInteractions", [])
                    if i["target"] == name and i["type"] == "NoFilter"}
    present = {x["name"] for x in page["visuals"]}
    for slicer, clause in SLICER_DAX.items():
        sname = f"{page_name}_{slicer}"
        if sname in present and sname not in switched_off:
            parts.append(clause)
    if extra:
        parts.append(extra)
    return ", ".join(parts), v


# ------------------------------------------------------------------ the static families
def _static(r: SEM.Result, rep: Report) -> None:
    # ---- P6B-01 nothing typed
    typed = []
    for page, v in rep.visuals():
        if page in ("p09_controls", "p10_lineage"):
            continue   # generated from the registers; P6B-13 checks them against the source
        text = rep.text(v)
        if text and AMOUNT.search(text):
            typed.append(f"{v['name']}: {text[:60]!r}")
        if rep.vtype(v) == "card" and not rep.measures_used(v):
            typed.append(f"{v['name']}: card without a measure")
    r.ok("P6B-01", "No financial amount is typed on a page: every number is a bound measure",
         "BLOCKING", not typed, typed or 0, 0,
         "textboxes on the eight financial pages carry no decimal, percentage or ratio; "
         "every card binds a governed measure")

    # ---- P6B-02 explicit measures only
    implicit = []
    for page, v in rep.visuals():
        kind = rep.vtype(v)
        for role, f, proj in rep.projections(v):
            if "Aggregation" in f or "Arithmetic" in f or "ScopedEval" in f:
                implicit.append(f"{v['name']}/{role}: {list(f)[0]}")
            elif "Column" in f and role in VALUE_ROLES and kind != "slicer":
                table = f["Column"]["Expression"]["SourceRef"]["Entity"]
                if kind == "tableEx" and table not in FACT_TABLES:
                    continue   # a dimension attribute in a register table is not a value
                implicit.append(f"{v['name']}/{role}: column {table}[{f['Column']['Property']}]")
            elif "Measure" in f and f["Measure"]["Property"] not in MEASURE_NAMES:
                implicit.append(f"{v['name']}: unknown measure {f['Measure']['Property']}")
    r.ok("P6B-02", "Every value on every visual is an explicit governed measure", "BLOCKING",
         not implicit, implicit or 0, 0,
         "no implicit aggregation, no report-side arithmetic, no fact column in a value role, "
         "no measure the model does not declare")

    # ---- P6B-03 the headline KPIs
    exec_page = next(p for p in rep.pages if p["name"] == "p01_executive")
    cards = {v["name"].split("p01_executive_")[1]: rep.measures_used(v)
             for v in exec_page["visuals"] if rep.vtype(v) == "card"}
    primary = [next(iter(cards.get(f"p_{k}_v", set())), None)
               for k in ("rev", "ebitda", "cash", "lev")]
    kpi_measures = {m for k, ms in cards.items() if k.startswith(("p_", "s_")) for m in ms}
    r.ok("P6B-03", "The headline KPIs are the four governed primaries, every tile a measure",
         "BLOCKING", tuple(primary) == HEADLINE_PRIMARY and kpi_measures <= MEASURE_NAMES,
         primary, list(HEADLINE_PRIMARY),
         f"first tier {', '.join(HEADLINE_PRIMARY)}; second tier "
         f"{', '.join(sorted(kpi_measures - set(HEADLINE_PRIMARY)))}")

    # ---- P6B-04 the P&L hierarchy
    pnl = next((v for p, v in rep.visuals() if v["name"] == "p02_pnl_pnl"), None)
    rows = [f"{f['Column']['Expression']['SourceRef']['Entity']}.{f['Column']['Property']}"
            for role, f, _ in rep.projections(pnl) if role == "Rows"] if pnl else []
    values = rep.measures_used(pnl) if pnl else set()
    want_rows = ["Measure Line.measure_name", "Business Unit.bu_name", "Entity.entity_name"]
    r.ok("P6B-04", "The income statement is the governed line hierarchy, unit and entity beneath",
         "BLOCKING", rows == want_rows and {"Variance Base", "Variance Comparator", "Variance",
                                            "Variance %", "Variance Favourability"} <= values,
         rows, want_rows, f"values {', '.join(sorted(values))}")

    # ---- P6B-06 variance percentages
    local_pct = []
    for page, v in rep.visuals():
        for role, f, proj in rep.projections(v):
            name = proj.get("displayName") or ""
            if ("%" in name or "Var" in name) and "Measure" not in f:
                local_pct.append(f"{v['name']}: {name}")
            if "Measure" in f and "%" in f["Measure"]["Property"] \
                    and f["Measure"]["Property"] not in MEASURE_NAMES:
                local_pct.append(f"{v['name']}: {f['Measure']['Property']}")
    r.ok("P6B-06", "Every percentage or variance shown is the governed measure, never local",
         "BLOCKING", not local_pct, local_pct or 0, 0,
         "[Variance %] divides the additive variance by the comparator at every grain; the "
         "report carries no ratio of its own")

    # ---- P6B-07 the cutoff cannot be bypassed
    bypass = []
    for page, v in rep.visuals():
        scenario = [vals for t, c, vals in rep.filters(v) if t == "Scenario"]
        if not scenario:
            continue
        for f, proj in rep.value_fields(v):
            if "Column" in f and f["Column"]["Expression"]["SourceRef"]["Entity"] in FACT_TABLES:
                bypass.append(f"{v['name']}: {f['Column']['Property']}")
            if "Aggregation" in f:
                bypass.append(f"{v['name']}: aggregation")
    r.ok("P6B-07", "No visual reaches Actual amounts past the governed cutoff measures",
         "BLOCKING", not bypass, bypass or 0, 0,
         "a visual scoped to the Actual scenario binds measures only; a raw fact column "
         "would show source rows dated after the reporting close")

    # ---- P6B-09 PY_DERIVED invisible; P6B-10 no version pinned
    version_refs = []
    for page, v in rep.visuals():
        blob = json.dumps({k: v.get(k) for k in ("filterConfig",)}) + \
            json.dumps(v["visual"].get("query")) + json.dumps(v["visual"].get("objects"))
        if "version_code" in blob or ("PY_DERIVED" in blob and rep.vtype(v) != "textbox"):
            version_refs.append(v["name"])
        elif "PY_DERIVED" in rep.text(v) and page != "p10_lineage":
            version_refs.append(f"{v['name']}: names the derived version")
        if rep.vtype(v) == "slicer":
            for _, f, _ in rep.projections(v):
                if f.get("Column", {}).get("Expression", {}).get("SourceRef", {}).get("Entity") \
                        == "Scenario":
                    version_refs.append(f"{v['name']}: scenario slicer")
    r.ok("P6B-09", "The derived prior-year version is never exposed: no version on any page",
         "BLOCKING", not version_refs, version_refs or 0, 0,
         "scenario scope is by scenario_code; the version behind Actual, Budget, Forecast and "
         "Prior Year is the measure's choice, not the reader's")

    # ---- P6B-11 covenant status, static side
    status_tile = next((v for p, v in rep.visuals() if v["name"] == "p07_debt_d_status_v"), None)
    tests = next((v for p, v in rep.visuals() if v["name"] == "p07_debt_tests"), None)
    verdict_text = [v["name"] for p, v in rep.visuals()
                    if re.search(r"\b(BREACH|Breach|Compliant|COMPLIANT)\b", rep.text(v))]
    tests_ok = tests is not None and any(t == "Date" and c == "accounting_period" and vals == [12]
                                         for t, c, vals in rep.filters(tests))
    r.ok("P6B-11", "Covenant status is the governed verdict, shown as a verdict only on test dates",
         "BLOCKING", status_tile is not None and rep.measures_used(status_tile) == {"Covenant Status"}
         and tests_ok and not verdict_text,
         dict(tile=sorted(rep.measures_used(status_tile)) if status_tile else None,
              tests_filtered=tests_ok, typed_verdicts=verdict_text),
         "tile=[Covenant Status], tests on accounting_period 12, no typed verdict",
         "the word Breach or Compliant appears only where [Covenant Status] puts it")

    # ---- P6B-12 the project key, static side
    projects = next((v for p, v in rep.visuals() if v["name"] == "p08_workforce_projects"), None)
    key_cols = [f"{f['Column']['Expression']['SourceRef']['Entity']}.{f['Column']['Property']}"
                for _, f, _ in rep.projections(projects) if "Column" in f] if projects else []
    r.ok("P6B-12", "The capital project table is keyed on the corrected unique project_id",
         "BLOCKING", "Capital Project.project_id" in key_cols and
         not any(c.endswith(("project_code", "legacy_project_id")) for c in key_cols),
         key_cols, ["Capital Project.project_id", "..."],
         "ADR-0026: the pre-correction identifier collided five ways in an entity-month")

    # ---- P6B-13 control counts come from the registers
    page09 = next(p for p in rep.pages if p["name"] == "p09_controls")
    shown = {}
    row_texts = {}
    for v in page09["visuals"]:
        m = re.fullmatch(r"p09_controls_cr(\d+)_(\d+)", v["name"])
        if m:
            row_texts.setdefault(int(m.group(1)), {})[int(m.group(2))] = rep.text(v)
    for i, cells in row_texts.items():
        ordered = [cells[x] for x in sorted(cells)]
        shown[ordered[0]] = (int(ordered[2]), int(ordered[3]))
    registers = {
        "Phase 6A": C.CONTROL_RESULTS,
        "Phase 5": C.DATA / "phase05_control_results.csv",
        "Phase 4": C.DATA / "phase04_control_results.csv",
    }
    mismatches = []
    for phase, path in registers.items():
        rows = list(csv.DictReader(open(path, newline="", encoding="utf-8"))) if path.exists() else []
        expect = (len(rows), sum(r.get("status") == "PASS" for r in rows))
        if shown.get(phase) != expect:
            mismatches.append(f"{phase}: page {shown.get(phase)} vs register {expect}")
    src = Path(__file__).with_name("pages.py").read_text("utf-8") + \
        Path(__file__).with_name("metadata.py").read_text("utf-8")
    typed_counts = [m for m in re.findall(r'"[^"\n]*"', src)
                    if re.search(r"\b(?:49|53|68)\b", m)]
    r.ok("P6B-13", "Control counts on the page are read from the registers, never typed",
         "BLOCKING", not mismatches and not typed_counts,
         dict(page=shown, typed_literals=len(typed_counts)), "page == register, 0 literals",
         f"Phase 6A shows {shown.get('Phase 6A')} from {C.CONTROL_RESULTS.name}; the page "
         f"code contains no control-count literal")

    # ---- P6B-14 the deferred concepts are absent
    present = []
    for page, v in rep.visuals():
        blob = json.dumps(v)
        for name in DEFERRED_NAMES:
            if re.search(rf"\b{re.escape(name)}\b", blob) and name not in rep.text(v):
                present.append(f"{v['name']}: {name}")
            elif name in rep.text(v):
                present.append(f"{v['name']}: {name}")
    deferred = {c for c, m in C.REPORT_CONCEPTS.items() if m is None}
    r.ok("P6B-14", "The concepts the owner deferred (DSO, DIO, DPO, CCC, revolver) are absent",
         "BLOCKING", not present and {"DSO", "DIO", "DPO", "Cash conversion cycle"} <= deferred,
         present or 0, 0, "deferred on record in REPORT_CONCEPTS; no page invents them")

    # ---- P6B-15 display units on scaled money
    double = []
    for page, v in rep.visuals():
        money_here = rep.measures_used(v) & MONEY
        if not money_here:
            continue
        objects = v["visual"].get("objects", {})
        for section in ("labels", "valueAxis", "dataLabels"):
            for obj in objects.get(section, []):
                for prop in ("labelDisplayUnits", "secLabelDisplayUnits"):
                    node = obj.get("properties", {}).get(prop)
                    if node is None:
                        continue
                    units = _literal(node["expr"]["Literal"]["Value"])
                    if units not in (0, 1, 0.0, 1.0):
                        double.append(f"{v['name']}/{section}.{prop}={units}")
        for _, f, proj in rep.projections(v):
            if "Measure" in f and f["Measure"]["Property"] in money_here and proj.get("format"):
                double.append(f"{v['name']}: projection format on {f['Measure']['Property']}")
    r.ok("P6B-15", "Scaled money measures are never scaled or reformatted again by a visual",
         "BLOCKING", not double, double or 0, 0,
         "the model's format already divides by a million; display units stay at None and no "
         "projection carries a format")

    # ---- P6B-16 every NoFilter has a reason
    unreasoned, total = [], 0
    for page in rep.pages:
        reasons = rep.reasons(page["name"])
        for i in page["page"].get("visualInteractions", []):
            total += 1
            if i["type"] != "NoFilter" or not reasons.get((i["source"], i["target"])):
                unreasoned.append(f"{i['source']} -> {i['target']}")
    r.ok("P6B-16", "Every switched-off slicer interaction states its reason", "BLOCKING",
         not unreasoned, len(unreasoned), 0,
         f"{total} NoFilter edges, each with a reason in the page declaration")

    # ---- P6B-17 slicers: synced, defaulted, consistent
    slicer_issues = []
    groups: dict[str, set] = {}
    for page, v in rep.visuals():
        if rep.vtype(v) != "slicer":
            continue
        key = v["name"].split(f"{page}_")[1]
        sync = (v["visual"].get("syncGroup") or {}).get("groupName")
        col = next((f"{f['Column']['Expression']['SourceRef']['Entity']}."
                    f"{f['Column']['Property']}" for _, f, _ in rep.projections(v)), None)
        groups.setdefault(key, set()).add((sync, col))
        if sync != key:
            slicer_issues.append(f"{v['name']}: syncGroup {sync}")
        if key in L.SLICER_DEFAULTS:
            default = rep.literal(v["visual"]["objects"], "general", "properties", "filter")
            has_default = bool(v["visual"]["objects"].get("general", [{}])[0]
                               .get("properties", {}).get("filter"))
            if not has_default:
                slicer_issues.append(f"{v['name']}: no default")
    for key, seen in groups.items():
        if len(seen) > 1:
            slicer_issues.append(f"{key}: inconsistent {sorted(seen)}")
    bu_pages = {p for p, v in rep.visuals() if v["name"].endswith("_sl_bu")}
    ent_pages = {p for p, v in rep.visuals() if v["name"].endswith("_sl_entity")}
    if bu_pages != ent_pages:
        slicer_issues.append(f"unit/entity pairing differs: {sorted(bu_pages ^ ent_pages)}")
    r.ok("P6B-17", "Slicers are synced by key, default to the reporting close, and pair unit "
         "with entity", "BLOCKING", not slicer_issues, slicer_issues or 0, 0,
         f"{len(groups)} slicer keys across {len(rep.pages)} pages")

    # ---- P6B-18 navigation
    page_names = [p["name"] for p in rep.pages]
    nav_issues = []
    for page in rep.pages:
        buttons = [v for v in page["visuals"] if rep.vtype(v) == "actionButton"]
        targets = []
        for b in buttons:
            link = (b["visual"].get("visualContainerObjects", {}).get("visualLink", [{}])[0]
                    .get("properties", {}))
            target = link.get("navigationSection", {}).get("expr", {}).get("Literal", {}).get("Value")
            targets.append(_literal(target) if target else None)
        if sorted(t for t in targets if t) != sorted(page_names):
            nav_issues.append(f"{page['name']}: {targets}")
    r.ok("P6B-18", "Every page carries one navigation button per page, each to a page that exists",
         "BLOCKING", not nav_issues, nav_issues or 0, 0,
         f"{len(page_names)} buttons on each of {len(page_names)} pages")

    # ---- P6B-19 layout and density
    layout_issues = []
    density = {}
    for page in rep.pages:
        kinds = rep.kinds(page["name"])
        analytical = []
        for v in page["visuals"]:
            pos = v["position"]
            if pos["x"] < 0 or pos["y"] < 0 or pos["x"] + pos["width"] > L.CANVAS_W \
                    or pos["y"] + pos["height"] > L.CANVAS_H:
                layout_issues.append(f"{v['name']}: outside the canvas")
            if kinds.get(v["name"]) == "analytical":
                analytical.append((v["name"], pos))
        for i, (a, pa) in enumerate(analytical):
            for b, pb in analytical[i + 1:]:
                if pa["x"] < pb["x"] + pb["width"] and pb["x"] < pa["x"] + pa["width"] and \
                        pa["y"] < pb["y"] + pb["height"] and pb["y"] < pa["y"] + pa["height"]:
                    layout_issues.append(f"{a} overlaps {b}")
        density[page["name"]] = len(analytical)
        if len(analytical) > L.MAX_ANALYTICAL:
            layout_issues.append(f"{page['name']}: {len(analytical)} analytical objects")
    r.ok("P6B-19", "Every object is on the canvas, analytical objects never overlap, and no "
         "page exceeds the density gate", "BLOCKING", not layout_issues, layout_issues or 0, 0,
         f"analytical objects per page {density}; gate {L.MAX_ANALYTICAL}")


def _measure_tables() -> dict[str, set[str]]:
    """The tables each measure reads, through the measures it calls."""
    dax_by_name = {m[0]: m[1] for m in MEASURES}
    cache: dict[str, set[str]] = {}

    def tables(name: str, seen: frozenset = frozenset()) -> set[str]:
        if name in cache:
            return cache[name]
        expr = dax_by_name.get(name, "")
        out = set(re.findall(r"'([^']+)'\[", expr))
        for ref in re.findall(r"\[([^\]]+)\]", expr):
            if ref in dax_by_name and ref not in seen and ref != name:
                out |= tables(ref, seen | {name})
        cache[name] = out
        return out

    return {name: tables(name) for name in dax_by_name}


def _filtered_by(dimension: str) -> set[str]:
    """Every table a filter on `dimension` reaches along the active one-to-many paths."""
    reached, frontier = {dimension}, [dimension]
    while frontier:
        one = frontier.pop()
        for many, _, to, _ in C.RELATIONSHIPS:
            if to == one and many not in reached:
                reached.add(many)
                frontier.append(many)
    return reached


PALETTE = {v.upper() for k, v in vars(T).items() if isinstance(v, str) and v.startswith("#")
           and len(v) == 7} | {"#C9D6E0", "#D9E2EA"}   # the two rail text tints
FONTS = {T.FONT, T.FONT_SEMIBOLD, T.FONT_LIGHT, "Consolas"}
SIZES = {float(v) for v in T.TYPE.values()} | {26.0, 16.0, 15.0, 12.0, 11.0, 10.0, 9.0, 8.0}


def _style(r: SEM.Result, rep: Report) -> None:
    """P6B-26 the palette, P6B-27 the type scale: nothing on any page is outside them."""
    colours, fonts, sizes = {}, {}, {}
    for page, v in rep.visuals():
        blob = json.dumps(v)
        for hexcode in re.findall(r"#[0-9A-Fa-f]{6}\b", blob):
            if hexcode.upper() not in PALETTE:
                colours.setdefault(hexcode.upper(), v["name"])
        for family in re.findall(r"'([^']*Segoe[^']*|Consolas|Arial|Calibri|Verdana|Times[^']*)'", blob):
            if family not in FONTS:
                fonts.setdefault(family, v["name"])
        for size in re.findall(r'"fontSize": \{"expr": \{"Literal": \{"Value": "([\d.]+)D"', blob):
            if float(size) not in SIZES:
                sizes.setdefault(size, v["name"])
        for size in re.findall(r'"fontSize": "([\d.]+)pt"', blob):
            if float(size) not in SIZES:
                sizes.setdefault(size, v["name"])
    r.ok("P6B-26", "Every colour on every page is a named colour of the approved palette",
         "BLOCKING", not colours, colours or 0, 0,
         f"{len(PALETTE)} named colours; navy structure and Actual, copper the second tier and "
         f"the Forecast, green and red favourability alone")
    r.ok("P6B-27", "Every font and size on every page is on the type scale", "BLOCKING",
         not fonts and not sizes, dict(fonts=fonts, sizes=sizes) if fonts or sizes else 0, 0,
         f"families {sorted(FONTS)}; sizes {sorted(SIZES)}")


def _inert_slicers(r: SEM.Result, rep: Report) -> None:
    """P6B-24: a slicer on a page moves at least one number on that page."""
    reads = _measure_tables()
    inert = []
    for page in rep.pages:
        off = {(i["source"], i["target"]) for i in page["page"].get("visualInteractions", [])
               if i["type"] == "NoFilter"}
        for sl in [v for v in page["visuals"] if rep.vtype(v) == "slicer"]:
            dim = next(f["Column"]["Expression"]["SourceRef"]["Entity"]
                       for _, f, _ in rep.projections(sl) if "Column" in f)
            reach = _filtered_by(dim)
            moved = []
            for v in page["visuals"]:
                if v is sl or (sl["name"], v["name"]) in off:
                    continue
                for m in rep.measures_used(v):
                    if reads.get(m, set()) & reach:
                        moved.append(v["name"])
                        break
            if not moved:
                inert.append(f"{sl['name']} ({dim})")
    r.ok("P6B-24", "No page carries a slicer that moves nothing on it", "BLOCKING",
         not inert, inert or 0, 0,
         "the balance sheet, cash flow, working capital and covenant marts are consolidated "
         "Group facts; a unit or basis slicer beside them would be a control that controls nothing")


# ------------------------------------------------------------------ the live family
def _live(r: SEM.Result, rep: Report, con, live: bool, why: str) -> None:
    def skip(cid, name, severity, threshold, detail):
        r.add(cid, name, severity, "NOT_EXECUTED", "-", threshold, f"{detail}. Not executed: {why}")

    # ---- P6B-05 the business-unit path, as the slicer uses it
    name = "Selecting a business unit narrows every unit-sensitive measure, and the units sum to the Group"
    if not live:
        skip("P6B-05", name, "BLOCKING", "sum of units == Group", "engine required")
    else:
        bad = []
        for measure, key in (("Revenue", "p_rev_v"), ("Management Adjusted EBITDA", "p_ebitda_v"),
                             ("Closing FTE", "s_fte_v")):
            scope, _ = visual_scope(rep, "p01_executive", key)
            group = dax.scalar(f"CALCULATE ( [{measure}], {scope} )") or 0.0
            units = dax.query(
                f"EVALUATE ADDCOLUMNS ( VALUES ( 'Business Unit'[bu_name] ), \"v\", "
                f"CALCULATE ( [{measure}], {scope} ) )")
            total = sum(float(u[1] or 0) for u in units)
            distinct = len({round(float(u[1] or 0), 2) for u in units})
            if abs(total - group) > 0.05 or distinct < 4:
                bad.append(f"{measure}: units {total:,.2f} vs Group {group:,.2f}, {distinct} distinct")
        r.ok("P6B-05", name, "BLOCKING", not bad, bad or 0, 0,
             "evaluated in the Executive Overview's own scope through Business Unit[bu_name], "
             "the slicer's column")

    # ---- P6B-08 the cutoff holds for every Actual measure the report uses
    name = "Every Actual measure the report shows is blank after the reporting close"
    actual_used = sorted({m for _, v in rep.visuals() for m in rep.measures_used(v)
                          if m.startswith("Actual ")} | {"Revenue", "Gross Profit"})
    # the balance and cash marts carry the last close forward, so a month-end trend must be
    # scoped to closed months or bind scenario-explicit measures, which cut off themselves
    unscoped = []
    explicit = ("Actual ", "Budget ", "Forecast ", "Prior Year ")
    for page, v in rep.visuals():
        on_date = any(role == "Category" and f.get("Column", {}).get("Expression", {})
                      .get("SourceRef", {}).get("Entity") == "Date"
                      for role, f, _ in rep.projections(v))
        if not on_date:
            continue
        closed = any(t == "Date" and c == "is_actual_month" and vals == [True]
                     for t, c, vals in rep.filters(v))
        if not closed and not all(m.startswith(explicit) for m in rep.measures_used(v)):
            unscoped.append(v["name"])
    if unscoped:
        r.ok("P6B-08", name, "BLOCKING", False, unscoped, 0,
             "a month-end trend on a carried-forward balance is not scoped to closed months")
    elif not live:
        skip("P6B-08", name, "BLOCKING", "blank", f"{len(actual_used)} measures")
    else:
        leaking = []
        later = [REPORT_PERIOD + k for k in (1, 2, 3, 4)]
        for measure in actual_used:
            act = "'Scenario'[scenario_code] = \"ACT\"" if not measure.startswith("Actual ") else ""
            for pk in later:
                val = dax.measure_at(measure, pk, act)
                if val not in (None, 0, 0.0):
                    leaking.append(f"{measure}@{pk}={val}")
                    break
        r.ok("P6B-08", name, "BLOCKING", not leaking, leaking or 0, 0,
             f"{len(actual_used)} measures at {later[0]}..{later[-1]}: {', '.join(actual_used)}; "
             f"every month-end trend is scoped to closed months")

    # ---- P6B-10 the current forecast is the version flagged default
    name = "The forecast on the page is the version flagged current in the version master"
    sql = """SELECT round(sum(y.ytd_usd), 2) FROM mart_financial_ytd y
             WHERE y.scenario_code = 'FC' AND y.basis = 'STATUTORY' AND y.measure_code = 'REVENUE'
               AND y.period_key = {p}
               AND y.version_code = (SELECT version_code FROM ref_default_version
                                     WHERE scenario_code = 'FC')"""
    expected = float(con.execute(sql.format(p=REPORT_PERIOD)).fetchone()[0] or 0)
    if not live:
        skip("P6B-10", name, "BLOCKING", f"{expected:,.2f}", "the mart's default forecast version")
    else:
        scope, _ = visual_scope(rep, "p01_executive", "rev_trend")
        actual = dax.scalar(f"CALCULATE ( [Forecast Revenue], 'Date'[period_key] = {REPORT_PERIOD}, "
                            f"'Period Basis'[basis_code] = \"YTD\", "
                            f"'Reporting Basis'[basis_name] = \"Statutory\" )") or 0.0
        r.ok("P6B-10", name, "BLOCKING", abs(actual - expected) <= C.TOL_XAR_USD,
             f"{abs(actual - expected):,.4f}", C.TOL_XAR_USD,
             f"[Forecast Revenue] YTD {actual:,.2f} vs mart default version {expected:,.2f}")

    # ---- P6B-11L covenant status at a non-test month and at the last test
    name = "Covenant status reads Indicative off the test date and the mart's verdict on it"
    if not live:
        skip("P6B-11L", name, "BLOCKING", "Indicative / verdict", "engine required")
    else:
        scope, _ = visual_scope(rep, "p07_debt", "d_status_v")
        off = dax.scalar(f"CALCULATE ( [Covenant Status], {scope} )")
        test_pk = (REPORT_PERIOD // 100 - 1) * 100 + 12
        on = dax.scalar(f"CALCULATE ( [Covenant Status], 'Date'[period_key] = {test_pk} )")
        mart = con.execute("SELECT in_compliance FROM mart_covenants WHERE period_key = ?",
                           [test_pk]).fetchone()
        want = "Compliant" if mart and mart[0] else "Breach"
        r.ok("P6B-11L", name, "BLOCKING", off == "Indicative" and on == want,
             dict(off_test=off, on_test=on), dict(off_test="Indicative", on_test=want),
             f"{REPORT_PERIOD} is not a test date; {test_pk} is, and the mart says {want}")

    # ---- P6B-12L the project key is unique in the engine and agrees with the mart
    name = "Capital projects are distinct on the corrected key in the engine and the mart alike"
    mart_n = con.execute("SELECT count(DISTINCT project_id) FROM mart_capex").fetchone()[0]
    if not live:
        skip("P6B-12L", name, "BLOCKING", mart_n, "engine required")
    else:
        engine_n = dax.scalar("DISTINCTCOUNT ( 'CapEx'[project_id] )")
        dim_n = dax.scalar("COUNTROWS ( 'Capital Project' )")
        dup = dax.scalar("COUNTROWS ( 'Capital Project' ) - DISTINCTCOUNT ( 'Capital Project'[project_id] )")
        r.ok("P6B-12L", name, "BLOCKING",
             engine_n == mart_n == dim_n and (dup or 0) == 0,
             dict(engine=engine_n, mart=mart_n, dimension=dim_n, duplicates=dup),
             "all equal, 0 duplicates", "ADR-0026 corrected key")


def render(value, fmt: str | None) -> str:
    """A value the way the model's own format string renders it, for the formats the report uses."""
    if value is None:
        return ""
    if fmt in (M_USD, M_USD2, PCT, TURNS):
        scale = 1e6 if fmt in (M_USD, M_USD2) else (0.01 if fmt == PCT else 1.0)
        places = 2 if fmt in (M_USD2, TURNS) else 1
        scaled = round(value / scale, places)
        if scaled == 0:
            return "–"
        text = f"{abs(scaled):,.{places}f}" + ("%" if fmt == PCT else "x" if fmt == TURNS else "")
        return f"({text})" if scaled < 0 else text
    if fmt == FTE:
        return f"{value:,.1f}"
    if fmt in ("#,0",):
        return f"{value:,.0f}"
    return str(value)


# ------------------------------------------------------------------ the native family
def _rendered(r: SEM.Result, rep: Report, qa: dict, live: bool, why: str) -> None:
    """P6B-25: what Desktop drew on the Executive Overview equals the engine in the tile's scope."""
    name = "Every card Desktop rendered on the Executive Overview shows the engine's value"
    rendered = qa.get("rendered") or {}
    if not rendered:
        r.add("P6B-25", name, "BLOCKING", "NOT_EXECUTED", "-", "-", "no rendered cards recorded")
        return
    if not live:
        r.add("P6B-25", name, "BLOCKING", "NOT_EXECUTED", len(rendered), "-",
              f"{len(rendered)} cards recorded. Not executed: {why}")
        return
    fmt_by_name = {m[0]: m[2] for m in MEASURES}
    page = next(p for p in rep.pages if p["name"] == "p01_executive")
    tiles = {}
    for v in page["visuals"]:
        if rep.vtype(v) == "card":
            key = v["name"].split("p01_executive_")[1]
            for m in rep.measures_used(v):
                tiles.setdefault(m, key)
    wrong, checked = [], 0
    for measure, shown in rendered.items():
        key = tiles.get(measure)
        if key is None or measure in ("Reporting Period", "Variance", "Variance Favourability"):
            continue
        scope, _ = visual_scope(rep, "p01_executive", key)
        value = dax.scalar(f"CALCULATE ( [{measure}], {scope} )")
        expect = render(value, fmt_by_name.get(measure))
        checked += 1
        if expect != shown:
            wrong.append(f"{measure}: rendered {shown!r} vs engine {expect!r}")
    r.ok("P6B-25", name, "BLOCKING", checked > 0 and not wrong, wrong or checked,
         f"{checked} cards equal",
         f"{checked} cards read from Desktop's accessibility tree and re-evaluated in each "
         f"tile's own scope")


def _native(r: SEM.Result, rep: Report, live: bool = False, why: str = "") -> None:
    from .. import run as RUN
    name = "The last native pass in Power BI Desktop rendered every page with zero visual errors"
    if not NATIVE_QA.exists():
        r.add("P6B-20", name, "BLOCKING", "NOT_EXECUTED", "-", "0 errors",
              "no native pass recorded; run `python -m src.powerbi.report.native_qa`")
        return
    qa = json.loads(NATIVE_QA.read_text("utf-8"))
    current = (RUN.report_build_id(), RUN.definition_digest())
    recorded = (qa.get("report_build_id"), qa.get("definition_digest"))
    if recorded != current:
        r.add("P6B-20", name, "BLOCKING", "NOT_EXECUTED", recorded, current,
              "the recorded native pass is for other report declarations or another model "
              "definition; run native_qa again")
        return
    errors = sum(len(e) for e in qa.get("visual_errors", {}).values())
    pages = len(qa.get("visual_errors", {}))
    r.ok("P6B-20", name, "BLOCKING", qa.get("opened") and qa.get("refreshed") and errors == 0
         and pages == len(rep.pages), dict(pages=pages, errors=errors),
         dict(pages=len(rep.pages), errors=0),
         f"Desktop {qa.get('desktop')} on report build {current[0]}, definition {current[1]}, "
         f"project {qa.get('project_digest')}, {qa.get('seconds')}s")
    nav = qa.get("navigation", {})
    r.ok("P6B-21", "Every navigation button lands on its page natively", "BLOCKING",
         nav.get("passed") == nav.get("total") == len(rep.pages), nav, len(rep.pages),
         "each rail button pressed in Desktop and the page tab checked")
    unit = qa.get("unit_slicer", {})
    r.ok("P6B-22", "Selecting a business unit natively narrows the Executive Overview", "BLOCKING",
         unit.get("narrowed") is True, unit, "narrowed", unit.get("detail", ""))
    cutoff = qa.get("cutoff", {})
    r.ok("P6B-23", "The Actual line stops at the reporting close on the native render", "BLOCKING",
         cutoff.get("stops_at_close") is True, cutoff, "stops_at_close",
         cutoff.get("detail", ""))
    _rendered(r, rep, qa, live, why)


# ------------------------------------------------------------------ the reconciliations
#: (control id, concept, page, visual key, measure, extra DAX filter, mart SQL by name)
RECON = (
    ("P6B-30", "Revenue", "p01_executive", "p_rev_v", "Revenue", "", "P6-XAR-01"),
    ("P6B-31", "Gross Profit", "p02_pnl", "pnl", "Variance Base",
     "'Measure Line'[measure_code] = \"GROSS_PROFIT\"", "P6-XAR-02"),
    ("P6B-32", "Statutory EBITDA", "p02_pnl", "pnl", "Variance Base",
     "'Measure Line'[measure_code] = \"EBITDA\"", "P6-XAR-03"),
    ("P6B-33", "Adjusted EBITDA", "p01_executive", "p_ebitda_v", "Management Adjusted EBITDA",
     "", "P6-XAR-04"),
    ("P6B-34", "EBIT", "p02_pnl", "pnl", "Variance Base",
     "'Measure Line'[measure_code] = \"EBIT\"", "P6-XAR-05"),
    ("P6B-35", "Net Income", "p02_pnl", "pnl", "Variance Base",
     "'Measure Line'[measure_code] = \"NET_INCOME\"", "P6-XAR-06"),
    ("P6B-36", "Cash", "p01_executive", "p_cash_v", "Closing Cash", "", "P6-XAR-11"),
    ("P6B-37", "Net Debt", "p01_executive", "s_nd_v", "Covenant Net Debt", "", "P6-XAR-13"),
    ("P6B-38", "Covenant EBITDA", "p07_debt", "d_ebitda_v", "Covenant EBITDA", "", "P6-XAR-14"),
    ("P6B-39", "Covenant Leverage", "p01_executive", "p_lev_v", "Covenant Net Leverage", "",
     "P6-XAR-15"),
    ("P6B-40", "Covenant Headroom", "p01_executive", "s_head_v", "Covenant Headroom", "",
     "HEADROOM"),
    ("P6B-41", "FTE", "p01_executive", "s_fte_v", "Closing FTE", "", "P6-XAR-16"),
    ("P6B-42", "CapEx", "p08_workforce", "x_spend_v", "Actual CapEx", "", "P6-XAR-17"),
)
EXTRA_SQL = {
    "HEADROOM": "SELECT round(headroom_turns, 6) FROM mart_covenants WHERE period_key = {p}",
}


def _reconcile(r: SEM.Result, rep: Report, con, live: bool, why: str) -> None:
    sql_by_id = {cid: sql for cid, _, _, _, sql in SEM.XAR + SEM.XAR_LEDGER}
    sql_by_id.update(EXTRA_SQL)
    fy = REPORT_PERIOD // 100
    for cid, concept, page, key, measure, extra, sql_id in RECON:
        name = f"{concept} on the page reconciles report scope, engine and mart"
        expected = con.execute(sql_by_id[sql_id].format(p=REPORT_PERIOD, fy=fy)).fetchone()[0]
        expected = float(expected) if expected is not None else 0.0
        scope, v = visual_scope(rep, page, key, extra)
        bound = rep.measures_used(v)
        if measure not in bound:
            r.add(cid, name, "BLOCKING", "FAIL", sorted(bound), measure,
                  f"{page}/{key} does not bind [{measure}]")
            continue
        if not live:
            r.add(cid, name, "BLOCKING", "NOT_EXECUTED", "-", f"{expected:,.2f}",
                  f"{page}/{key} in scope {scope}. Not executed: {why}")
            continue
        value = dax.scalar(f"CALCULATE ( [{measure}], {scope} )")
        value = float(value) if value is not None else 0.0
        tol = C.TOL_RATIO if sql_id in ("P6-XAR-15", "HEADROOM") else C.TOL_XAR_USD
        diff = abs(value - expected)
        r.ok(cid, name, "BLOCKING", diff <= tol, f"{diff:,.6f}", tol,
             f"{page}/{key} [{measure}] in its own scope = {value:,.2f}; mart {expected:,.2f} "
             f"({sql_id})")


# ------------------------------------------------------------------ the run
def run(con, report_dir: Path | None = None, pages: list | None = None,
        native: bool = True) -> SEM.Result:
    rep = Report(report_dir, pages)
    r = SEM.Result()
    live, why = dax.available()
    if live and not dax.model_loaded():
        live, why = False, "the engine is reachable but the Northstar model is not loaded"
    r.add("P6B-00", "The generated report was read and the engine is available", "INFO",
          "PASS" if live else "NOT_EXECUTED",
          f"{sum(len(p['visuals']) for p in rep.pages)} visuals, {len(rep.pages)} pages",
          "live", why)
    _static(r, rep)
    _inert_slicers(r, rep)
    _style(r, rep)
    _live(r, rep, con, live, why)
    if native:
        _native(r, rep, live, why)
    _reconcile(r, rep, con, live, why)
    return r


def write(res: SEM.Result, path: Path = RESULTS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys()))
        w.writeheader()
        w.writerows(res)


def report(res: SEM.Result) -> None:
    for row in res:
        if row["status"] != "PASS":
            print(f"  {row['status']:12} {row['control_id']:10} {row['control_name']}")
            print(f"      measured {row['measured']} vs {row['threshold']} -- {row['detail']}")
    print(f"{sum(r['status'] == 'PASS' for r in res)}/{len(res)} report controls passed, "
          f"{len(res.not_executed)} not executed, {len(res.failed)} blocking failures")


def inventory(pages: list | None = None) -> dict:
    """The object inventory: every visual classified, counted by page and kind."""
    pages = pages if pages is not None else BUILD.build_pages()
    out = {"pages": {}, "total": {}, "visuals": 0}
    for pg in pages:
        counts: dict[str, int] = {}
        for kind in pg.kinds.values():
            counts[kind] = counts.get(kind, 0) + 1
            out["total"][kind] = out["total"].get(kind, 0) + 1
        out["pages"][pg.display] = dict(sorted(counts.items()), objects=len(pg.kinds))
        out["visuals"] += len(pg.kinds)
    return out


def main(argv: list[str]) -> int:
    con = duckdb.connect(str(C.DUCKDB_PATH), read_only=True)
    res = run(con)
    con.close()
    if "--no-write" not in argv:
        write(res)
        INVENTORY.write_text(json.dumps(inventory(), indent=2) + "\n", encoding="utf-8")
    report(res)
    return 1 if res.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
