"""
Build the portfolio assets from the final renders: framed screenshots, the hero image and the
architecture diagram.

    python tools/portfolio_assets.py

Inputs are the artefacts the platform already produces -- the workbook's own PDF renders
(`data/90_exports/workbook_render/`, written by `src.excel.qa` from Excel's PDF writer) and
the native Power BI Desktop captures (`docs/assets/phase-06b/final/`). Nothing here touches
a data value: the images are trimmed, scaled and framed, never edited.

Outputs go to `docs/assets/portfolio/`:

    excel/        framed Excel sheets (two-page sheets stacked)
    powerbi/      framed Power BI pages
    architecture/ the pipeline diagram (SVG, hand-drawn in code so it renders on GitHub)
    hero.png      the two-panel Excel + Power BI composition
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "data" / "90_exports" / "workbook_render"
PBI = ROOT / "docs" / "assets" / "phase-06b" / "final"
OUT = ROOT / "docs" / "assets" / "portfolio"

# the approved palette, by name
NAVY = "#1B4965"
COPPER = "#B07A45"
COPPER_TINT = "#E8D8C8"
INK = "#1F2A37"
INK_MUTED = "#5B6B7B"
RULE = "#D5DBE1"
PANEL = "#EEF3F7"
GROUND = "#F4F6F8"          # the framing ground: off-white, a step cooler than the page
FONT = "C:/Windows/Fonts/segoeui.ttf"
FONT_BOLD = "C:/Windows/Fonts/segoeuib.ttf"

PAD = 56
BORDER = RULE
MAX_W = 1800


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


# ------------------------------------------------------------------ primitives
def trim(im: Image.Image, threshold: int = 250, margin: int = 24) -> Image.Image:
    """Cut the white paper away from a render, leaving a small even margin."""
    grey = ImageOps.grayscale(im)
    mask = grey.point(lambda p: 255 if p < threshold else 0)
    box = mask.getbbox()
    if not box:
        return im
    x0, y0, x1, y1 = box
    return im.crop((max(0, x0 - margin), max(0, y0 - margin),
                    min(im.width, x1 + margin), min(im.height, y1 + margin)))


def stack(images: list[Image.Image], gap: int = 24) -> Image.Image:
    """Pages of one sheet, one beneath the other, left-aligned on white."""
    w = max(i.width for i in images)
    h = sum(i.height for i in images) + gap * (len(images) - 1)
    out = Image.new("RGB", (w, h), "white")
    y = 0
    for i in images:
        out.paste(i, (0, y))
        y += i.height + gap
    return out


def frame(im: Image.Image, max_w: int = MAX_W, pad: int = PAD, caption: str | None = None) -> Image.Image:
    """Scale to a common width and set on the ground with an even margin and a hairline."""
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    cap_h = 0
    if caption:
        cap_h = 44
    out = Image.new("RGB", (im.width + 2 * pad, im.height + 2 * pad + cap_h), GROUND)
    d = ImageDraw.Draw(out)
    d.rectangle((pad - 1, pad - 1, pad + im.width, pad + im.height), outline=BORDER, width=1)
    out.paste(im, (pad, pad))
    if caption:
        d.text((pad, pad + im.height + 14), caption, fill=INK_MUTED, font=font(20))
    return out


def save(im: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)
    print(f"  {path.relative_to(ROOT)}  {im.width}x{im.height}")


# ------------------------------------------------------------------ Excel
EXCEL_SHEETS = {
    # stem -> (pages, caption)
    "01_Executive_Summary": (["01_Executive_Summary_p1.png"], "Executive summary — Aug 2026, year to date against budget"),
    "06_Cash_Flow": (["06_Cash_Flow_p1.png", "06_Cash_Flow_p2.png"], "Consolidated cash flow and liquidity"),
    "09_Debt_Covenants": (["09_Debt_&_Covenants_p1.png", "09_Debt_&_Covenants_p2.png"], "Debt and covenant compliance"),
    "13_Consolidation_Controls": (["13_Consolidation_&_Controls_p1.png"], "Consolidation layers and control status"),
    "02_PL": (["02_P&L_p1.png", "02_P&L_p2.png"], "Income statement"),
}


def excel_sheet(stem: str) -> Image.Image:
    pages, _ = EXCEL_SHEETS[stem]
    ims = [trim(Image.open(RENDER / p).convert("RGB")) for p in pages]
    return stack(ims) if len(ims) > 1 else ims[0]


def build_excel() -> None:
    for stem in EXCEL_SHEETS:
        save(frame(excel_sheet(stem)), OUT / "excel" / f"{stem}.png")


# ------------------------------------------------------------------ Power BI
PBI_PAGES = ["01_executive_overview", "02_pnl_performance", "03_business_units_entities",
             "05_cash_flow_liquidity", "06_ebitda_bridge", "07_debt_covenants",
             "09_consolidation_controls", "01_executive_overview_unit_selected"]


def build_powerbi() -> None:
    for stem in PBI_PAGES:
        im = Image.open(PBI / f"{stem}.png").convert("RGB")
        save(frame(im, max_w=1600), OUT / "powerbi" / f"{stem}.png")


# ------------------------------------------------------------------ the hero
def build_hero() -> None:
    """
    Two panels on one ground: the workbook's Executive summary and the report's Executive
    Overview, the same numbers in two artefacts, with the pipeline written beneath.
    """
    excel = excel_sheet("01_Executive_Summary")
    # the top of the sheet: title, KPI tiles and the performance table
    excel = excel.crop((0, 0, excel.width, int(excel.height * 0.50)))
    pbi = Image.open(PBI / "01_executive_overview.png").convert("RGB")
    panel_h = 760
    excel = excel.resize((round(excel.width * panel_h / excel.height), panel_h), Image.LANCZOS)
    pbi = pbi.resize((round(pbi.width * panel_h / pbi.height), panel_h), Image.LANCZOS)
    gap, pad, top, bottom = 40, 72, 150, 130
    w = pad + excel.width + gap + pbi.width + pad
    h = top + panel_h + bottom
    out = Image.new("RGB", (w, h), GROUND)
    d = ImageDraw.Draw(out)
    d.rectangle((0, 0, w, 8), fill=NAVY)
    d.rectangle((0, 8, 160, 14), fill=COPPER)
    d.text((pad, 40), "Northstar Consolidation & Board Reporting Platform", fill=NAVY, font=font(40, True))
    d.text((pad, 96), "Multi-entity consolidation, controls and executive reporting for a synthetic $400M industrial group",
           fill=INK_MUTED, font=font(24))
    x = pad
    for im, label in ((excel, "Excel management reporting · Executive summary"),
                      (pbi, "Power BI executive report · Executive Overview")):
        d.rectangle((x - 1, top - 1, x + im.width, top + im.height), outline=BORDER, width=1)
        out.paste(im, (x, top))
        d.text((x, top + im.height + 16), label, fill=INK_MUTED, font=font(20))
        x += im.width + gap
    chain = ("Aurora · Sable · Kestrel ERP extracts  →  harmonised ledger  →  five-layer consolidation"
             "  →  governed marts  →  Excel · Power BI      controls and lineage at every step")
    d.text((pad, h - 62), chain, fill=INK, font=font(22))
    save(out, OUT / "hero.png")


# ------------------------------------------------------------------ the architecture diagram
def build_architecture() -> None:
    W, H = 1400, 980
    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
                 f'font-family="Segoe UI, Helvetica, Arial, sans-serif">')
    parts.append(f'<rect width="{W}" height="{H}" fill="{GROUND}"/>')

    def band(y, h, title, sub, fill, text=NAVY):
        parts.append(f'<rect x="60" y="{y}" width="{W - 320}" height="{h}" rx="6" fill="{fill}" stroke="{RULE}"/>')
        parts.append(f'<text x="84" y="{y + 30}" font-size="20" font-weight="700" fill="{text}">{title}</text>')
        if sub:
            parts.append(f'<text x="84" y="{y + 54}" font-size="14" fill="{INK_MUTED}">{sub}</text>')

    def box(x, y, w, h, label, note=None, fill="white", stroke=NAVY, text=INK):
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{fill}" stroke="{stroke}"/>')
        parts.append(f'<text x="{x + w / 2}" y="{y + (24 if note else h / 2 + 5)}" text-anchor="middle" '
                     f'font-size="15" font-weight="600" fill="{text}">{label}</text>')
        if note:
            parts.append(f'<text x="{x + w / 2}" y="{y + 44}" text-anchor="middle" font-size="12" fill="{INK_MUTED}">{note}</text>')

    def arrow(y0, y1, x=W / 2 - 130):
        parts.append(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y1 - 10}" stroke="{NAVY}" stroke-width="2"/>')
        parts.append(f'<polygon points="{x - 7},{y1 - 12} {x + 7},{y1 - 12} {x},{y1}" fill="{NAVY}"/>')

    # title
    parts.append(f'<rect x="0" y="0" width="{W}" height="6" fill="{NAVY}"/>')
    parts.append(f'<rect x="0" y="6" width="140" height="5" fill="{COPPER}"/>')
    parts.append(f'<text x="60" y="50" font-size="26" font-weight="700" fill="{NAVY}">How the platform is built</text>')
    parts.append(f'<text x="60" y="76" font-size="15" fill="{INK_MUTED}">From three ERP extracts to two reporting artefacts, with controls and lineage as a layer of their own</text>')

    # 1 sources
    y = 100
    band(y, 118, "Source systems", "three ERPs, three charts of accounts, three sign conventions · 507 native extracts · ~1.1M journal lines", "white")
    bw = 300
    for i, (name, note) in enumerate((("Aurora ERP", "US entities · USD"), ("Sable ERP", "European entities · EUR, GBP"),
                                      ("Kestrel ERP", "Canadian entities · CAD"))):
        box(84 + i * (bw + 30), y + 66, bw, 40, name, None)
        parts.append(f'<text x="{84 + i * (bw + 30) + bw / 2}" y="{y + 108}" text-anchor="middle" font-size="12" fill="{INK_MUTED}">{note}</text>')
    arrow(y + 118, y + 150)

    # 2 processing
    y = 250
    band(y, 118, "Ingestion and harmonisation", "one schema, one calendar, one currency table · group chart of accounts · conformed dimensions", "white")
    bw = 222
    for i, name in enumerate(("Parsing", "Standardisation", "COA mapping", "Conformed dimensions")):
        box(84 + i * (bw + 22), y + 66, bw, 40, name)
    arrow(y + 118, y + 150)

    # 3 consolidation
    y = 400
    band(y, 150, "Five-layer consolidation", "statutory = layers 1 + 2 + 3 + 5 · management adds layer 4 · every entry a journal with a rule and evidence", PANEL)
    bw = 178
    layers = (("1  Reported", "translated at governed rates"), ("2  IC eliminations", "matched relationship-periods"),
              ("3  Consolidation adj.", "PPA · goodwill · NCI · unrealised profit"), ("4  Management adj.", "approved add-backs"),
              ("5  FX / CTA", "translation to the group currency"))
    for i, (name, note) in enumerate(layers):
        box(84 + i * (bw + 12), y + 66, bw, 66, name, note, fill="white", stroke=COPPER if i == 3 else NAVY)
    arrow(y + 150, y + 182)

    # 4 marts
    y = 582
    band(y, 100, "Governed reporting marts", "fifteen marts at declared grain · monthly and year-to-date · variance, covenants, cash flow, working capital, headcount, capex", "white")
    box(84, y + 62, W - 368, 28, "one authoritative definition per measure · keys and grain declared and proven", fill=PANEL, stroke=RULE, text=INK_MUTED)
    arrow(y + 100, y + 132)

    # 5 outputs
    y = 714
    band(y, 150, "Outputs", "the same governed numbers, in the artefact each reader uses", "white")
    bw = 320
    outs = (("Excel management reporting", "16 report sheets · Power Query refresh · rendered and reconciled natively"),
            ("Power BI semantic model", "28 tables · 96 measures · PBIP / TMDL · validated in the engine and in Desktop"),
            ("Power BI executive report", "10 pages · generated from declarations · 43 controls of its own"))
    for i, (name, note) in enumerate(outs):
        box(84 + i * (bw + 22), y + 66, bw, 66, name, note, fill=COPPER_TINT if i == 0 else "white", stroke=NAVY)

    # cross-cutting controls
    x = W - 240
    parts.append(f'<rect x="{x}" y="100" width="180" height="764" rx="6" fill="{NAVY}"/>')
    parts.append(f'<rect x="{x}" y="100" width="180" height="6" fill="{COPPER}"/>')
    lines = ["Controls and", "lineage", "", "677 automated controls", "83 fault fixtures", "reconciliation across", "every artefact",
             "", "deterministic builds", "canonical build ids", "digests at every layer", "", "a defect register", "and the design", "lesson each one", "taught"]
    for i, t in enumerate(lines):
        weight = "700" if i < 2 else "400"
        size = 18 if i < 2 else 14
        parts.append(f'<text x="{x + 90}" y="{150 + i * 30}" text-anchor="middle" font-size="{size}" font-weight="{weight}" fill="white">{t}</text>')

    parts.append(f'<text x="60" y="{H - 40}" font-size="13" fill="{INK_MUTED}">Northstar Consolidation &amp; Board Reporting Platform · a synthetic environment · every number regenerable from a fixed seed</text>')
    parts.append("</svg>")
    path = OUT / "architecture" / "architecture.svg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")
    print(f"  {path.relative_to(ROOT)}")


def main(argv: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    build_excel()
    build_powerbi()
    build_hero()
    build_architecture()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
