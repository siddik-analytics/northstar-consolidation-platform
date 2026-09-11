"""
The Phase 6B report fixtures: each puts one report-level fault into a scratch copy of the
generated report and asks whether the control written for it notices.

    python -m src.powerbi.report.faults

A fixture is a mutation of the *generated files* -- a typed number where a card was, an
implicit sum where a measure was, a stale key, a verdict spelled out in text -- because that
is the form in which such a fault would reach Desktop. Nothing here touches the committed
report; every fixture works on its own copy under the scratch directory and is deleted after.
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import duckdb

from .. import config as C
from . import build as BUILD
from . import controls as K
from . import pages as PAGES
from . import pbir as P
from . import theme as T


def _visual(report_dir: Path, page: str, key: str) -> tuple[Path, dict]:
    path = report_dir / "definition" / "pages" / page / "visuals" / f"{page}_{key}" / "visual.json"
    return path, json.loads(path.read_text("utf-8"))


def _save(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _textbox_in_place(report_dir: Path, page: str, key: str, text: str) -> None:
    """The visual becomes a textbox saying `text`, at the same position."""
    path, v = _visual(report_dir, page, key)
    pos = v["position"]
    box = P.container(page, key, pos["x"], pos["y"], pos["width"], pos["height"],
                      P.textbox(text, 26.0, T.NAVY, True), z=pos["z"])
    _save(path, box)


# ------------------------------------------------------------------ the fixtures
def f01_typed_kpi(d: Path) -> None:
    """The Revenue card replaced by the number typed as text."""
    _textbox_in_place(d, "p01_executive", "p_rev_v", "279.0")


def f02_implicit_measure(d: Path) -> None:
    """A chart series that is Sum of a fact column, not a measure."""
    path, v = _visual(d, "p03_bu", "bu_rev")
    proj = v["visual"]["query"]["queryState"]["Y"]["projections"][0]
    proj["field"] = {"Aggregation": {"Expression": {"Column": {
        "Expression": {"SourceRef": {"Entity": "Financials"}}, "Property": "amount_usd"}},
        "Function": 0}}
    proj["queryRef"] = "Sum(Financials.amount_usd)"
    proj["nativeQueryRef"] = "Sum of amount_usd"
    _save(path, v)


def f03_cutoff_bypassed(d: Path) -> None:
    """Account detail reading the raw fact column under an Actual filter: post-close rows show."""
    path, v = _visual(d, "p02_pnl", "accounts")
    proj = v["visual"]["query"]["queryState"]["Values"]["projections"][0]
    proj["field"] = {"Column": {"Expression": {"SourceRef": {"Entity": "Financial Detail"}},
                                "Property": "amount_usd"}}
    proj["queryRef"] = "Financial Detail.amount_usd"
    proj["nativeQueryRef"] = "amount_usd"
    _save(path, v)


def f04_typed_verdict(d: Path) -> None:
    """The covenant status tile replaced by the word Breach, typed."""
    _textbox_in_place(d, "p07_debt", "d_status_v", "Breach")


def f05_stale_project_key(d: Path) -> None:
    """The project table keyed on the pre-correction identifier."""
    path, v = _visual(d, "p08_workforce", "projects")
    for proj in v["visual"]["query"]["queryState"]["Values"]["projections"]:
        col = proj["field"].get("Column")
        if col and col["Property"] == "project_id":
            col["Property"] = "project_code"
            proj["queryRef"] = "Capital Project.project_code"
            proj["nativeQueryRef"] = "project_code"
    _save(path, v)


def f06_typed_control_count(d: Path) -> None:
    """The Phase 6A control count on the page typed as the stale 53."""
    page = d / "definition" / "pages" / "p09_controls" / "visuals"
    for folder in page.glob("p09_controls_cr*_*"):
        v = json.loads((folder / "visual.json").read_text("utf-8"))
        if K.Report.text(v) == "Phase 6A":
            row = folder.name.split("_cr")[1].split("_")[0]
            for other in page.glob(f"p09_controls_cr{row}_*"):
                ov = json.loads((other / "visual.json").read_text("utf-8"))
                if K.Report.text(ov) == "68":
                    ov["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0] \
                        ["textRuns"][0]["value"] = "53"
                    _save(other / "visual.json", ov)
                    break
            break


def f07_local_variance_pct(d: Path) -> None:
    """The outlook's Var % computed in the visual as Variance / Comparator."""
    path, v = _visual(d, "p01_executive", "outlook")
    for proj in v["visual"]["query"]["queryState"]["Values"]["projections"]:
        if proj["queryRef"].endswith("Variance %"):
            proj["field"] = {"Arithmetic": {
                "Left": {"Measure": {"Expression": {"SourceRef": {"Entity": C.MEASURES_TABLE}},
                                     "Property": "Variance"}},
                "Right": {"Measure": {"Expression": {"SourceRef": {"Entity": C.MEASURES_TABLE}},
                                      "Property": "Variance Comparator"}},
                "Operator": 3}}
            proj["queryRef"] = "Divide(Variance, Variance Comparator)"
            proj["nativeQueryRef"] = "Var %"
    _save(path, v)


def f08_double_scaled(d: Path) -> None:
    """The Revenue card told to show millions on a measure that already does."""
    path, v = _visual(d, "p01_executive", "p_rev_v")
    v["visual"]["objects"]["labels"][0]["properties"]["labelDisplayUnits"] = P.lit(1000000.0)
    _save(path, v)


def f09_broken_navigation(d: Path) -> None:
    """A rail button pointing at a page that does not exist."""
    path, v = _visual(d, "p02_pnl", "nav_p10_lineage")
    v["visual"]["visualContainerObjects"]["visualLink"][0]["properties"]["navigationSection"] = \
        P.lit("p11_missing")
    _save(path, v)


def f10_double_units_on_axis(d: Path) -> None:
    """A money chart with a K display unit on its value axis."""
    path, v = _visual(d, "p01_executive", "cash_trend")
    v["visual"]["objects"]["valueAxis"][0]["properties"]["labelDisplayUnits"] = P.lit(1000.0)
    _save(path, v)


# the two declaration-level fixtures regenerate the report with a patched page function
@contextmanager
def _patched_page(index: int, factory):
    original = PAGES.PAGES
    PAGES.PAGES = tuple(factory if i == index else f for i, f in enumerate(original))
    try:
        yield
    finally:
        PAGES.PAGES = original


def f11_unreasoned_nofilter():
    """A NoFilter edge with its reason erased after the page was declared."""
    base = PAGES.executive

    def page():
        pg = base()
        pg.reasons = {}
        return pg
    return _patched_page(0, page)


def f12_inert_slicer():
    """A business-unit slicer on the Group-level cash flow page."""
    base = PAGES.cash_flow

    def page():
        pg = base()
        pg.add("sl_bu", 700, 76, 190, 46,
               P.slicer(P.column("Business Unit", "bu_name"), "Business unit", sync="sl_bu"))
        pg.add("sl_entity", 900, 76, 220, 46,
               P.slicer(P.column("Entity", "entity_name"), "Entity", sync="sl_entity"))
        return pg
    return _patched_page(4, page)


FIXTURES = (
    ("F6B-01", "A headline KPI typed as text where a card should be", f01_typed_kpi, "P6B-01"),
    ("F6B-02", "An implicit Sum of a fact column on a chart", f02_implicit_measure, "P6B-02"),
    ("F6B-03", "Account detail reading the raw fact column past the cutoff", f03_cutoff_bypassed,
     "P6B-07"),
    ("F6B-04", "A covenant verdict typed as text off the test date", f04_typed_verdict, "P6B-11"),
    ("F6B-05", "The project table on the pre-correction project key", f05_stale_project_key,
     "P6B-12"),
    ("F6B-06", "The Phase 6A control count typed as the stale 53", f06_typed_control_count,
     "P6B-13"),
    ("F6B-07", "A variance percentage computed in the visual", f07_local_variance_pct, "P6B-06"),
    ("F6B-08", "A million-scaled card on a measure that already scales", f08_double_scaled,
     "P6B-15"),
    ("F6B-09", "A rail button to a page that does not exist", f09_broken_navigation, "P6B-18"),
    ("F6B-10", "A thousands unit on a money chart's axis", f10_double_units_on_axis, "P6B-15"),
    ("F6B-11", "A NoFilter interaction with no reason on record", f11_unreasoned_nofilter,
     "P6B-16"),
    ("F6B-12", "Unit and entity slicers on the Group-level cash flow page", f12_inert_slicer,
     "P6B-24"),
)


def run(con) -> list[dict]:
    scratch = Path(tempfile.mkdtemp(prefix="northstar-6b-"))
    results = []
    try:
        baseline = scratch / "baseline"
        BUILD.generate(baseline)
        for fid, description, fixture, intended in FIXTURES:
            work = scratch / fid
            pages = None
            if fixture.__code__.co_argcount == 1:
                shutil.copytree(baseline, work)
                fixture(work)
                pages = BUILD.build_pages()
            else:
                with fixture():
                    BUILD.generate(work)
                    pages = BUILD.build_pages()
            res = K.run(con, report_dir=work, pages=pages, native=False)
            hit = next((r for r in res if r["control_id"] == intended), None)
            detected = hit is not None and hit["status"] == "FAIL"
            others = sorted(r["control_id"] for r in res
                            if r["status"] == "FAIL" and r["control_id"] != intended)
            results.append(dict(fixture_id=fid, description=description,
                                intended_control=intended,
                                status="DETECTED" if detected else "MISSED",
                                detail=(hit["measured"] if hit else "control absent")[:200],
                                also_failed=", ".join(others)))
            print(f"  {results[-1]['status']:9} {fid}  {description}  -> {intended}"
                  + (f" (also {', '.join(others)})" if others else ""))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return results


def write(rows: list[dict]) -> None:
    with open(K.FAULT_RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str]) -> int:
    con = duckdb.connect(str(C.DUCKDB_PATH), read_only=True)
    rows = run(con)
    con.close()
    if "--no-write" not in argv:
        write(rows)
    detected = sum(r["status"] == "DETECTED" for r in rows)
    print(f"{detected}/{len(rows)} report fixtures detected by their intended control")
    return 0 if detected == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
