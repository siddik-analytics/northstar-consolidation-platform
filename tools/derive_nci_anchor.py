"""
Derive the non-controlling interest's share of earnings from the consolidation engine.

Phase 1 set the NCI share of result as a top-down estimate -- 0.18 / 0.28 / 0.36 -- made
before entity-level profitability existed. Phase 4 built the engine that computes it, and the
two disagreed in sign: NIG-510 is loss-making on its own books at the approved transfer price,
so the minority's share of its result is negative (P3-D-07). The owner's decision is that the
generated ledger and the approved transfer-pricing economics are the authority and the Phase 1
estimate is superseded (ADR-0025).

This tool derives the anchor rather than anyone typing it:

    NCI share = (NIG-510's own result + the layer-3 consolidation adjustments attributable
                 to it) x the effective NCI percentage for the period

Intercompany eliminations are excluded from the base. They remove a matched pair and change
group profit by nothing; attributing the buyer's half to the buyer without the seller's half
to the seller would hand NIG-510 its purchases for free.

There is a feedback loop, exactly as there was for CTA in Phase 2.2: the anchor feeds net
income, which feeds retained earnings, which feeds the generated ledgers, which feed the
consolidation that produces the anchor. So this converges rather than computing once.

    python tools/derive_nci_anchor.py            derive, write, and report
    python tools/derive_nci_anchor.py --check    derive and compare, write nothing
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.consol.config import DUCKDB_PATH                       # noqa: E402

ANCHOR_FILE = ROOT / "src" / "anchors" / "build_anchors.py"
COLUMNS = ["FY2023A", "FY2024A", "FY2025A", "FY2026B", "FY2026F"]


def derive() -> dict[str, float]:
    """The NCI share of result per anchor column, in USD millions, from the built engine."""
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    rows = con.execute("""
        SELECT fiscal_year, round(sum(nci_share_usd) / 1e6, 6) AS nci_usd_m
        FROM stg_nci_result GROUP BY 1 ORDER BY 1
    """).fetchall()
    con.close()
    by_year = {int(y): float(v) for y, v in rows}
    out = {f"FY{y}A": by_year.get(y, 0.0) for y in (2023, 2024, 2025)}
    # The planning columns share the fiscal year the forecast covers. FY2026 is eight actual
    # months plus four forecast, so the forecast column takes the whole year and the budget
    # column takes the same figure: budget and forecast are alternative views of one year.
    out["FY2026F"] = by_year.get(2026, 0.0)
    out["FY2026B"] = by_year.get(2026, 0.0)
    return out


def current() -> dict[str, float]:
    text = ANCHOR_FILE.read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if ln.startswith("NCI_INCOME"))
    return {k: float(v) for k, v in re.findall(r"(FY\d{4}[ABF])=(-?[\d.]+)", line)}


def write(values: dict[str, float]) -> None:
    text = ANCHOR_FILE.read_text(encoding="utf-8")
    body = ", ".join(f"{c}={values[c]:.6f}" for c in COLUMNS)
    new = (f"NCI_INCOME = series({body})")
    text = re.sub(r"^NCI_INCOME = series\([^)]*\)", new, text, count=1, flags=re.M)
    ANCHOR_FILE.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    derived, in_file = derive(), current()
    worst = max(abs(derived[c] - in_file.get(c, 0.0)) for c in COLUMNS)
    print("NCI_INCOME derived:", {c: round(derived[c], 6) for c in COLUMNS})
    print("        in file   :", {c: round(in_file.get(c, 0.0), 6) for c in COLUMNS})
    print(f"largest difference: {worst:.6f} USD m")

    if args.check:
        if worst > 5e-4:
            print("STALE: run tools/derive_nci_anchor.py, then rebuild the source layer")
            return 1
        print("the NCI anchor agrees with the consolidation engine")
        return 0

    if worst <= 5e-4:
        print("already converged; nothing written")
        return 0
    write(derived)
    print(f"written to {ANCHOR_FILE.relative_to(ROOT)} -- rebuild the source layer and rerun")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
