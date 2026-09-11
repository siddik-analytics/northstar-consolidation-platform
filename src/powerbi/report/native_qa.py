"""
The native pass: the report opened, refreshed and exercised in Power BI Desktop itself.

    python -m src.powerbi.report.native_qa [--out DIR] [--keep]

Nothing here evaluates a measure. Desktop opens the project through its own Open dialog,
refreshes every partition, and the pass then reads what Desktop *rendered* -- the accessible
name of every card ("Revenue 279.0."), the text of every visual that failed, the selected
page tab after each rail button, the cards after a business unit is chosen in the slicer --
and captures each page by PrintWindow. The record it writes (`data/phase06b_native_qa.json`)
carries the report build id (the declarations) and the model's definition digest it was
taken on; `P6B-20…23` and `P6B-25` accept it only while both are the ones on disk. The
project digest is recorded too, but register-derived text on the Controls page changes when
this very pass is written into the register, so it is not the binding.

UI automation runs only when the machine has been idle (`desktop.wait_idle`), and captures
are PrintWindow of Desktop's own window, never the screen.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from .. import config as C
from .. import desktop
from ..measures import MEASURES
from . import layout as L
from .controls import NATIVE_QA

MEASURE_NAMES = sorted((m[0] for m in MEASURES), key=len, reverse=True)

FINAL = C.ROOT / "docs" / "assets" / "phase-06b" / "final"
#: every page, by display name -> file stem (the owner asked for seven; all ten are kept)
WANTED = {
    "01 Executive Overview": "01_executive_overview",
    "02 P&L Performance": "02_pnl_performance",
    "03 Business Units & Entities": "03_business_units_entities",
    "04 Balance Sheet & Working Capital": "04_balance_sheet_working_capital",
    "05 Cash Flow & Liquidity": "05_cash_flow_liquidity",
    "06 EBITDA & Variance Bridge": "06_ebitda_bridge",
    "07 Debt & Covenants": "07_debt_covenants",
    "08 Workforce & CapEx": "08_workforce_capex",
    "09 Consolidation & Controls": "09_consolidation_controls",
    "10 Lineage & Technical": "10_lineage_technical",
}
UNIT = "Industrial Services"


def _win(pid):
    w, _ = desktop.window(pid)
    return w, w.rectangle()


def _settle(pid, rect) -> None:
    """Leave the tab and its tooltip, park the pointer on the collapsed pane strip."""
    from pywinauto import mouse
    from pywinauto.keyboard import send_keys
    time.sleep(0.5)
    send_keys("{ESC}")
    mouse.move(coords=(rect.right - 14, rect.top + 600))
    time.sleep(1.0)
    mouse.move(coords=(rect.right - 12, rect.top + 620))
    time.sleep(3.0)


def cards(pid) -> dict[str, str]:
    """Every card's accessible name, as Desktop rendered it: measure -> displayed value."""
    w, rect = _win(pid)
    out = {}
    for d in w.descendants(control_type="Image"):
        name = d.window_text()
        if not name or d.rectangle().top < rect.top + 300:
            continue
        for measure in MEASURE_NAMES:
            if name.startswith(measure + " ") and name.endswith("."):
                out.setdefault(measure, name[len(measure) + 1:-1])
                break
    return out


def _selected_page(w) -> str | None:
    for t in w.descendants(control_type="TabItem"):
        try:
            text = t.window_text().strip()
            if re.match(r"^\d\d ", text) and t.is_selected():
                return text
        except Exception:
            continue
    return None


def prepare(pid) -> None:
    from pywinauto import mouse
    from pywinauto.keyboard import send_keys
    desktop.report_view(pid)
    w, rect = _win(pid)
    w.set_focus()
    time.sleep(0.5)
    for dx in (1364, 1636, 1910):          # the three pane chevrons, right-anchored
        mouse.click(coords=(rect.left + dx, rect.top + 280))
        time.sleep(1.0)
    send_keys("^{F1}")                      # collapse the ribbon
    time.sleep(1.5)


def unit_test(pid, out_dir: Path) -> dict:
    """Choose one business unit in the slicer, read the cards, put it back."""
    w, rect = _win(pid)
    before = cards(pid)
    combos = [c for c in w.descendants(control_type="ComboBox") if c.window_text() == "bu_name"]
    if not combos:
        return dict(narrowed=False, detail="no business-unit slicer found")
    combos[0].click_input()
    time.sleep(1.5)
    items = [d for d in w.descendants(control_type="ListItem") if d.window_text() == UNIT]
    if not items:
        return dict(narrowed=False, detail=f"{UNIT} not offered")
    items[0].click_input()
    time.sleep(3.5)
    after = cards(pid)
    combos[0].click_input()          # the header toggles the list closed
    time.sleep(1.0)
    _settle(pid, rect)
    desktop.capture_page(out_dir / "01_executive_overview_unit_selected.png", pid)
    # put it back: Ctrl+click clears a single selection
    from pywinauto import mouse
    from pywinauto.keyboard import send_keys
    combos = [c for c in w.descendants(control_type="ComboBox") if c.window_text() == "bu_name"]
    combos[0].click_input()
    time.sleep(1.5)
    items = [d for d in w.descendants(control_type="ListItem") if d.window_text() == UNIT]
    if items:
        r = items[0].rectangle()
        send_keys("{VK_CONTROL down}")
        mouse.click(coords=(r.left + 40, r.top + r.height() // 2))
        send_keys("{VK_CONTROL up}")
        time.sleep(3.0)
    combos = [c for c in w.descendants(control_type="ComboBox") if c.window_text() == "bu_name"]
    if combos:
        combos[0].click_input()
        time.sleep(1.0)
    _settle(pid, rect)
    restored = cards(pid)
    moved = {k: (before.get(k), after.get(k)) for k in before if before.get(k) != after.get(k)}
    held = {k: before.get(k) for k in before if before.get(k) == after.get(k)}
    keys = ("Revenue", "Management Adjusted EBITDA", "Closing FTE")
    return dict(unit=UNIT, before=before, after=after, moved=moved, held=held,
                narrowed=bool(moved) and before.get("Revenue") != after.get("Revenue"),
                reset_ok=all(restored.get(k) == before.get(k) for k in keys),
                restored={k: restored.get(k) for k in keys},
                detail=f"{len(moved)} cards moved, {len(held)} held (Group-level measures)")


def nav_test(pid, tabs: list[str]) -> dict:
    """Press every rail button on the Executive Overview page and read the tab it lands on."""
    from pywinauto import mouse
    from pywinauto.keyboard import send_keys
    results = []
    for target in tabs:
        desktop.goto_page(tabs[0], pid)
        w, rect = _win(pid)
        _settle(pid, rect)
        links = [d for d in w.descendants(control_type="Hyperlink")
                 if "Page navigation" in d.window_text()
                 and d.rectangle().left < rect.left + rect.width() * 0.25]
        links.sort(key=lambda d: d.rectangle().top)
        idx = tabs.index(target)
        if idx >= len(links):
            results.append((target, None))
            continue
        r = links[idx].rectangle()
        send_keys("{VK_CONTROL down}")
        mouse.click(coords=(r.left + 20, r.top + r.height() // 2))
        send_keys("{VK_CONTROL up}")
        landed = None
        for _ in range(8):                  # the heavier pages take a moment to switch
            time.sleep(1.0)
            landed = _selected_page(w)
            if landed == target:
                break
        results.append((target, landed))
    passed = sum(1 for t, s in results if t == s)
    return dict(total=len(tabs), passed=passed, results=results)


def cutoff_test(page_png: Path, out_dir: Path) -> dict:
    """The Actual revenue line on the rendered Executive Overview stops at the close."""
    from PIL import Image
    spec = json.loads((C.REPORT_DIR / "definition" / "pages" / "p01_executive" / "visuals"
                       / "p01_executive_rev_trend" / "visual.json").read_text("utf-8"))["position"]
    im = Image.open(page_png).convert("RGB")
    scale = im.size[0] / L.CANVAS_W
    x0, y0 = int(spec["x"] * scale), int(spec["y"] * scale)
    x1, y1 = int((spec["x"] + spec["width"]) * scale), int((spec["y"] + spec["height"]) * scale)
    im.crop((x0, y0, x1, y1)).save(out_dir / "01_executive_overview_cutoff.png")
    # the plot area: below the title and legend, above the axis labels, right of the axis
    px = im.load()
    left, right = x0 + int(44 * scale), x1 - int(12 * scale)
    top, bottom = y0 + int(84 * scale), y1 - int(46 * scale)
    navy = [x for y in range(top, bottom) for x in range(left, right)
            if abs(px[x, y][0] - 0x1B) < 28 and abs(px[x, y][1] - 0x49) < 28
            and abs(px[x, y][2] - 0x65) < 28]
    if not navy:
        return dict(stops_at_close=False, detail="no Actual line found in the plot area")
    last = max(navy)
    months = 12
    close_index = C.REPORT_PERIOD % 100 - 1
    centre = lambda i: left + (i + 0.5) / months * (right - left)
    close_x, next_x = centre(close_index), centre(close_index + 1)
    stops = last <= (close_x + next_x) / 2 and last >= centre(close_index - 1)
    return dict(stops_at_close=bool(stops), last_actual_px=int(last), close_px=int(close_x),
                next_month_px=int(next_x),
                detail=f"the Actual line ends at x={last}px; {C.REPORT_PERIOD} sits at "
                       f"{close_x:.0f}px and the next month at {next_x:.0f}px")


def run(out_dir: Path | None = None, keep: bool = False) -> dict:
    from .. import run as RUN
    out_dir = out_dir or FINAL
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    opened = desktop.open_project(C.PBIP_DIR / f"{C.PROJECT}.pbip", wait=300)
    record = dict(opened=opened["opened"], refusal=opened.get("refusal", ""),
                  desktop=desktop.version(), project_digest=RUN.project_digest(),
                  report_build_id=RUN.report_build_id(),
                  definition_digest=RUN.definition_digest(), pid=opened.get("pid"))
    if not opened["opened"]:
        record.update(seconds=round(time.time() - t0, 1))
        NATIVE_QA.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return record
    pid = opened["pid"]
    try:
        refreshed = desktop.refresh(pid, wait=600)
        record["refreshed"] = bool(refreshed.get("done"))
        prepare(pid)
        tabs = desktop.page_tabs(pid)
        record["pages"] = tabs
        errors, shots = {}, {}
        for i, name in enumerate(tabs):
            desktop.goto_page(name, pid)
            w, rect = _win(pid)
            _settle(pid, rect)
            errors[name] = desktop.visual_errors(pid)
            path = out_dir / f"{WANTED.get(name, f'{i + 1:02d}')}.png"
            if desktop.capture_page(path, pid):
                shots[name] = str(path.relative_to(C.ROOT)) if C.ROOT in path.parents else str(path)
            if name == tabs[0]:
                record["rendered"] = cards(pid)
        record["visual_errors"] = errors
        record["screenshots"] = shots
        first = out_dir / f"{WANTED[tabs[0]]}.png"
        record["cutoff"] = cutoff_test(first, out_dir)
        desktop.goto_page(tabs[0], pid)
        _settle(pid, _win(pid)[1])
        record["unit_slicer"] = unit_test(pid, out_dir)
        record["navigation"] = nav_test(pid, tabs)
        desktop.goto_page(tabs[0], pid)
    finally:
        record["seconds"] = round(time.time() - t0, 1)
        if not keep:
            desktop.close_instance(pid)
    NATIVE_QA.write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")
    return record


def main(argv: list[str]) -> int:
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else None
    record = run(out, keep="--keep" in argv)
    errors = sum(len(v) for v in record.get("visual_errors", {}).values())
    print(json.dumps({k: record.get(k) for k in ("opened", "refreshed", "desktop", "seconds")}))
    print(f"pages {len(record.get('pages', []))}, visual errors {errors}, "
          f"navigation {record.get('navigation', {}).get('passed')}/{record.get('navigation', {}).get('total')}, "
          f"unit narrowed {record.get('unit_slicer', {}).get('narrowed')}, "
          f"cutoff {record.get('cutoff', {}).get('stops_at_close')}")
    return 0 if record.get("opened") and errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
