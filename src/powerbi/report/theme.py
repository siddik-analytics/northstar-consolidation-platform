"""
The report theme: the approved Excel palette, carried across unchanged.

The Excel style guide (`docs/excel-style-guide.md`) is the visual authority. Every colour here
is one of its named colours, under the same name, with the same meaning:

* navy is the structure and the Actual scenario;
* copper is the secondary accent -- a highlighted element, a reference line, a bridge step,
  the active page -- and the Forecast scenario, exactly as in the workbook;
* the light copper is a wash behind a group, never a data colour;
* green and red are favourable and unfavourable, and nothing else is ever green or red.

`dataColors` is deliberately short. A report that reaches its eighth data colour is a chart
with too many series, and the theme should make that visible rather than accommodate it.
"""

from __future__ import annotations

# ---- the palette, by the Excel style guide's names
NAVY = "#1B4965"
COPPER = "#B07A45"
COPPER_TINT = "#E8D8C8"
INK = "#1F2A37"
INK_MUTED = "#5B6B7B"
RULE = "#D5DBE1"
RULE_STRONG = "#9AA7B4"
PANEL = "#EEF3F7"
ZEBRA = "#F5F8FA"
CANVAS = "#FBFCFD"
WHITE = "#FFFFFF"
BUDGET = "#8C9BAB"
PRIOR = "#B7BFC7"
FAVOURABLE = "#1E7A46"
UNFAVOURABLE = "#B3261E"

#: Scenario colours, identical to the workbook's and to `src/excel/style.py`.
SCENARIO_COLOURS = {
    "Actual": NAVY,
    "Budget": BUDGET,
    "Forecast": COPPER,
    "Prior Year": PRIOR,
}

FONT = "Segoe UI"
FONT_SEMIBOLD = "Segoe UI Semibold"
FONT_LIGHT = "Segoe UI Light"

#: Type scale, in points. Five sizes, used everywhere; nothing in between.
TYPE = {
    "page_title": 18,
    "section": 11,
    "chart_title": 10,
    "body": 9,
    "small": 8,
    "kpi_value": 20,
    "kpi_label": 9,
}


def theme() -> dict:
    """The theme JSON Power BI registers. Visual defaults live here, not on every visual."""
    fill = lambda c: {"solid": {"color": c}}                      # noqa: E731
    return {
        "name": "NorthstarIndustrial.json",
        "dataColors": [NAVY, COPPER, BUDGET, PRIOR, INK_MUTED, RULE_STRONG, COPPER_TINT, RULE],
        "background": WHITE,
        "foreground": INK,
        "tableAccent": NAVY,
        "good": FAVOURABLE,
        "neutral": INK_MUTED,
        "bad": UNFAVOURABLE,
        "maximum": NAVY,
        "center": COPPER_TINT,
        "minimum": PANEL,
        "textClasses": {
            "title": {"fontFace": FONT_SEMIBOLD, "fontSize": TYPE["chart_title"], "color": NAVY},
            "largeTitle": {"fontFace": FONT_SEMIBOLD, "fontSize": TYPE["page_title"],
                           "color": NAVY},
            "header": {"fontFace": FONT_SEMIBOLD, "fontSize": TYPE["section"], "color": NAVY},
            "label": {"fontFace": FONT, "fontSize": TYPE["body"], "color": INK},
            "callout": {"fontFace": FONT_SEMIBOLD, "fontSize": TYPE["kpi_value"], "color": NAVY},
            "lightLabel": {"fontFace": FONT, "fontSize": TYPE["small"], "color": INK_MUTED},
            "boldLabel": {"fontFace": FONT_SEMIBOLD, "fontSize": TYPE["body"], "color": INK},
            "semiboldLabel": {"fontFace": FONT_SEMIBOLD, "fontSize": TYPE["body"],
                              "color": NAVY},
        },
        "visualStyles": {
            "*": {
                "*": {
                    "background": [{"show": True, "color": fill(WHITE), "transparency": 0}],
                    "border": [{"show": False}],
                    "dropShadow": [{"show": False}],
                    "visualHeader": [{"show": False}],
                    "title": [{"show": True, "fontColor": fill(NAVY),
                               "fontSize": TYPE["chart_title"], "fontFamily": FONT_SEMIBOLD,
                               "alignment": "left", "titleWrap": False}],
                    "subTitle": [{"show": False, "fontColor": fill(INK_MUTED),
                                  "fontSize": TYPE["small"], "fontFamily": FONT}],
                    "categoryAxis": [{"show": True, "labelColor": fill(INK_MUTED),
                                      "fontSize": TYPE["small"], "fontFamily": FONT,
                                      "showAxisTitle": False, "gridlineShow": False,
                                      "concatenateLabels": False}],
                    "valueAxis": [{"show": True, "labelColor": fill(INK_MUTED),
                                   "fontSize": TYPE["small"], "fontFamily": FONT,
                                   "showAxisTitle": False, "gridlineShow": True,
                                   "gridlineColor": fill(RULE), "gridlineThickness": 1,
                                   "gridlineStyle": "solid"}],
                    "legend": [{"show": True, "position": "Top", "showTitle": False,
                                "labelColor": fill(INK_MUTED), "fontSize": TYPE["small"],
                                "fontFamily": FONT}],
                    "labels": [{"show": False, "color": fill(INK_MUTED),
                                "fontSize": TYPE["small"], "fontFamily": FONT}],
                    "dataPoint": [{"showAllDataPoints": False}],
                    "wordWrap": [{"show": True}],
                },
            },
            "page": {"*": {"background": [{"color": fill(CANVAS), "transparency": 0}],
                           "outspace": [{"color": fill(PANEL), "transparency": 0}]}},
            "pivotTable": {"*": {
                "grid": [{"gridVertical": False, "gridHorizontal": True,
                          "gridHorizontalColor": fill(RULE), "gridHorizontalWeight": 1,
                          "rowPadding": 3, "outlineColor": fill(RULE_STRONG),
                          "outlineWeight": 1, "textSize": TYPE["body"]}],
                "columnHeaders": [{"fontColor": fill(INK), "backColor": fill(WHITE),
                                   "fontFamily": FONT_SEMIBOLD, "fontSize": TYPE["body"],
                                   "alignment": "Right", "outline": "BottomOnly",
                                   "wordWrap": True}],
                "rowHeaders": [{"fontColor": fill(INK), "backColor": fill(WHITE),
                                "fontFamily": FONT, "fontSize": TYPE["body"],
                                "outline": "None", "stepped": True, "steppedLayoutIndentation": 14,
                                "showExpandCollapseButtons": True}],
                "values": [{"fontColorPrimary": fill(INK), "backColorPrimary": fill(WHITE),
                            "fontColorSecondary": fill(INK), "backColorSecondary": fill(ZEBRA),
                            "fontFamily": FONT, "fontSize": TYPE["body"]}],
                "subTotals": [{"fontColor": fill(NAVY), "backColor": fill(WHITE),
                               "fontFamily": FONT_SEMIBOLD, "fontSize": TYPE["body"],
                               "outline": "TopOnly"}],
                "total": [{"fontColor": fill(NAVY), "backColor": fill(WHITE),
                           "fontFamily": FONT_SEMIBOLD, "fontSize": TYPE["body"],
                           "outline": "TopOnly"}],
            }},
            "tableEx": {"*": {
                "grid": [{"gridVertical": False, "gridHorizontal": True,
                          "gridHorizontalColor": fill(RULE), "rowPadding": 3,
                          "outlineColor": fill(RULE_STRONG), "textSize": TYPE["body"]}],
                "columnHeaders": [{"fontColor": fill(INK), "backColor": fill(WHITE),
                                   "fontFamily": FONT_SEMIBOLD, "fontSize": TYPE["body"],
                                   "outline": "BottomOnly", "wordWrap": True}],
                "values": [{"fontColorPrimary": fill(INK), "backColorPrimary": fill(WHITE),
                            "fontColorSecondary": fill(INK), "backColorSecondary": fill(ZEBRA),
                            "fontFamily": FONT, "fontSize": TYPE["body"]}],
                "total": [{"fontColor": fill(NAVY), "backColor": fill(WHITE),
                           "fontFamily": FONT_SEMIBOLD, "outline": "TopOnly"}],
            }},
            "slicer": {"*": {
                "header": [{"show": True, "fontColor": fill(INK_MUTED),
                            "fontSize": TYPE["small"], "fontFamily": FONT_SEMIBOLD}],
                "items": [{"fontColor": fill(INK), "background": fill(WHITE),
                           "fontSize": TYPE["body"], "fontFamily": FONT,
                           "outline": "Frame", "outlineColor": fill(RULE)}],
                "selection": [{"selectAllCheckboxEnabled": False, "singleSelect": True}],
                "background": [{"show": False}],
            }},
            "cardVisual": {"*": {
                "background": [{"show": False}],
                "title": [{"show": False}],
            }},
            "textbox": {"*": {"background": [{"show": False}]}},
            "actionButton": {"*": {"background": [{"show": False}]}},
            "pageNavigator": {"*": {"background": [{"show": False}]}},
            "shape": {"*": {"background": [{"show": False}]}},
        },
    }
