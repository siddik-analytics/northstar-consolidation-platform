"""
Pipeline paths, layer names and the canonical conventions every stage shares.

Nothing here reads data.  It exists so that a stage cannot invent its own idea of what a
layer is called, where it writes, or which way a debit points.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
DATA = ROOT / "data"
RAW = DATA / "raw"
REFERENCE = DATA / "reference"
STAGING = DATA / "10_staging"
WAREHOUSE = DATA / "20_warehouse"
EXPORTS = DATA / "90_exports"
FAULTS_DIR = DATA / "faults"

DUCKDB_PATH = WAREHOUSE / "northstar.duckdb"
MANIFEST = DATA / "phase03_manifest.json"
CONTROL_RESULTS = DATA / "phase03_control_results.csv"
EXCEPTIONS = STAGING / "exceptions"

#: The five pipeline layers, in order.  `raw` is the frozen Phase 2 source layer and is
#: never written by this pipeline.
LAYERS = ["raw", "parsed", "standardised", "mapped", "conformed"]
LAYER_DIR = {
    "parsed": STAGING / "01_parsed",
    "standardised": STAGING / "02_standardised",
    "mapped": STAGING / "03_mapped",
    "conformed": STAGING / "04_conformed",
}

ERPS = ["AURORA", "SABLE", "KESTREL"]

#: The canonical financial sign convention, stated once and used by every stage.
#:
#:     signed_local_amount  is DEBIT-POSITIVE.
#:
#: An asset or an expense carries a positive balance; a liability, equity item or revenue
#: carries a negative one.  A trial balance therefore sums to zero.  The convention is a
#: property of the model, not of any source system: each adapter is responsible for
#: recovering it from its own system's conventions, and `standardise` proves it.
SIGN_CONVENTION = "DEBIT_POSITIVE"

#: Group account classes and the sign a normal balance takes under the convention above.
NORMAL_SIGN = {"ASSET": 1, "EXPENSE": 1, "COGS": 1, "LIABILITY": -1, "EQUITY": -1,
               "REVENUE": -1}

#: Kestrel's special periods, and what each one is.  The accounting period keeps the
#: source value; the management reporting period is always December, because a special
#: period is part of the December close and must never appear as a thirteenth month in a
#: management chart.
SPECIAL_PERIODS = {
    13: "STATUTORY_CLOSE",
    14: "AUDIT_ADJUSTMENT",
    15: "TAX_ADJUSTMENT",
    16: "GROUP_REPORTING_ADJUSTMENT",
}

#: Every status a line can end the mapping stage in.  A line always carries exactly one.
MAPPING_STATUS = [
    "MAPPED_DIRECT",          # a one-to-one account mapping, no condition to evaluate
    "MAPPED_MERGE",           # several source accounts collapse into one group account
    "MAPPED_SPLIT",           # a conditional branch of a split rule fired
    "MAPPED_SPLIT_DEFAULT",   # the split's declared default branch fired
    "MAPPED_DERIVED",         # a presentation reclassification (German total-cost method)
    "UNMAPPED_ACCOUNT",       # the source account is not in that ERP's chart
    "UNMAPPED_NO_RULE",       # a split account whose rule set matched nothing
    "AMBIGUOUS",              # more than one non-default rule matched
    "INVALID_DIMENSION",      # a dimension key on the line does not resolve
    "OUT_OF_EFFECT",          # no mapping row effective at the posting date
]

#: Statuses that stop the pipeline.  A line in any of these is an exception, not a result.
BLOCKING_STATUS = {"UNMAPPED_ACCOUNT", "UNMAPPED_NO_RULE", "AMBIGUOUS",
                   "INVALID_DIMENSION", "OUT_OF_EFFECT"}

#: Source fields no downstream calculation may read (CTL-FX-06).  Both are translated
#: amounts produced by the source system's own rate table, and both are preserved in the
#: parsed layer for lineage only.
FORBIDDEN_DOWNSTREAM_FIELDS = {
    "AURORA": "AMOUNT_USD_SYSTEM",
    "KESTREL": "DMBTR_KONZERN_EUR",
}


#: Whether a stage materialises its layer to Parquet. The fault harness turns this off so
#: that running a fault variant through the real pipeline cannot overwrite the clean
#: baseline's staging artefacts -- the stages themselves are unchanged, only the writing is.
_WRITE_ARTEFACTS = True


def set_artefact_writing(enabled: bool) -> None:
    global _WRITE_ARTEFACTS
    _WRITE_ARTEFACTS = enabled


def writing_artefacts() -> bool:
    return _WRITE_ARTEFACTS


def ensure_dirs() -> None:
    for path in (*LAYER_DIR.values(), WAREHOUSE, EXCEPTIONS):
        path.mkdir(parents=True, exist_ok=True)
