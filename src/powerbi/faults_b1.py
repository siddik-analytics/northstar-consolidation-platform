"""
The Phase 6B.1 fixtures: each puts one of the corrected faults back and asks whether the
control written for it notices.

    python -m src.powerbi.faults_b1

``F6B1-01``  one level-2 caption given two sort values in the published Account dimension
             (P6B-D-06 put back) -- `P6B1-HS-01`
``F6B1-02``  the consolidation bridge told to ignore the period slicer, so it reads a scope
             the headline does not -- `P6B1-SC-01`
``F6B1-03``  Layer EBITDA reverted to a plain sum of the bridge fact, blind to the period
             basis and the close -- `P6B1-BR-03`

The data fixture publishes a damaged copy of the dimension beside the real one and points
the table at it, the way the Phase 6A fixtures do; the declaration fixtures patch the page
or the measure for the duration of the fixture. Everything is restored and the clean model
redeployed afterwards.
"""

from __future__ import annotations

import csv
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import duckdb

from . import config as C
from . import controls_b1 as K1
from . import dax, deploy
from .faults import _patched_measure, _patched_tables, _publish
from .report import build as BUILD
from .report import pages as PAGES


@contextmanager
def f01_caption_with_two_sorts():
    """P6B-D-06 again: 'Accrued liabilities' carries two level-2 sort keys."""
    con = ACTIVE_CON
    con.execute("""
        CREATE OR REPLACE TABLE stg_account_two_sorts AS
        SELECT * REPLACE (
            CASE WHEN fs_caption_l2 = 'Accrued liabilities' AND group_account = '219100'
                 THEN 2320 ELSE fs_caption_l2_sort END AS fs_caption_l2_sort)
        FROM dim_semantic_account""")
    _publish(con, "stg_account_two_sorts", "35_semantic")

    def mutate(tables):
        return tuple(dict(t, source="stg_account_two_sorts") if t["name"] == "Account" else t
                     for t in tables)
    try:
        with _patched_tables(mutate):
            yield
    finally:
        con.execute("DROP TABLE IF EXISTS stg_account_two_sorts")
        path = C.DATA / "35_semantic" / "stg_account_two_sorts.parquet"
        if path.exists():
            path.unlink()


@contextmanager
def f02_bridge_ignores_the_period():
    """The bridge switched off from the period slicer: annual again, beside a YTD headline."""
    base = PAGES.consolidation

    def page():
        pg = base()
        pg.no_filter("sl_period", "layer_bridge",
                     reason="fixture: the bridge reads every month the fact holds")
        return pg
    original = PAGES.PAGES
    PAGES.PAGES = tuple(page if f is base else f for f in original)
    try:
        yield
    finally:
        PAGES.PAGES = original


@contextmanager
def f03_layer_ebitda_plain_sum():
    """Layer EBITDA as a plain sum: the month at MTD, and never the year to date."""
    with _patched_measure("Layer EBITDA", "SUM ( 'Layer Bridge'[ebitda_usd] )"):
        yield


FIXTURES = (
    ("F6B1-01", "One level-2 caption with two sort values in the Account dimension (P6B-D-06)",
     f01_caption_with_two_sorts, "P6B1-HS-01"),
    ("F6B1-02", "The consolidation bridge switched off from the period slicer",
     f02_bridge_ignores_the_period, "P6B1-SC-01"),
    ("F6B1-03", "Layer EBITDA reverted to a plain sum of the bridge fact",
     f03_layer_ebitda_plain_sum, "P6B1-BR-03"),
)

ACTIVE_CON = None


def run(con) -> list[dict]:
    global ACTIVE_CON
    ACTIVE_CON = con
    live, why = dax.available()
    rows = []
    scratch = Path(tempfile.mkdtemp(prefix="northstar-6b1-"))
    try:
        for fid, description, factory, expected in FIXTURES:
            deployed, message = True, ""
            with factory():
                needs_engine = fid != "F6B1-02"
                if needs_engine and live:
                    deployed, message = deploy.deploy(con)
                report_dir = scratch / fid
                BUILD.generate(report_dir)
                res = K1.run(con, report_dir=report_dir, pages=BUILD.build_pages())
            broken = [r["control_id"] for r in res if r["status"] == "FAIL"]
            triggered = ";".join(broken) or "none"
            if expected in broken:
                status = "DETECTED"
                if needs_engine and live and not deployed:
                    triggered += " (and the engine refused to load the model)"
            elif needs_engine and not live:
                status, triggered = "NOT_EXECUTED", why
            elif needs_engine and not deployed:
                status, triggered = "NOT_DEPLOYED", message[:200]
            else:
                status = "MISSED"
            rows.append(dict(fixture_id=fid, description=description,
                             expected_control=expected, status=status,
                             controls_triggered=triggered))
            print(f"  {status:12} {fid}  {description}  -> {expected} [{triggered}]")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        if live:
            deploy.deploy(con)          # leave the clean model behind
    return rows


def write(rows: list[dict]) -> None:
    with open(K1.FAULT_RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str]) -> int:
    con = duckdb.connect(str(C.DUCKDB_PATH))
    rows = run(con)
    con.close()
    if "--no-write" not in argv:
        write(rows)
    detected = sum(r["status"] == "DETECTED" for r in rows)
    print(f"{detected}/{len(rows)} Phase 6B.1 fixtures detected by their intended control")
    return 0 if detected == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
