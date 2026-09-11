"""
The grid every page is laid out on, and the chrome every page shares.

One canvas: 1280 x 720. One rail: a navy band down the left, 176 wide, carrying the brand and
the page navigator -- the report's equivalent of the workbook's Cover navigation, with the
page you are on in copper. One content column: from x = 200 to x = 1256, in which a page
title, a slicer band and the page's own content stack top to bottom on a 16-pixel gutter.

The numbers are constants, and the page builders ask for positions by name (`col(0, 2)`,
`row_y(1)`) rather than typing pixels, so that "consistent margins, padding, card sizes" is
a property of the grid rather than a discipline every page has to keep separately.
"""

from __future__ import annotations

import re

from . import pbir as P
from . import theme as T

CANVAS_W, CANVAS_H = 1280, 720
RAIL_W = 176
X0 = RAIL_W + 24            # first content pixel
X1 = CANVAS_W - 24          # last content pixel
CONTENT_W = X1 - X0         # 1056
GUTTER = 16
#: the density gate: analytical objects (charts, matrices, tables) a page may carry
MAX_ANALYTICAL = 6

TITLE_Y = 14
SUBTITLE_Y = 46
SLICER_Y = 76
SLICER_H = 46
CONTENT_Y = SLICER_Y + SLICER_H + 14   # 136
CONTENT_H = CANVAS_H - CONTENT_Y - 20  # 564

#: The pages, in order: (name, display name). The rail lists them all, on every page.
PAGES = (
    ("p01_executive", "01 Executive Overview"),
    ("p02_pnl", "02 P&L Performance"),
    ("p03_bu", "03 Business Units & Entities"),
    ("p04_balance", "04 Balance Sheet & Working Capital"),
    ("p05_cash", "05 Cash Flow & Liquidity"),
    ("p06_ebitda", "06 EBITDA & Variance Bridge"),
    ("p07_debt", "07 Debt & Covenants"),
    ("p08_workforce", "08 Workforce & CapEx"),
    ("p09_controls", "09 Consolidation & Controls"),
    ("p10_lineage", "10 Lineage & Technical"),
)

#: The slicers every page carries, in order: (key, label, table, column, style, width)
SLICERS = (
    ("sl_period", "Period", "Date", "month_label_long", "dropdown", 132),
    ("sl_basis", "Period basis", "Period Basis", "basis_name", "tile", 232),
    ("sl_rbasis", "Reporting basis", "Reporting Basis", "basis_name", "dropdown", 132),
    ("sl_bu", "Business unit", "Business Unit", "bu_name", "dropdown", 176),
    ("sl_entity", "Entity", "Entity", "entity_name", "dropdown", 208),
)
#: What the slicers say when the report opens: the reporting close, year to date, statutory.
SLICER_DEFAULTS = {
    "sl_period": ("Date", "month_label_long", ["Aug 2026"]),
    "sl_basis": ("Period Basis", "basis_name", ["Year to date"]),
    "sl_rbasis": ("Reporting Basis", "basis_name", ["Statutory"]),
}


def cols(n: int, x0: int = X0, width: int = CONTENT_W, gutter: int = GUTTER) -> list[tuple[int, int]]:
    """`n` equal columns across the content area, as (x, w)."""
    w = (width - gutter * (n - 1)) // n
    return [(x0 + i * (w + gutter), w) for i in range(n)]


def span(columns: list[tuple[int, int]], first: int, last: int) -> tuple[int, int]:
    x = columns[first][0]
    return x, columns[last][0] + columns[last][1] - x


#: The vocabulary of the object inventory. A page is judged on its *analytical* objects --
#: the charts and tables a reader reads -- and on the KPI tiles; the rest is chrome.
KINDS = ("analytical", "kpi", "slicer", "navigation", "text", "shape", "tooltip", "other")

_ANALYTICAL = {"lineChart", "clusteredColumnChart", "barChart", "lineClusteredColumnComboChart",
               "waterfallChart", "pivotTable", "tableEx"}
_CHROME_PREFIXES = ("st", "id", "md", "pq", "cr", "rc", "ch", "rail", "brand", "rp")


def classify(key: str, visual: dict) -> str:
    """What a visual is for, from its type and the key the page gave it."""
    kind = visual.get("visualType", "")
    if kind == "slicer":
        return "slicer"
    if kind == "actionButton":
        return "navigation"
    if kind in _ANALYTICAL:
        return "analytical"
    if kind == "card":
        return "kpi" if not key.startswith(_CHROME_PREFIXES) else "text"
    if kind == "textbox":
        # a tile's label, variance caption or note belongs to the tile it sits on
        tile_part = re.search(r"_(l|n|d|f)$", key) is not None
        return "kpi" if tile_part and not key.startswith(_CHROME_PREFIXES) else "text"
    if kind == "shape":
        return "shape"
    return "other"


class Page:
    """Accumulates visuals for one page and writes them in PBIR order."""

    def __init__(self, name: str, display: str, title: str, subtitle: str,
                 slicers: tuple[str, ...] = tuple(s[0] for s in SLICERS),
                 page_filters: dict | None = None):
        self.name = name
        self.display = display
        self.visuals: list[dict] = []
        self.interactions: list[dict] = []
        #: one reason per NoFilter edge, keyed (source, target) -- `P6B-15` requires it
        self.reasons: dict[tuple[str, str], str] = {}
        #: what each visual is for, keyed by visual name -- the object inventory
        self.kinds: dict[str, str] = {}
        self.page_filters = page_filters
        self._z = 0
        self._chrome(title, subtitle, slicers)

    # ------------------------------------------------------------ primitives
    def add(self, key: str, x: int, y: int, w: int, h: int, visual: dict,
            filters: dict | None = None) -> str:
        self._z += 1
        self.visuals.append(P.container(self.name, key, int(x), int(y), int(w), int(h),
                                        visual, z=self._z, filter_config=filters))
        name = P._name(self.name, key)
        self.kinds[name] = classify(key, visual)
        return name

    def no_filter(self, source_key: str, *target_keys: str, reason: str) -> None:
        """
        Slicer `source` does not filter these visuals. `reason` is mandatory: an interaction
        that is switched off without a stated reason is how a page quietly stops answering
        the slicer, and `P6B-15` fails a NoFilter that has none.
        """
        if not reason or not reason.strip():
            raise ValueError(f"{self.name}: NoFilter from {source_key} needs a reason")
        for target in target_keys:
            source, target_name = P._name(self.name, source_key), P._name(self.name, target)
            self.interactions.append({"source": source, "target": target_name,
                                      "type": "NoFilter"})
            self.reasons[(source, target_name)] = reason.strip()

    def label(self, key: str, x: int, y: int, w: int, text: str, h: int = 18,
              size: float | None = None, colour: str = T.INK_MUTED, bold: bool = True) -> str:
        return self.add(key, x, y, w, h, P.textbox(text, size or T.TYPE["small"], colour, bold))

    def section(self, key: str, x: int, y: int, w: int, text: str,
                right_text: str | None = None) -> int:
        """
        A section header in the workbook's vocabulary: navy text over a navy rule, closed by a
        short copper mark -- the report's version of the section bar with its copper edge.
        Returns the y at which content below it starts.
        """
        self.add(f"{key}_mark", x, y + 4, 4, 14, P.shape(T.COPPER))
        self.add(f"{key}_t", x + 10, y, w - 10 - (200 if right_text else 0), 22,
                 P.textbox(text, T.TYPE["section"], T.NAVY, True))
        if right_text:
            self.add(f"{key}_r", x + w - 200, y + 3, 200, 18,
                     P.textbox(right_text, T.TYPE["small"], T.INK_MUTED, False, align="right"))
        return y + 30

    # ------------------------------------------------------------ chrome
    def _chrome(self, title: str, subtitle: str, slicers: tuple[str, ...]) -> None:
        # the rail: brand, the copper mark, one button per page, the reporting close
        self.add("rail", 0, 0, RAIL_W, CANVAS_H, P.shape(T.NAVY))
        self.add("rail_mark", 0, 0, 6, 64, P.shape(T.COPPER))
        self.add("brand", 18, 16, RAIL_W - 26, 22,
                 P.textbox("NORTHSTAR", 11, T.WHITE, True))
        self.add("brand2", 18, 38, RAIL_W - 26, 18,
                 P.textbox("Industrial Group", T.TYPE["small"], "#C9D6E0", False))
        ny = 84
        for page_name, display in PAGES:
            self.add(f"nav_{page_name}", 8, ny, RAIL_W - 16, 30,
                     P.nav_button(display, page_name, active=(page_name == self.name)))
            ny += 34
        self.add("rail_period_l", 18, CANVAS_H - 66, RAIL_W - 28, 16,
                 P.textbox("Reporting close", T.TYPE["small"], "#C9D6E0", False))
        self.add("rail_period", 14, CANVAS_H - 50, RAIL_W - 24, 30,
                 P.card("Reporting Period", value_size=12.0, value_colour=T.WHITE))
        # the title
        self.add("title", X0, TITLE_Y, CONTENT_W, 30,
                 P.textbox(title, T.TYPE["page_title"], T.NAVY, True))
        self.add("subtitle", X0, SUBTITLE_Y, CONTENT_W, 22,
                 P.textbox(subtitle, T.TYPE["body"], T.INK_MUTED, False))
        # the slicer band
        x = X0
        for key, header, table, col, style, width in SLICERS:
            if key not in slicers:
                continue
            self.add(key, x, SLICER_Y, width, SLICER_H,
                     P.slicer(P.column(table, col), header, style=style,
                              default=SLICER_DEFAULTS.get(key), sync=key))
            x += width + 12

    # ------------------------------------------------------------ output
    def page_json(self) -> dict:
        out = P.page(self.name, self.display, page_filters=self.page_filters)
        if self.interactions:
            out["visualInteractions"] = self.interactions
        return out
