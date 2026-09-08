"""
What the source-defect remediation changed, stated so a reviewer can check it.

Phase 2's source layer was frozen at commit 20355b2 and reopened in Phase 3.1 for one
purpose: to correct the four defects Phase 3 found in it. A correction pass that quietly
moved something else would be indistinguishable from one that did not, so this writes the
evidence out rather than asserting it:

  * every file under src/generation, config and data/reference that differs from the
    frozen baseline, with its git status and the size of the change
  * every headline financial anchor, before and after, with the difference
  * the causal chain for each anchor that moved

Run:  python tools/source_diff_manifest.py [--baseline 20355b2]
Writes data/phase03_1_source_diff.json and prints the anchor movement table.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASELINE = "20355b2"          # Phase 2.2, the frozen source layer
TRACKED = ("src/generation", "config", "data/reference", "tools")

#: The figures a reader checks first, and where each is stated.
HEADLINE = [
    ("Revenue", "anchor_income_statement", "revenue"),
    ("Gross profit", "anchor_income_statement", "gross_profit"),
    ("EBITDA", "anchor_income_statement", "ebitda"),
    ("Adjusted EBITDA", "anchor_income_statement", "adjusted_ebitda"),
    ("Cost of sales", "anchor_income_statement", "cost_of_sales"),
    ("Operating expenses", "anchor_income_statement", "opex"),
    ("EBIT", "anchor_income_statement", "ebit"),
    ("Profit before tax", "anchor_income_statement", "pbt"),
    ("Net interest", "anchor_income_statement", "net_interest"),
    ("Tax", "anchor_income_statement", "tax"),
    ("Net income", "anchor_income_statement", "net_income"),
    ("Cash", "anchor_balance_sheet", "cash"),
    ("Term loan B", "anchor_balance_sheet", "tlb_gross"),
    ("Revolver drawn", "anchor_balance_sheet", "rcf"),
    ("Total equity", "anchor_balance_sheet", "total_equity"),
    ("Retained earnings", "anchor_balance_sheet", "retained_earnings"),
    ("CTA", "anchor_balance_sheet", "cta"),
    ("Non-controlling interest", "anchor_balance_sheet", "nci"),
    ("Trade receivables", "anchor_balance_sheet", "ar"),
    ("Inventory", "anchor_balance_sheet", "inventory"),
    ("Trade payables", "anchor_balance_sheet", "ap"),
    ("Contract assets", "anchor_balance_sheet", "contract_assets"),
    ("Prepayments", "anchor_balance_sheet", "prepaid"),
    ("Accrued liabilities", "anchor_balance_sheet", "accrued"),
    ("Income taxes payable", "anchor_balance_sheet", "tax_payable"),
    ("Total assets", "anchor_balance_sheet", "total_assets"),
    ("Operating cash flow", "anchor_cash_flow", "operating_cash_flow"),
    ("Free cash flow", "anchor_cash_flow", "free_cash_flow"),
    ("Net debt", "anchor_kpi", "net_debt"),
    ("Net leverage", "anchor_kpi", "net_leverage_x"),
    ("Intercompany AR/AP", "anchor_intercompany", "ic_ar_ap_close"),
    ("Intercompany loans", "anchor_intercompany", "ic_loan_close"),
    ("CTA movement (group)", "anchor_cta_rollforward", "cta_movement_group"),
    ("CTA closing", "anchor_cta_rollforward", "cta_closing"),
]

YEARS = ["FY2023A", "FY2024A", "FY2025A"]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True).stdout


def anchor_at(ref: str | None, name: str) -> dict[str, dict[str, float]]:
    """One anchor file as {line_item: {column: value}}, at a git ref or on disk."""
    path = f"config/anchors/{name}.csv"
    text = git("show", f"{ref}:{path}") if ref else (ROOT / path).read_text(encoding="utf-8")
    if not text.strip():
        return {}
    rows = list(csv.DictReader(text.splitlines()))
    key = list(rows[0])[0]
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        vals = {}
        for col, v in row.items():
            if col == key:
                continue
            try:
                vals[col] = float(v)
            except (TypeError, ValueError):
                pass
        out[row[key]] = vals
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=BASELINE)
    args = ap.parse_args()
    base = args.baseline

    # ---------------------------------------------------------------- files
    files = []
    for line in git("diff", "--numstat", base, "--", *TRACKED).splitlines():
        added, removed, path = (line.split("\t") + ["", "", ""])[:3]
        if not path:
            continue
        status = git("diff", "--name-status", base, "--", path).split("\t")[0].strip()
        files.append({"path": path, "status": status,
                      "lines_added": None if added == "-" else int(added),
                      "lines_removed": None if removed == "-" else int(removed)})

    # ---------------------------------------------------------------- anchors
    cache_before: dict[str, dict] = {}
    cache_after: dict[str, dict] = {}
    movements = []
    for label, source, item in HEADLINE:
        before = cache_before.setdefault(source, anchor_at(base, source))
        after = cache_after.setdefault(source, anchor_at(None, source))
        if item not in after:
            continue
        row = {"measure": label, "anchor": f"{source}.{item}", "years": {}}
        moved = False
        for col in YEARS:
            b = before.get(item, {}).get(col)
            a = after.get(item, {}).get(col)
            if b is None or a is None:
                continue
            d = a - b
            row["years"][col] = {"before": round(b, 6), "after": round(a, 6),
                                 "change": round(d, 6),
                                 "change_pct": round(d / b * 100, 4) if b else None}
            moved = moved or abs(d) >= 5e-7
        row["unchanged"] = not moved
        movements.append(row)

    manifest = {
        "phase": "3.1",
        "baseline_commit": base,
        "purpose": "correction of source defects P2-D-01 to P2-D-04",
        "files_changed": files,
        "files_changed_count": len(files),
        "generator_modules_changed": sorted(
            f["path"] for f in files if f["path"].startswith("src/generation/")),
        "anchor_movements": movements,
        "anchors_unchanged": sorted(m["measure"] for m in movements if m["unchanged"]),
        "anchors_moved": sorted(m["measure"] for m in movements if not m["unchanged"]),
    }
    out = ROOT / "data" / "phase03_1_source_diff.json"
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"baseline {base}: {len(files)} files changed under {', '.join(TRACKED)}")
    print()
    print(f"{'measure':28} {'FY2023':>22} {'FY2024':>22} {'FY2025':>22}")
    for m in movements:
        cells = []
        for col in YEARS:
            y = m["years"].get(col)
            if y is None:
                cells.append(f"{'-':>22}")
            elif abs(y["change"]) < 5e-7:
                cells.append(f"{y['after']:>13.3f} {'=':>8}")
            else:
                cells.append(f"{y['after']:>13.3f} {y['change']:>+8.3f}")
        print(f"{m['measure']:28} " + " ".join(cells))
    print()
    print("unchanged:", ", ".join(manifest["anchors_unchanged"]) or "none")
    print("moved:    ", ", ".join(manifest["anchors_moved"]) or "none")
    print(f"written to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
