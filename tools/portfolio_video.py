"""
Produce the portfolio walkthrough video and the short GitHub preview.

    python tools/portfolio_video.py            record, compose and encode
    python tools/portfolio_video.py --encode   re-encode from the frames already recorded

The video is a project walkthrough, not an advertisement: title cards drawn in the palette,
the workbook's own renders held and slowly framed, and Power BI Desktop captured live
(PrintWindow, never the screen) while the report is used -- a business unit chosen, the
cutoff read, the covenant and consolidation pages visited, the account hierarchy expanded.
Every frame is composed to 1920x1080 on the framing ground with a one-line caption, and
FFmpeg encodes the sequence. The voice-over script is `docs/portfolio/video-script.md`.

Outputs: `docs/assets/portfolio/video/northstar-walkthrough.mp4` and
`docs/assets/portfolio/video/preview.gif`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import portfolio_assets as PA  # noqa: E402

OUT = ROOT / "docs" / "assets" / "portfolio" / "video"
FRAMES = Path(tempfile.gettempdir()) / "northstar_video_frames"
W, H = 1920, 1080
FPS = 10

# ------------------------------------------------------------------ frame composition
class Reel:
    """An ordered list of frames with durations, written as PNGs for FFmpeg's concat demuxer."""

    def __init__(self):
        self.entries: list[tuple[Path, float]] = []
        self.n = 0
        FRAMES.mkdir(parents=True, exist_ok=True)

    def add(self, im: Image.Image, seconds: float) -> None:
        path = FRAMES / f"f{self.n:05d}.png"
        im.save(path)
        self.entries.append((path, seconds))
        self.n += 1

    def write_list(self, path: Path, subset=None) -> None:
        entries = self.entries if subset is None else subset
        lines = ["ffconcat version 1.0"]
        for p, secs in entries:
            lines.append(f"file '{p.as_posix()}'")
            lines.append(f"duration {secs:.3f}")
        lines.append(f"file '{entries[-1][0].as_posix()}'")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @property
    def seconds(self) -> float:
        return sum(s for _, s in self.entries)


def canvas(caption: str | None = None) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (W, H), PA.GROUND)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 8), fill=PA.NAVY)
    d.rectangle((0, 8, 160, 14), fill=PA.COPPER)
    if caption:
        d.text((72, H - 64), caption, fill=PA.INK_MUTED, font=PA.font(24))
    return im, d


def place(im: Image.Image, caption: str, box=(72, 60, W - 72, H - 90), focus=None) -> Image.Image:
    """A picture on the ground, fitted to `box`; `focus` is a fractional crop for a closer look."""
    out, d = canvas(caption)
    if focus:
        fx0, fy0, fx1, fy1 = focus
        im = im.crop((int(im.width * fx0), int(im.height * fy0), int(im.width * fx1), int(im.height * fy1)))
    bw, bh = box[2] - box[0], box[3] - box[1]
    scale = min(bw / im.width, bh / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    x = box[0] + (bw - im.width) // 2
    y = box[1] + (bh - im.height) // 2
    d.rectangle((x - 1, y - 1, x + im.width, y + im.height), outline=PA.RULE, width=1)
    out.paste(im, (x, y))
    return out


def title_card(title: str, lines: list[str], footer: str | None = None) -> Image.Image:
    out, d = canvas()
    d.text((120, 200), title, fill=PA.NAVY, font=PA.font(64, True))
    y = 320
    for line in lines:
        bold = line.startswith("**")
        text = line.strip("*")
        d.text((120, y), text, fill=PA.INK if bold else PA.INK_MUTED, font=PA.font(34, bold))
        y += 58
    if footer:
        d.text((120, H - 120), footer, fill=PA.INK_MUTED, font=PA.font(24))
    return out


def glide(reel: Reel, im: Image.Image, caption: str, seconds: float, start, end, fps: int = FPS) -> None:
    """A slow move from one fractional crop to another -- the only motion a still needs."""
    n = int(seconds * fps)
    for k in range(n):
        t = k / max(1, n - 1)
        t = t * t * (3 - 2 * t)                      # ease in and out
        focus = tuple(a + (b - a) * t for a, b in zip(start, end))
        reel.add(place(im, caption, focus=focus), 1 / fps)


# ------------------------------------------------------------------ the live Power BI segment
def record_powerbi(reel: Reel) -> dict:
    from src.powerbi import config as C, desktop
    from src.powerbi.report import native_qa as N
    from pywinauto import mouse
    from pywinauto.keyboard import send_keys

    tmp = FRAMES / "live"
    tmp.mkdir(exist_ok=True)
    shots = {"n": 0}

    def shot(pid, caption, seconds):
        path = tmp / f"s{shots['n']:04d}.png"
        shots["n"] += 1
        if desktop.capture_page(path, pid):
            reel.add(place(Image.open(path).convert("RGB"), caption), seconds)

    def deselect(pid, rect):
        # a click in the gap between the first-tier tiles and the second-tier band, where
        # no visual sits, drops Desktop's selection of the slicer
        o = _origin(pid)
        if o:
            x0, y0, sc = o
            mouse.click(coords=(rect.left + int(x0 + 700 * sc), rect.top + int(y0 + 231 * sc)))
            time.sleep(1.0)

    r = desktop.open_project(C.PBIP_DIR / f"{C.PROJECT}.pbip", wait=300)
    if not r["opened"]:
        raise SystemExit(f"Desktop did not open the project: {r}")
    pid = r["pid"]
    refreshed = desktop.refresh(pid, wait=600)
    N.prepare(pid)
    w, rect = N._win(pid)
    tabs = desktop.page_tabs(pid)
    cap = "Power BI executive report · "
    try:
        # 01 the overview, read
        desktop.goto_page(tabs[0], pid)
        N._settle(pid, rect)
        shot(pid, cap + "Executive Overview — four first-tier KPIs, the outlook, the unit that needs attention", 9)
        # choose a business unit
        def combo():
            return [c for c in w.descendants(control_type="ComboBox") if c.window_text() == "bu_name"][0]
        combo().expand()
        time.sleep(1.2)
        shot(pid, cap + "the business unit slicer", 1.5)
        items = [d for d in w.descendants(control_type="ListItem") if d.window_text() == N.UNIT]
        items[0].click_input()
        time.sleep(3.0)
        try:
            combo().collapse()
        except Exception:
            pass
        time.sleep(0.8)
        deselect(pid, rect)
        N._settle(pid, rect)
        shot(pid, cap + "Industrial Services selected — revenue, EBITDA and headcount narrow; Group cash and leverage hold", 9)
        # clear it (the header toggles the list; press until the list is actually open)
        combo().expand()
        time.sleep(1.5)
        items = [d for d in w.descendants(control_type="ListItem") if d.window_text() == N.UNIT]
        rr = items[0].rectangle()
        send_keys("{VK_CONTROL down}")
        mouse.click(coords=(rr.left + 40, rr.top + rr.height() // 2))
        send_keys("{VK_CONTROL up}")
        time.sleep(2.5)
        try:
            combo().collapse()
        except Exception:
            pass
        time.sleep(0.8)
        deselect(pid, rect)
        N._settle(pid, rect)
        shot(pid, cap + "back to the Group — the Actual line stops at the August close; budget and forecast carry on", 6)
        # 03 units
        desktop.goto_page("03 Business Units & Entities", pid)
        N._settle(pid, rect)
        shot(pid, cap + "Business Units & Entities — units sum to the Group; each bar coloured by the measure's own favourability", 7)
        # 07 covenants
        desktop.goto_page("07 Debt & Covenants", pid)
        N._settle(pid, rect)
        shot(pid, cap + "Debt & Covenants — Indicative between test dates; a verdict only at a fiscal year end", 9)
        # 06 the three EBITDAs
        desktop.goto_page("06 EBITDA & Variance Bridge", pid)
        N._settle(pid, rect)
        shot(pid, cap + "EBITDA & Variance Bridge — statutory, management and covenant EBITDA kept apart", 6)
        # 09 consolidation
        desktop.goto_page("09 Consolidation & Controls", pid)
        N._settle(pid, rect)
        shot(pid, cap + "Consolidation & Controls — the year-to-date bridge sums to Statutory EBITDA; every count from a register", 10)
        # 02 the P&L, with the hierarchy expanded
        desktop.goto_page("02 P&L Performance", pid)
        N._settle(pid, rect)
        shot(pid, cap + "P&L Performance — the governed statement, variance and favourability from the model", 5)
        # the expanded hierarchy: the native capture taken for the Phase 6B.1 acceptance
        expanded = PA.PBI / "02_pnl_performance_expanded.png"
        if expanded.exists():
            reel.add(place(Image.open(expanded).convert("RGB"),
                           cap + "account detail — Revenue expanded to its sub-captions, in statement order"), 7)
    finally:
        desktop.close_instance(pid)
    return dict(opened=True, refreshed=refreshed.get("done"), frames=shots["n"])


def _origin(pid):
    """The page's origin and scale inside Desktop's window, from the copper mark."""
    from src.powerbi import desktop
    tmp = FRAMES / "_full.png"
    if not desktop.screenshot(tmp, pid):
        return None
    im = Image.open(tmp).convert("RGB")
    px = im.load()
    Wd, Hd = im.size

    def copper(x, y):
        r, g, b = px[x, y]
        return abs(r - 0xB0) < 12 and abs(g - 0x7A) < 12 and abs(b - 0x45) < 12

    def navy(x, y):
        r, g, b = px[x, y]
        return abs(r - 0x1B) < 12 and abs(g - 0x49) < 12 and abs(b - 0x65) < 12

    for y in range(int(Hd * 0.22), int(Hd * 0.9)):
        for x in range(int(Wd * 0.03), int(Wd * 0.6)):
            if copper(x, y) and copper(x + 1, y + 2):
                y1 = y
                while y1 < Hd - 1 and (copper(x + 1, y1 + 1) or navy(x + 1, y1 + 1)):
                    y1 += 1
                return x, y, (y1 - y + 1) / 720
    return None


# ------------------------------------------------------------------ the reel
def build(record: bool = True) -> dict:
    if FRAMES.exists() and record:
        shutil.rmtree(FRAMES)
    reel = Reel()
    marks = {}

    # 0 — what this is
    marks["title"] = reel.seconds
    reel.add(title_card("Northstar Consolidation & Board Reporting Platform", [
        "A synthetic PE-backed industrial group, rebuilt as a finance platform",
        "**12 legal entities · 4 currencies · 3 ERPs · ~$400M revenue · ~1.1M journal lines",
        "ERP extracts → harmonised ledger → five-layer consolidation → governed marts",
        "→ Excel management reporting and a Power BI executive report",
    ], "A project walkthrough · every number regenerable from a fixed seed"), 12)
    arch = Image.open(PA.OUT / "architecture" / "architecture.png").convert("RGB")
    reel.add(place(arch, "How the platform is built — controls and lineage as a layer of their own"), 11)

    # 1 — Excel
    marks["excel"] = reel.seconds
    exec_sheet = PA.excel_sheet("01_Executive_Summary")
    cap = "Excel management reporting · "
    reel.add(place(exec_sheet, cap + "Executive summary — Aug 2026, year to date against budget"), 6)
    glide(reel, exec_sheet, cap + "Executive summary — the KPI tiles, with the governed variance and its direction",
          9, (0.0, 0.0, 1.0, 1.0), (0.0, 0.05, 0.72, 0.40))
    glide(reel, exec_sheet, cap + "Executive summary — what requires management attention, generated by rule",
          5, (0.0, 0.05, 0.72, 0.40), (0.0, 0.55, 0.75, 1.0))
    cash = PA.excel_sheet("06_Cash_Flow")
    reel.add(place(cash, cap + "Consolidated cash flow and liquidity — derived from balance sheet movements, checked every month"), 7)
    debt = PA.excel_sheet("09_Debt_Covenants")
    glide(reel, debt, cap + "Debt and covenant compliance — leverage against a limit read from the agreement",
          8, (0.0, 0.0, 1.0, 1.0), (0.0, 0.18, 0.62, 0.62))
    cons = PA.excel_sheet("13_Consolidation_Controls")
    glide(reel, cons, cap + "Consolidation and control status — five layers, and every phase's controls beside the numbers",
          9, (0.0, 0.0, 1.0, 1.0), (0.0, 0.42, 0.62, 0.95))

    # 2 — Power BI, live
    marks["powerbi"] = reel.seconds
    live = record_powerbi(reel) if record else {}

    # 3 — why the numbers can be trusted
    marks["controls"] = reel.seconds
    reel.add(title_card("Why the numbers can be trusted", [
        "**A model can balance, render and still be wrong.",
        "677 automated controls across eight registers · 83 fault fixtures, each caught by the control named for it",
        "Reconciliation across artefacts: ledger, marts, workbook, semantic model, rendered page",
        "Deterministic builds, canonical build ids, digests at every layer",
        "A defect register, and the design lesson each defect taught",
    ], "github.com — Northstar Consolidation & Board Reporting Platform"), 14)

    return dict(reel=reel, marks=marks, live=live)


def encode(reel: Reel, marks: dict) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    lst = FRAMES / "reel.txt"
    reel.write_list(lst)
    mp4 = OUT / "northstar-walkthrough.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-vf", f"fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "22",
                    "-movflags", "+faststart", str(mp4)], check=True)
    # the preview: the live Power BI segment, small and short
    start = marks["powerbi"]
    end = marks["controls"]
    acc, subset = 0.0, []
    for p, s in reel.entries:
        if start <= acc < end:
            subset.append((p, s))
        acc += s
    plst = FRAMES / "preview.txt"
    reel.write_list(plst, subset)
    gif = OUT / "preview.gif"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(plst),
                    "-vf", "fps=6,scale=900:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3",
                    "-loop", "0", str(gif)], check=True)
    return dict(mp4=str(mp4.relative_to(ROOT)), gif=str(gif.relative_to(ROOT)),
                seconds=round(reel.seconds, 1), mp4_mb=round(mp4.stat().st_size / 1e6, 1),
                gif_mb=round(gif.stat().st_size / 1e6, 1), preview_seconds=round(end - start, 1))


def main(argv: list[str]) -> int:
    result = build(record="--no-record" not in argv)
    info = encode(result["reel"], result["marks"])
    info["live"] = result["live"]
    (OUT / "video.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
