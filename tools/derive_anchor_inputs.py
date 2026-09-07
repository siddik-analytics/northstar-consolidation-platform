"""
Derive the three anchor inputs that the source ledgers, not judgement, must supply.

    python tools/derive_anchor_inputs.py [--check]

Phase 1 set the cumulative translation adjustment, the non-controlling interest's share of
it, and the revolver's average drawn balance as economic estimates, because no generated
data existed to compute them from.  Phase 2 produced that data, and Phase 2.2 showed that
two of the three estimates were wrong in a way the source layer could not absorb without a
plug.  They are now derived:

    CTA_MOVEMENT    the translation adjustment the entity ledgers generate under the
                    approved FX policy, plus the retranslation of goodwill and acquired
                    intangibles, less the minority's share and the movement in unrealised
                    intercompany profit          (src/generation/translation.py)

    NCI_FX          20% of the translation adjustment arising in NIG-510, the group's only
                    partly-owned entity

    RCF_AVG_DRAWN   the average DAILY drawn balance from the generated utilisation model,
                    which is what interest and the commitment fee accrue on
                    (src/generation/datasets.py::build_revolver_utilisation)

The three feed back into the anchors -- a higher average drawn balance costs interest,
which reduces retained earnings, which the revolver funds -- so the script iterates to a
fixed point and rewrites the constants in `src/anchors/build_anchors.py` in place.  Run it
whenever a driver that moves foreign net assets or group liquidity changes.

`--check` re-derives without writing and exits non-zero if the committed constants are
stale, which is what `tests/test_phase02_2_corrections.py` and the build gate use.
"""

from __future__ import annotations

import importlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ANCHOR_SRC = ROOT / "src" / "anchors" / "build_anchors.py"

#: A movement is treated as settled once successive iterations agree to USD 500.
TOLERANCE_USD_M = 0.0005
MAX_ITERATIONS = 12


def derive() -> dict[str, dict[str, float]]:
    """Re-import the generator against the anchors on disk and compute the three series."""
    for name in [m for m in list(sys.modules) if m.startswith("src.")]:
        del sys.modules[name]
    series_mod = importlib.import_module("src.generation.series")
    translation = importlib.import_module("src.generation.translation")
    datasets = importlib.import_module("src.generation.datasets")

    sb = series_mod.SeriesBuilder()
    rows = sb.build_actuals()
    cta_rows = translation.cta_by_period(sb, rows)
    group = translation.group_cta_expectation(sb, rows, cta_rows)
    nci = translation.annual_cta_for(cta_rows, "NIG-510")
    nci_share = sb.ent["NIG-510"].nci

    util = datasets.build_revolver_utilisation(sb)
    drawn: dict[int, list[float]] = {}
    for r in util:
        y = r["period_key"] // 100
        acc = drawn.setdefault(y, [0.0, 0.0])
        acc[0] += r["average_daily_drawn"] * r["days_in_month"]
        acc[1] += r["days_in_month"]

    cta = {f"FY{r['fiscal_year']}A": r["derived_group_cta_movement_usd_m"] for r in group}
    return {
        "CTA_MOVEMENT": {**cta, "FY2026B": 0.000, "FY2026F": 1.000},
        "NCI_FX": {f"FY{y}A": nci.get(y, 0.0) * nci_share for y in (2023, 2024, 2025)}
                  | {"FY2026B": 0.000,
                     "FY2026F": round(nci.get(2026, 0.0) * nci_share, 6)},
        "RCF_AVG_DRAWN": {f"FY{y}A": drawn[y][0] / drawn[y][1] / 1e6
                          for y in (2023, 2024, 2025)}
                         | {"FY2026B": 2.000,
                            "FY2026F": drawn[2026][0] / drawn[2026][1] / 1e6},
    }


def committed() -> dict[str, dict[str, float]]:
    for name in [m for m in list(sys.modules) if m.startswith("build_anchors")]:
        del sys.modules[name]
    sys.path.insert(0, str(ROOT / "src" / "anchors"))
    mod = importlib.import_module("build_anchors")
    importlib.reload(mod)
    return {k: dict(getattr(mod, k)) for k in ("CTA_MOVEMENT", "NCI_FX", "RCF_AVG_DRAWN")}


def render(name: str, values: dict[str, float], places: int) -> str:
    body = ", ".join(f"{k}={values[k]:.{places}f}"
                     for k in ("FY2023A", "FY2024A", "FY2025A", "FY2026B", "FY2026F"))
    line = f"{name} = series({body})"
    if len(line) <= 96:
        return line
    head, tail = body.rsplit(", FY2026B=", 1)
    pad = " " * (len(name) + 10)
    return f"{name} = series({head},\n{pad}FY2026B={tail})"


def rewrite(derived: dict[str, dict[str, float]]) -> None:
    text = ANCHOR_SRC.read_text(encoding="utf-8")
    for name, places in (("CTA_MOVEMENT", 6), ("NCI_FX", 6), ("RCF_AVG_DRAWN", 3)):
        pattern = re.compile(rf"^{name} = series\(.*?\)$", re.MULTILINE | re.DOTALL)
        match = re.search(rf"^{name} = series\((?:[^()]|\([^()]*\))*?\)\s*$",
                          text, re.MULTILINE)
        if not match:
            raise SystemExit(f"cannot find the {name} constant in {ANCHOR_SRC}")
        text = text[:match.start()] + render(name, derived[name], places) + \
            text[match.end():]
    ANCHOR_SRC.write_text(text, encoding="utf-8")


def rebuild_anchors() -> None:
    subprocess.run([sys.executable, str(ROOT / "src" / "anchors" / "build_anchors.py")],
                   check=True, capture_output=True)


def differences(a: dict, b: dict) -> float:
    return max(abs(a[k][c] - b[k][c]) for k in a for c in a[k])


def main() -> int:
    check = "--check" in sys.argv
    if check:
        derived = derive()
        current = committed()
        gap = differences(derived, current)
        for name in derived:
            print(f"{name:16} derived {derived[name]}")
            print(f"{'':16} in file {current[name]}")
        print(f"largest difference: {gap:.6f} USD m")
        if gap > TOLERANCE_USD_M:
            print("STALE: run tools/derive_anchor_inputs.py to refresh the anchors")
            return 1
        print("anchor inputs agree with the generated data")
        return 0

    previous = None
    for i in range(1, MAX_ITERATIONS + 1):
        derived = derive()
        if previous is not None and differences(derived, previous) <= TOLERANCE_USD_M:
            print(f"converged after {i} iterations")
            break
        rewrite(derived)
        rebuild_anchors()
        print(f"iteration {i}: " + "  ".join(
            f"{n}={[round(derived[n][c], 4) for c in ('FY2023A', 'FY2024A', 'FY2025A')]}"
            for n in derived))
        previous = derived
    else:
        print("did NOT converge")
        return 1
    for name, values in derived.items():
        print(f"{name}: " + ", ".join(f"{k}={v:.6f}" for k, v in values.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
