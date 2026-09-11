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
    architecture/ the pipeline diagram (drawn in code, in the palette)
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
    # the top-left of the sheet: title and the two KPI tile bands, the part a reader meets
    # first; the sheet is wide and a full-width panel would shrink past legibility on GitHub
    excel = excel.crop((0, 0, int(excel.width * 0.705), int(excel.height * 0.36)))
    pbi = Image.open(PBI / "01_executive_overview.png").convert("RGB")
    # the report's first two tiers and its middle row
    pbi = pbi.crop((0, 0, pbi.width, int(pbi.height * 0.74)))
    panel_h = 600
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
def build_architecture(controls: int = 677, fixtures: int = 83) -> None:
    """The pipeline as five bands with the control layer beside them, drawn in the palette."""
    W, H = 1600, 1180
    im = Image.new("RGB", (W, H), GROUND)
    d = ImageDraw.Draw(im)
    f_title, f_band, f_sub, f_box, f_note = font(32, True), font(22, True), font(16), font(17, True), font(14)
    d.rectangle((0, 0, W, 8), fill=NAVY)
    d.rectangle((0, 8, 160, 14), fill=COPPER)
    d.text((60, 44), "How the platform is built", fill=NAVY, font=f_title)
    d.text((60, 90), "From three ERP extracts to two reporting artefacts, with controls and lineage as a layer of their own",
           fill=INK_MUTED, font=f_sub)
    left, right = 60, W - 300
    cx = (left + right) // 2

    def band(y, h, title, sub, fill):
        d.rectangle((left, y, right, y + h), fill=fill, outline=RULE)
        d.text((left + 24, y + 18), title, fill=NAVY, font=f_band)
        d.text((left + 24, y + 52), sub, fill=INK_MUTED, font=f_sub)

    def box(x, y, w, h, label, note=None, fill="white", stroke=NAVY):
        d.rectangle((x, y, x + w, y + h), fill=fill, outline=stroke, width=2)
        tw = d.textlength(label, font=f_box)
        d.text((x + (w - tw) / 2, y + (12 if note else (h - 22) / 2)), label, fill=INK, font=f_box)
        if note:
            nw = d.textlength(note, font=f_note)
            d.text((x + (w - nw) / 2, y + 40), note, fill=INK_MUTED, font=f_note)

    def arrow(y0, y1):
        d.line((cx, y0, cx, y1 - 12), fill=NAVY, width=3)
        d.polygon([(cx - 9, y1 - 14), (cx + 9, y1 - 14), (cx, y1)], fill=NAVY)

    y = 140
    band(y, 150, "Source systems",
         "three ERPs, three charts of accounts, three sign conventions  ·  507 native extracts  ·  ~1.1M journal lines", "white")
    bw = (right - left - 48 - 2 * 24) // 3
    for k, (name, note) in enumerate((("Aurora ERP", "US entities · USD"), ("Sable ERP", "European entities · EUR, GBP"),
                                      ("Kestrel ERP", "Canadian entities · CAD"))):
        box(left + 24 + k * (bw + 24), y + 84, bw, 70, name, note)
    arrow(y + 168, y + 200)

    y = 340
    band(y, 150, "Ingestion and harmonisation",
         "one schema, one calendar, one currency table  ·  the group chart of accounts  ·  conformed dimensions", "white")
    bw = (right - left - 48 - 3 * 20) // 4
    for k, name in enumerate(("Parsing", "Standardisation", "COA mapping", "Conformed dimensions")):
        box(left + 24 + k * (bw + 20), y + 84, bw, 52, name)
    arrow(y + 150, y + 184)

    y = 524
    band(y, 170, "Five-layer consolidation",
         "statutory = layers 1 + 2 + 3 + 5  ·  management adds layer 4  ·  every entry a journal with a rule and its evidence", PANEL)
    bw = (right - left - 48 - 4 * 14) // 5
    layers = (("1  Reported", "translated at governed rates"), ("2  IC eliminations", "matched relationship-periods"),
              ("3  Consolidation adj.", "PPA · goodwill · NCI · PUP"), ("4  Management adj.", "approved add-backs"),
              ("5  FX / CTA", "translation to the group currency"))
    for k, (name, note) in enumerate(layers):
        box(left + 24 + k * (bw + 14), y + 84, bw, 70, name, note, stroke=COPPER if k == 3 else NAVY)
    arrow(y + 170, y + 204)

    y = 728
    band(y, 130, "Governed reporting marts",
         "fifteen marts at declared grain  ·  monthly and year to date  ·  variance, covenants, cash flow, working capital, headcount, capex", "white")
    box(left + 24, y + 84, right - left - 48, 34,
        "one authoritative definition per measure  ·  keys and grain declared and proven", fill=PANEL, stroke=RULE)
    arrow(y + 130, y + 164)

    y = 892
    band(y, 170, "Outputs", "the same governed numbers, in the artefact each reader uses", "white")
    bw = (right - left - 48 - 2 * 20) // 3
    outs = (("Excel management reporting", "16 sheets · rendered and reconciled natively"),
            ("Power BI semantic model", "28 tables · 96 measures · PBIP / TMDL"),
            ("Power BI executive report", "10 pages · 43 controls of its own"))
    for k, (name, note) in enumerate(outs):
        box(left + 24 + k * (bw + 20), y + 84, bw, 70, name, note, fill=COPPER_TINT if k == 0 else "white")

    # the cross-cutting layer
    x0 = W - 260
    d.rectangle((x0, 140, W - 60, 1062), fill=NAVY)
    d.rectangle((x0, 140, W - 60, 147), fill=COPPER)
    lines = [("Controls and lineage", True), ("", False), (f"{controls} automated controls", False),
             (f"{fixtures} fault fixtures, each", False), ("caught by the control", False), ("named for it", False),
             ("", False), ("reconciliation across", False), ("every artefact: ledger,", False), ("marts, workbook,", False),
             ("model, rendered page", False), ("", False), ("deterministic builds", False), ("canonical build ids", False),
             ("digests at every layer", False), ("", False), ("a defect register and", False), ("the design lesson", False),
             ("each one taught", False)]
    yy = 190
    for text, bold in lines:
        f = font(19, True) if bold else font(16)
        tw = d.textlength(text, font=f)
        d.text((x0 + (200 - tw) / 2, yy), text, fill="white", font=f)
        yy += 34 if bold else 28
    d.text((60, H - 56), "Northstar Consolidation & Board Reporting Platform  ·  a synthetic environment  ·  every number regenerable from a fixed seed",
           fill=INK_MUTED, font=f_note)
    save(im, OUT / "architecture" / "architecture.png")


def main(argv: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    build_excel()
    build_powerbi()
    build_hero()
    build_architecture()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
