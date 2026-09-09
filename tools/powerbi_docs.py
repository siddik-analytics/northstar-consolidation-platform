"""
Generate the Power BI measure reference from the measure declarations.

    python tools/powerbi_docs.py

`docs/powerbi-measures.md` is written from `src/powerbi/measures.py`, not maintained beside
it. A measure reference kept by hand is a measure reference that is wrong: it drifts the first
time somebody changes an expression and does not think to open the document.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.powerbi import config as C
from src.powerbi.measures import MEASURES, PERIOD_BASIS_ROWS

OUT = ROOT / "docs" / "powerbi-measures.md"

PREAMBLE = f"""# Power BI measures

*Generated from `src/powerbi/measures.py` by `tools/powerbi_docs.py`. Do not edit by hand: a
measure reference maintained beside the code is a measure reference that is wrong the first
time somebody changes an expression and does not think to open the document.*

**{len(MEASURES)} measures** across {len(set(f for _n, _e, _f, f, _d in MEASURES))} display
folders. Every one is declared once, written into TMDL, deployed to Analysis Services and
evaluated there by the `P6-SEM-14` control, and reconciled to the governed marts by `P6-XAR`.

## The rule this layer honours

**Power BI is not a second accounting engine.** EBITDA, the add-back policy, FX translation,
CTA, NCI, PPA, unrealised profit, statutory and management membership, the covenant definition
and the cash-flow classification are settled upstream and arrive on the mart row. What DAX does
here is aggregate a governed column and occasionally divide one by another. Where a measure
looks like it is deciding something, it is selecting something that was decided upstream.

## Two things every statement measure states

**The period basis.** `mart_financial_ytd` publishes three governed columns -- `mtd_usd`,
`ytd_usd`, `fy_usd` -- and a disconnected `Period Basis` table drives which one is read:
{", ".join(f"`{code}` ({name})" for code, name, _o in PERIOD_BASIS_ROWS)}. One slicer, every
statement measure, no hidden machinery.

**The reporting basis.** The same mart publishes *both* bases as separate rows, so a measure
that does not say which one it wants sums both and reports exactly twice the truth. Most lines
follow the reader's selection and default to statutory; `Statutory EBITDA` and
`Management Adjusted EBITDA` are pinned, because a definition that changes when someone moves a
slicer is not a definition.

## Blank is not zero

A measure returns `BLANK()` when the population has not happened -- an Actual month after the
{C.REPORT_PERIOD} close -- and **zero** when a component exists and is nil, which is the Phase
4C rule carried forward. The distinction matters here more than usual: the mart publishes
Actual rows for the whole fiscal year and the four after the close carry `0.00`, so a measure
without the guard reports a company that stopped trading in September.

---
"""


def main() -> int:
    by_folder: dict[str, list] = defaultdict(list)
    for name, expression, fmt, folder, description in MEASURES:
        by_folder[folder].append((name, expression, fmt, description))

    lines = [PREAMBLE]
    for folder in sorted(by_folder):
        lines.append(f"\n## {folder}\n")
        for name, expression, fmt, description in by_folder[folder]:
            lines.append(f"### `{name}`\n")
            lines.append(f"{description}\n")
            if fmt:
                lines.append(f"*Format:* `{fmt}`\n")
            lines.append("```dax")
            lines.append(expression)
            lines.append("```\n")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} ({len(MEASURES)} measures, {len(by_folder)} folders)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
