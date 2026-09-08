"""
Paths, tolerances and the reporting conventions every mart shares.

Nothing here reads data. It exists so that no mart can invent its own idea of what a reporting
basis is, which scenarios are allowed to appear, or how tight a reconciliation has to be.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
DATA = ROOT / "data"
WAREHOUSE = DATA / "20_warehouse"
MARTS_DIR = DATA / "30_marts"
EXPORTS = DATA / "90_exports"

DUCKDB_PATH = WAREHOUSE / "northstar.duckdb"
MANIFEST = DATA / "phase05_manifest.json"
CONTROL_RESULTS = DATA / "phase05_control_results.csv"

#: The two reporting bases, selected upstream at the architecture level (ADR-0003). The marts
#: carry the basis on every row rather than deriving it, so a report cannot pick the wrong one
#: by filtering wrongly.
BASES = ("STATUTORY", "MANAGEMENT")

#: Intercompany account sets. Excluded from every reporting measure, on BOTH sides of every
#: comparison, and this is a presentation rule rather than a second elimination engine:
#:
#:   * on **Actual** the consolidation has already eliminated them, so they sum to nil and
#:     excluding them changes nothing;
#:   * on **Budget and Forecast** there is no consolidation -- the plan is entity-level layer 1
#:     -- so leaving them in would compare a consolidated actual against a plan that still
#:     contains its own internal trade.
#:
#: The sets are the same ones the elimination engine uses (`ref_ic_side`), read from the
#: warehouse rather than restated here.
IC_PREFIX = ("49", "59", "69", "79")

#: Reserved scenarios never appear in a reporting option. `DS` is a stress case the
#: architecture supports and the base dataset does not populate; exposing it as a selectable
#: scenario would offer a reader an empty report that looks like a real one.
RESERVED_SCENARIOS = ("DS",)

#: Prior year is derived, never stored (ADR-0004): the same actual, offset twelve months.
PY_OFFSET_MONTHS = 12

#: Tolerances. A mart against the fact it is derived from is a structural identity and is
#: tested at the cent; nothing here is allowed a "reporting difference".
TOL_MART_USD = 0.05
TOL_RATIO = 0.0005

#: The measure hierarchy, in presentation order. `level` drives indentation in the workbook and
#: `is_subtotal` drives emphasis; `favourable` says which direction is good news, which is what
#: makes variance colouring account-aware instead of "positive is green".
MEASURES: tuple[tuple[str, str, int, bool, str], ...] = (
    ("REVENUE",       "Revenue",                        0, False, "HIGHER"),
    ("COST_OF_SALES", "Cost of sales",                  0, False, "LOWER"),
    ("GROSS_PROFIT",  "Gross profit",                   0, True,  "HIGHER"),
    ("OPEX",          "Operating expenses",             0, False, "LOWER"),
    ("EBITDA",        "EBITDA",                         0, True,  "HIGHER"),
    ("ADDBACKS",      "Approved add-backs",             1, False, "NEUTRAL"),
    ("ADJ_EBITDA",    "Adjusted EBITDA",                0, True,  "HIGHER"),
    ("DA",            "Depreciation and amortisation",  0, False, "LOWER"),
    ("EBIT",          "EBIT",                           0, True,  "HIGHER"),
    ("NET_FINANCE",   "Net finance costs",              0, False, "LOWER"),
    ("TAX",           "Income tax",                     0, False, "LOWER"),
    ("NET_INCOME",    "Net income",                     0, True,  "HIGHER"),
    ("NCI",           "Non-controlling interests",      1, False, "NEUTRAL"),
    ("NI_PARENT",     "Attributable to the parent",     0, True,  "HIGHER"),
)

#: Ratios presented alongside the measures. Held separately because a margin is not additive
#: and must never be summed across periods or entities.
RATIOS: tuple[tuple[str, str, str, str], ...] = (
    ("GROSS_MARGIN_PCT",  "Gross margin %",     "GROSS_PROFIT", "REVENUE"),
    ("EBITDA_MARGIN_PCT", "EBITDA margin %",    "EBITDA",       "REVENUE"),
    ("ADJ_EBITDA_MARGIN_PCT", "Adjusted EBITDA margin %", "ADJ_EBITDA", "REVENUE"),
)

#: The four comparisons management asks for. `base` is what is being assessed and `comparator`
#: is what it is assessed against, so the variance is always base − comparator.
COMPARISONS: tuple[tuple[str, str, str, str], ...] = (
    ("ACT_VS_BUD", "Actual vs Budget",   "ACT", "BUD"),
    ("ACT_VS_FC",  "Actual vs Forecast", "ACT", "FC"),
    ("FC_VS_BUD",  "Forecast vs Budget", "FC",  "BUD"),
    ("ACT_VS_PY",  "Actual vs Prior Year", "ACT", "PY"),
)


def ensure_dirs() -> None:
    for path in (MARTS_DIR, EXPORTS):
        path.mkdir(parents=True, exist_ok=True)


_WRITE_ARTEFACTS = True


def set_artefact_writing(enabled: bool) -> None:
    global _WRITE_ARTEFACTS
    _WRITE_ARTEFACTS = enabled


def writing_artefacts() -> bool:
    return _WRITE_ARTEFACTS
