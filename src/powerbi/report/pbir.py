"""
Builders for the Power BI enhanced report format (PBIR).

A PBIR report is a folder of JSON: one `page.json` per page, one `visual.json` per visual,
each written against a published schema. The report is **generated** from declarations, as
the semantic model is, so that a reviewer diffs intent rather than fifteen thousand lines of
JSON, and so that a control can read the same declarations the report is built from.

Every builder here returns plain dicts in the shape Power BI Desktop 2.157 itself writes --
verified by opening the generated project in Desktop, not by reading a schema. The shapes
that matter most:

* a field is `{"Measure": {"Expression": {"SourceRef": {"Entity": T}}, "Property": M}}`
  or the same with `Column`;
* a visual's data roles are `query.queryState.<Role>.projections[]`;
* formatting is `objects.<card>[{"properties": {...}, "selector": ...}]` with every scalar
  wrapped as `{"expr": {"Literal": {"Value": "..."}}}` -- strings quoted with single quotes,
  numbers suffixed `D` (double) or `L` (long), booleans bare;
* a visual-level filter is `filterConfig.filters[]` with a version-2 filter tree.

Nothing here knows what a page says. That is `pages.py`; this is grammar.
"""

from __future__ import annotations

import hashlib
import json
from typing import Iterable

from . import theme as T

VISUAL_SCHEMA = ("https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
                 "visualContainer/2.12.0/schema.json")
PAGE_SCHEMA = ("https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
               "page/2.1.0/schema.json")
PAGES_SCHEMA = ("https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
                "pagesMetadata/1.1.0/schema.json")
REPORT_SCHEMA = ("https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
                 "report/3.3.0/schema.json")
VERSION_SCHEMA = ("https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
                  "versionMetadata/1.0.0/schema.json")

MEASURES_TABLE = None  # set by build.py from config, so this module has no config import


# ---------------------------------------------------------------- expressions
def lit(value) -> dict:
    """A literal in PBIR's expression language."""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, int):
        text = f"{value}L"
    elif isinstance(value, float):
        text = f"{value}D"
    else:
        text = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": text}}}


def colour(hex_colour: str) -> dict:
    return {"solid": {"color": lit(hex_colour)}}


def measure(name: str, table: str | None = None) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table or MEASURES_TABLE}},
                        "Property": name}}


def column(table: str, name: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def hierarchy_level(table: str, hierarchy: str, level: str) -> dict:
    return {"HierarchyLevel": {
        "Expression": {"Hierarchy": {"Expression": {"SourceRef": {"Entity": table}},
                                     "Hierarchy": hierarchy}},
        "Level": level}}


def _query_ref(field: dict) -> str:
    kind = next(iter(field))
    body = field[kind]
    if kind == "HierarchyLevel":
        table = body["Expression"]["Hierarchy"]["Expression"]["SourceRef"]["Entity"]
        return f"{table}.{body['Expression']['Hierarchy']['Hierarchy']}.{body['Level']}"
    table = body["Expression"]["SourceRef"]["Entity"]
    return f"{table}.{body['Property']}"


def projection(field: dict, display_name: str | None = None, active: bool = False,
               fmt: str | None = None) -> dict:
    kind = next(iter(field))
    native = (field[kind]["Property"] if kind != "HierarchyLevel" else field[kind]["Level"])
    out = {"field": field, "queryRef": _query_ref(field), "nativeQueryRef": native}
    if display_name:
        out["displayName"] = display_name
    if active:
        out["active"] = True
    if fmt:
        out["format"] = fmt
    return out


# ---------------------------------------------------------------- filters
def _filter_in(table: str, col: str, values: Iterable, name: str) -> dict:
    return {
        "name": name,
        "field": column(table, col),
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": "f", "Entity": table, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "f"}},
                                            "Property": col}}],
                "Values": [[lit(v)["expr"]] for v in values],
            }}}],
        },
    }


def filters(*specs: tuple[str, str, Iterable], prefix: str = "f") -> dict:
    """
    Visual- or page-level filters: `(table, column, values)` triples.

    Used for what a visual is *about* -- the Actual scenario on a card, one comparison on a
    variance table, one measure line on a bridge. Never for a financial value: a filter on
    `version_code = "ACTUAL"` is a statement of scope, and the number still comes from the
    governed measure.
    """
    out = []
    for i, (table, col, values) in enumerate(specs):
        out.append(_filter_in(table, col, list(values), f"{prefix}{i}"))
    return {"filters": out}


# ---------------------------------------------------------------- objects
def props(**kwargs) -> dict:
    """`{"properties": {...}}` with every scalar wrapped as a literal; dicts pass through."""
    out = {}
    for key, value in kwargs.items():
        out[key] = value if isinstance(value, dict) else lit(value)
    return {"properties": out}


def selector_data(table: str, col: str, value) -> dict:
    return {"selector": {"data": [{"scopeId": {"Comparison": {
        "ComparisonKind": 0,
        "Left": column(table, col),
        "Right": lit(value)["expr"],
    }}}]}}


def title(text: str, size: float | None = None, colour_hex: str = T.NAVY,
          show: bool = True) -> dict:
    return {"title": [props(show=show, text=text,
                            fontColor=colour(colour_hex),
                            fontSize=float(size or T.TYPE["chart_title"]),
                            fontFamily=T.FONT_SEMIBOLD, alignment="left", titleWrap=False)]}


def title_measure(measure_name: str, size: float | None = None) -> dict:
    """A title that reads a governed measure -- the only dynamic text the report uses."""
    return {"title": [{"properties": {
        "show": lit(True),
        "text": {"expr": measure(measure_name)},
        "fontColor": colour(T.NAVY),
        "fontSize": lit(float(size or T.TYPE["chart_title"])),
        "fontFamily": lit(T.FONT_SEMIBOLD),
        "alignment": lit("left"),
    }}]}


def subtitle(text: str) -> dict:
    return {"subTitle": [props(show=True, text=text, fontColor=colour(T.INK_MUTED),
                               fontSize=float(T.TYPE["small"]), fontFamily=T.FONT,
                               alignment="left")]}


def subtitle_measure(measure_name: str) -> dict:
    return {"subTitle": [{"properties": {
        "show": lit(True), "text": {"expr": measure(measure_name)},
        "fontColor": colour(T.INK_MUTED), "fontSize": lit(float(T.TYPE["small"])),
        "fontFamily": lit(T.FONT), "alignment": lit("left")}}]}


# ---------------------------------------------------------------- containers
def _name(page: str, key: str) -> str:
    return f"{page}_{key}"


def container(page: str, key: str, x: int, y: int, w: int, h: int, visual: dict,
              z: int = 0, filter_config: dict | None = None, tab: int | None = None) -> dict:
    out = {
        "$schema": VISUAL_SCHEMA,
        "name": _name(page, key),
        "position": {"x": x, "y": y, "z": z, "width": w, "height": h,
                     "tabOrder": tab if tab is not None else z * 1000},
        "visual": visual,
    }
    if filter_config:
        out["filterConfig"] = filter_config
    return out


def visual(kind: str, roles: dict[str, list[dict]] | None = None, objects: dict | None = None,
           vc_objects: dict | None = None, sort: list[dict] | None = None,
           drill_others: bool = True) -> dict:
    out = {"visualType": kind}
    if roles:
        out["query"] = {"queryState": {role: {"projections": projs}
                                       for role, projs in roles.items()}}
        if sort:
            out["query"]["sortDefinition"] = {"sort": sort, "isDefaultSort": True}
    if objects:
        out["objects"] = objects
    if vc_objects:
        out["visualContainerObjects"] = vc_objects
    out["drillFilterOtherVisuals"] = drill_others
    return out


def sort_by(field: dict, ascending: bool = True) -> list[dict]:
    return [{"field": field, "direction": "Ascending" if ascending else "Descending"}]


# ---------------------------------------------------------------- the visual builders
#: Chrome elements -- text, bands, cards, buttons -- fill their box exactly. Power BI's
#: default 8px visual padding shrinks a 28px button to a 12px one (verified natively).
NO_PADDING = {"properties": {"top": {"expr": {"Literal": {"Value": "0D"}}},
                             "bottom": {"expr": {"Literal": {"Value": "0D"}}},
                             "left": {"expr": {"Literal": {"Value": "0D"}}},
                             "right": {"expr": {"Literal": {"Value": "0D"}}}}}


def textbox(text: str, size: float, colour_hex: str = T.INK, bold: bool = False,
            align: str = "left", family: str | None = None, italic: bool = False) -> dict:
    style = {"fontSize": f"{size}pt", "color": colour_hex,
             "fontFamily": family or (T.FONT_SEMIBOLD if bold else T.FONT)}
    if bold:
        style["fontWeight"] = "bold"
    if italic:
        style["fontStyle"] = "italic"
    runs = [{"value": text, "textStyle": style}]
    return {
        "visualType": "textbox",
        "objects": {"general": [{"properties": {"paragraphs": [
            {"textRuns": runs, "horizontalTextAlignment": align}]}}]},
        "visualContainerObjects": {"background": [props(show=False)],
                                   "border": [props(show=False)],
                                   "padding": [NO_PADDING]},
        "drillFilterOtherVisuals": True,
    }


def paragraphs(lines: list[tuple[str, float, str, bool]], align: str = "left") -> dict:
    """A textbox with several paragraphs: (text, size, colour, bold)."""
    paras = []
    for text, size, colour_hex, bold in lines:
        style = {"fontSize": f"{size}pt", "color": colour_hex,
                 "fontFamily": T.FONT_SEMIBOLD if bold else T.FONT}
        if bold:
            style["fontWeight"] = "bold"
        paras.append({"textRuns": [{"value": text, "textStyle": style}],
                      "horizontalTextAlignment": align})
    return {
        "visualType": "textbox",
        "objects": {"general": [{"properties": {"paragraphs": paras}}]},
        "visualContainerObjects": {"background": [props(show=False)],
                                   "border": [props(show=False)],
                                   "padding": [NO_PADDING]},
        "drillFilterOtherVisuals": True,
    }


def shape(fill_hex: str, kind: str = "rectangle") -> dict:
    """
    A flat band, rule or key square.

    The shape visual's own `fill` renders from the theme's first data colour whatever it is
    told (verified natively, five spellings); its **container background** honours the colour
    exactly and, unlike a textbox, has no minimum height, so a two-pixel rule stays two
    pixels. So the shape is drawn with no fill and the container painted.
    """
    return {
        "visualType": "shape",
        "objects": {
            "shape": [props(tileShape=kind)],
            "fill": [props(show=False)],
            "outline": [props(show=False)],
        },
        "visualContainerObjects": {
            "background": [props(show=True, color=colour(fill_hex), transparency=0.0)],
            "border": [props(show=False)],
            "padding": [NO_PADDING]},
        "drillFilterOtherVisuals": True,
    }


def card(measure_name: str, fmt: str | None = None, value_size: float | None = None,
         value_colour: str = T.NAVY, label: str | None = None, align: str = "left") -> dict:
    """
    A KPI value: the classic card, stripped to the number.

    The label is a textbox beside it and the comparator a second, smaller card, because a
    card that carries its own callout, category and reference labels in the default styling
    is the generic Power BI card this report is not allowed to look like. The new card
    visual clips its value at tile size; the classic one does not (verified natively).
    """
    return {
        "visualType": "card",
        "query": {"queryState": {"Values": {"projections": [
            projection(measure(measure_name), display_name=label or measure_name, fmt=fmt)]}}},
        "objects": {
            # display units "none" and no forced precision: the display format decides
            "labels": [props(fontSize=float(value_size or T.TYPE["kpi_value"]),
                             color=colour(value_colour), fontFamily=T.FONT_SEMIBOLD,
                             labelDisplayUnits=1.0)],
            "categoryLabels": [props(show=False)],
            "wordWrap": [props(show=False)],
        },
        "visualContainerObjects": {"background": [props(show=False)],
                                   "border": [props(show=False)],
                                   "title": [props(show=False)],
                                   "padding": [NO_PADDING]},
        "drillFilterOtherVisuals": True,
    }


def slicer(field: dict, header: str, style: str = "dropdown", single: bool = True,
           default: tuple[str, str, list] | None = None, sync: str | None = None) -> dict:
    """
    `style`: dropdown | tile | list. `default` is (table, column, values): the selection the
    slicer opens with, stored where Desktop stores a slicer's own selection -- under
    `general.filter`, wrapped once (verified natively; a `filterConfig` on a slicer restricts
    its items instead of selecting one). `sync` names the sync group shared across pages.
    """
    mode = {"dropdown": "Dropdown", "tile": "Basic", "list": "Basic"}[style]
    general = [props(orientation=1.0 if style == "tile" else 0.0)] if style != "dropdown" \
        else [props(orientation=0.0)]
    objects = {
        "data": [props(mode=mode)],
        "general": general,
        "header": [props(show=True, text=header, fontColor=colour(T.INK_MUTED),
                         fontSize=float(T.TYPE["small"]), fontFamily=T.FONT_SEMIBOLD)],
        "items": [props(fontColor=colour(T.INK), background=colour(T.WHITE),
                        fontSize=float(T.TYPE["body"]), fontFamily=T.FONT,
                        outline="Frame", outlineColor=colour(T.RULE))],
        "selection": [props(singleSelect=single, selectAllCheckboxEnabled=False)],
    }
    if style == "tile":
        objects["items"] = [props(fontColor=colour(T.INK), background=colour(T.WHITE),
                                  fontSize=float(T.TYPE["body"]), fontFamily=T.FONT,
                                  outline="Frame", outlineColor=colour(T.RULE)),
                            dict(props(fontColor=colour(T.WHITE), background=colour(T.NAVY)),
                                 selector={"id": "selected"})]
    if default:
        table, col, values = default
        objects["general"][0]["properties"]["filter"] = {
            "filter": _filter_in(table, col, values, "d")["filter"]}
    out = {
        "visualType": "slicer",
        "query": {"queryState": {"Values": {"projections": [projection(field, active=True)]}}},
        "objects": objects,
        "visualContainerObjects": {"background": [props(show=False)],
                                   "border": [props(show=False)]},
        "drillFilterOtherVisuals": True,
    }
    if sync:
        out["syncGroup"] = {"groupName": sync, "fieldChanges": True, "filterChanges": True}
    return out


def _axis_objects(units: float | None = None, precision: int | None = None,
                  y_start: float | None = None, y_end: float | None = None) -> dict:
    value_axis = {"show": True, "labelColor": colour(T.INK_MUTED),
                  "fontSize": float(T.TYPE["small"]), "showAxisTitle": False,
                  "gridlineShow": True, "gridlineColor": colour(T.RULE)}
    if units is not None:
        value_axis["labelDisplayUnits"] = units
    if precision is not None:
        value_axis["labelPrecision"] = precision
    if y_start is not None:
        value_axis["start"] = float(y_start)
    if y_end is not None:
        value_axis["end"] = float(y_end)
    return {
        "categoryAxis": [props(show=True, labelColor=colour(T.INK_MUTED),
                               fontSize=float(T.TYPE["small"]), showAxisTitle=False,
                               gridlineShow=False, concatenateLabels=False)],
        "valueAxis": [props(**value_axis)],
    }


def series_colours(kind_table: str, kind_col: str, mapping: dict[str, str]) -> list[dict]:
    """`dataPoint` entries pinning a colour to a series member -- scenario colours."""
    return [dict(props(fill=colour(hex_colour)), **selector_data(kind_table, kind_col, member))
            for member, hex_colour in mapping.items()]


def line_chart(category: dict, values: list[tuple[str, str | None]], title_text: str,
               series: dict | None = None, colours: dict[str, str] | None = None,
               series_table_col: tuple[str, str] | None = None, units: float = 1_000_000.0,
               precision: int = 1, legend: bool = True, y_start: float | None = None,
               y_end: float | None = None, sort_field: dict | None = None,
               subtitle_text: str | None = None, markers: bool = False) -> dict:
    roles = {"Category": [projection(category, active=True)],
             "Y": [projection(measure(m), display_name=d) for m, d in values]}
    if series:
        roles["Series"] = [projection(series)]
    objects = _axis_objects(units, precision, y_start, y_end)
    objects["legend"] = [props(show=legend and (bool(series) or len(values) > 1),
                               position="Top", showTitle=False,
                               labelColor=colour(T.INK_MUTED), fontSize=float(T.TYPE["small"]))]
    objects["lineStyles"] = [props(strokeWidth=2.0, showMarker=markers, lineStyle="solid")]
    if colours and series_table_col:
        objects["dataPoint"] = series_colours(series_table_col[0], series_table_col[1], colours)
    elif colours:
        # colours by measure: selector by metadata queryRef
        objects["dataPoint"] = [dict(props(fill=colour(hex_colour)),
                                     selector={"metadata": _query_ref(measure(m))})
                                for m, hex_colour in colours.items()]
    vc = dict(title(title_text))
    if subtitle_text:
        vc.update(subtitle(subtitle_text))
    return visual("lineChart", roles, objects, vc,
                  sort=sort_by(sort_field or category))


def column_chart(category: dict, values: list[tuple[str, str | None]], title_text: str,
                 series: dict | None = None, colours: dict[str, str] | None = None,
                 series_table_col: tuple[str, str] | None = None,
                 units: float = 1_000_000.0, precision: int = 1, horizontal: bool = False,
                 sort_field: dict | None = None, sort_ascending: bool = True,
                 labels: bool = False, subtitle_text: str | None = None,
                 category_colours: dict[str, str] | None = None,
                 category_table_col: tuple[str, str] | None = None) -> dict:
    roles = {"Category": [projection(category, active=True)],
             "Y": [projection(measure(m), display_name=d) for m, d in values]}
    if series:
        roles["Series"] = [projection(series)]
    objects = _axis_objects(units, precision)
    objects["legend"] = [props(show=bool(series) or len(values) > 1, position="Top",
                               showTitle=False, labelColor=colour(T.INK_MUTED),
                               fontSize=float(T.TYPE["small"]))]
    objects["labels"] = [props(show=labels, color=colour(T.INK_MUTED),
                               fontSize=float(T.TYPE["small"]),
                               labelDisplayUnits=units, labelPrecision=precision)]
    points = []
    if colours and series_table_col:
        points += series_colours(series_table_col[0], series_table_col[1], colours)
    elif colours:
        points += [dict(props(fill=colour(hex_colour)),
                        selector={"metadata": _query_ref(measure(m))})
                   for m, hex_colour in colours.items()]
    if category_colours and category_table_col:
        points += series_colours(category_table_col[0], category_table_col[1],
                                 category_colours)
    if points:
        objects["dataPoint"] = points
    vc = dict(title(title_text))
    if subtitle_text:
        vc.update(subtitle(subtitle_text))
    kind = "barChart" if horizontal else "clusteredColumnChart"
    if horizontal:
        # on a bar chart the value axis is X; swap the axis objects' meaning
        pass
    return visual(kind, roles, objects, vc,
                  sort=sort_by(sort_field or category, sort_ascending))


def combo_chart(category: dict, columns: list[tuple[str, str | None]],
                lines: list[tuple[str, str | None]], title_text: str,
                colours: dict[str, str] | None = None, units: float = 1_000_000.0,
                precision: int = 1, line_units: float | None = None,
                line_precision: int | None = None, subtitle_text: str | None = None) -> dict:
    roles = {"Category": [projection(category, active=True)],
             "Y": [projection(measure(m), display_name=d) for m, d in columns],
             "Y2": [projection(measure(m), display_name=d) for m, d in lines]}
    objects = _axis_objects(units, precision)
    objects["valueAxis"][0]["properties"].update({
        "secShow": lit(True), "secLabelColor": colour(T.INK_MUTED),
        "secFontSize": lit(float(T.TYPE["small"])), "secShowAxisTitle": lit(False),
    })
    if line_units is not None:
        objects["valueAxis"][0]["properties"]["secLabelDisplayUnits"] = lit(line_units)
    if line_precision is not None:
        objects["valueAxis"][0]["properties"]["secLabelPrecision"] = lit(line_precision)
    objects["legend"] = [props(show=True, position="Top", showTitle=False,
                               labelColor=colour(T.INK_MUTED), fontSize=float(T.TYPE["small"]))]
    objects["lineStyles"] = [props(strokeWidth=2.0, showMarker=True, lineStyle="solid")]
    if colours:
        objects["dataPoint"] = [dict(props(fill=colour(hex_colour)),
                                     selector={"metadata": _query_ref(measure(m))})
                                for m, hex_colour in colours.items()]
    vc = dict(title(title_text))
    if subtitle_text:
        vc.update(subtitle(subtitle_text))
    return visual("lineClusteredColumnComboChart", roles, objects, vc, sort=sort_by(category))


def waterfall(category: dict, value: str, title_text: str, increase: str = T.COPPER,
              decrease: str = T.COPPER, total: str = T.NAVY, units: float = 1_000_000.0,
              precision: int = 1, labels: bool = True, subtitle_text: str | None = None,
              sort_field: dict | None = None) -> dict:
    """
    A bridge. Increases and decreases are both copper by default: on this report a bridge
    step is *an adjustment*, a category, and not a judgement -- green and red are for
    favourable and unfavourable, which an EBITDA add-back is not.
    """
    roles = {"Category": [projection(category, active=True)],
             "Y": [projection(measure(value))]}
    objects = _axis_objects(units, precision)
    objects["sentimentColors"] = [props(increaseFill=colour(increase),
                                        decreaseFill=colour(decrease),
                                        totalFill=colour(total))]
    objects["labels"] = [props(show=labels, color=colour(T.INK), fontSize=float(T.TYPE["small"]),
                               labelDisplayUnits=units, labelPrecision=precision)]
    objects["legend"] = [props(show=False)]
    vc = dict(title(title_text))
    if subtitle_text:
        vc.update(subtitle(subtitle_text))
    return visual("waterfallChart", roles, objects, vc, sort=sort_by(sort_field or category))


def matrix(rows: list[dict], values: list[tuple[str, str | None]], title_text: str | None,
           columns: list[dict] | None = None, sort_field: dict | None = None,
           value_formats: dict[str, str] | None = None, stepped: bool = True,
           conditional: list[dict] | None = None, subtotals: bool = False,
           subtitle_text: str | None = None, row_header: str | None = None,
           row_names: dict[str, str] | None = None,
           widths: dict[str, int] | None = None) -> dict:
    roles = {"Rows": [projection(r, active=(i == 0),
                                 display_name=(row_names or {}).get(_query_ref(r)))
                      for i, r in enumerate(rows)],
             "Values": [projection(measure(m), display_name=d,
                                   fmt=(value_formats or {}).get(m))
                        for m, d in values]}
    if columns:
        roles["Columns"] = [projection(c) for c in columns]
    objects = {
        "grid": [props(gridVertical=False, gridHorizontal=True,
                       gridHorizontalColor=colour(T.RULE), gridHorizontalWeight=1,
                       rowPadding=3, outlineColor=colour(T.RULE_STRONG), outlineWeight=1,
                       textSize=float(T.TYPE["body"]))],
        "columnHeaders": [props(fontColor=colour(T.INK), backColor=colour(T.WHITE),
                                fontFamily=T.FONT_SEMIBOLD, fontSize=float(T.TYPE["body"]),
                                alignment="Right", outline="BottomOnly", wordWrap=True)],
        "rowHeaders": [props(fontColor=colour(T.INK), backColor=colour(T.WHITE),
                             fontFamily=T.FONT, fontSize=float(T.TYPE["body"]),
                             outline="None", stepped=stepped, steppedLayoutIndentation=14,
                             showExpandCollapseButtons=stepped,
                             **({"title": row_header} if row_header else {}))],
        "values": [props(fontColorPrimary=colour(T.INK), backColorPrimary=colour(T.WHITE),
                         fontColorSecondary=colour(T.INK), backColorSecondary=colour(T.WHITE),
                         fontFamily=T.FONT, fontSize=float(T.TYPE["body"]), wordWrap=False)],
        "subTotals": [props(rowSubtotals=subtotals, columnSubtotals=False,
                            fontColor=colour(T.NAVY), backColor=colour(T.WHITE),
                            fontFamily=T.FONT_SEMIBOLD, outline="TopOnly")],
        "total": [props(fontColor=colour(T.NAVY), backColor=colour(T.WHITE),
                        fontFamily=T.FONT_SEMIBOLD, outline="TopOnly")],
        "columnWidth": [props(autoSizeColumns=False)]
                       + [dict(props(value=float(w)), selector={"metadata": ref})
                          for ref, w in (widths or {}).items()],
    }
    if conditional:
        objects["values"] = objects["values"] + conditional
    vc = dict(title(title_text)) if title_text else {"title": [props(show=False)]}
    if subtitle_text:
        vc.update(subtitle(subtitle_text))
    return visual("pivotTable", roles, objects, vc,
                  sort=sort_by(sort_field) if sort_field else None)


def table(fields: list[tuple[dict, str | None, str | None]], title_text: str | None,
          sort_field: dict | None = None, ascending: bool = True,
          subtitle_text: str | None = None, totals: bool = False,
          widths: dict[str, int] | None = None) -> dict:
    """`fields`: (field, display name, format)."""
    roles = {"Values": [projection(f, display_name=d, fmt=fmt) for f, d, fmt in fields]}
    objects = {
        "grid": [props(gridVertical=False, gridHorizontal=True,
                       gridHorizontalColor=colour(T.RULE), rowPadding=3,
                       outlineColor=colour(T.RULE_STRONG), textSize=float(T.TYPE["body"]))],
        "columnHeaders": [props(fontColor=colour(T.INK), backColor=colour(T.WHITE),
                                fontFamily=T.FONT_SEMIBOLD, fontSize=float(T.TYPE["body"]),
                                outline="BottomOnly", wordWrap=True)],
        "values": [props(fontColorPrimary=colour(T.INK), backColorPrimary=colour(T.WHITE),
                         fontColorSecondary=colour(T.INK), backColorSecondary=colour(T.WHITE),
                         fontFamily=T.FONT, fontSize=float(T.TYPE["body"]))],
        "total": [props(totals=totals, fontColor=colour(T.NAVY), backColor=colour(T.WHITE),
                        fontFamily=T.FONT_SEMIBOLD, outline="TopOnly")],
        "columnWidth": [props(autoSizeColumns=not widths)]
                       + [dict(props(value=float(w)), selector={"metadata": ref})
                          for ref, w in (widths or {}).items()],
    }
    vc = dict(title(title_text)) if title_text else {"title": [props(show=False)]}
    if subtitle_text:
        vc.update(subtitle(subtitle_text))
    return visual("tableEx", roles, objects, vc,
                  sort=sort_by(sort_field, ascending) if sort_field else None)


def status_colour_rule(measure_name: str, mapping: dict[str, str], target_measure: str) -> dict:
    """
    Font colour on one matrix column driven by a text measure: Favourable green,
    Unfavourable red, everything else ink. The colour is never the only channel -- the
    favourability word itself sits in the next column.
    """
    cases = [{"Condition": {"Comparison": {"ComparisonKind": 0,
                                           "Left": measure(measure_name),
                                           "Right": lit(k)["expr"]}},
              "Value": lit(v)["expr"]} for k, v in mapping.items()]
    return {"properties": {"fontColorPrimary": {"solid": {"color": {"expr": {
        "Conditional": {"Cases": cases, "Else": lit(T.INK)["expr"]}}}}}},
            "selector": {"metadata": _query_ref(measure(target_measure))}}


def nav_button(label: str, page_name: str, active: bool) -> dict:
    """
    One entry of the report's navigation: an action button that goes to a page.

    Built from buttons rather than Desktop's page navigator, whose orientation cannot be
    set from the definition in this build (verified natively, four spellings). Every page
    generates its own rail, so the page you are on is simply the button painted copper --
    the workbook's "start here" mark, made into the active state.
    """
    fill = T.COPPER if active else T.NAVY
    text = props(show=True, text=label, fontColor=colour(T.WHITE),
                 fontSize=float(T.TYPE["body"]),
                 fontFamily=T.FONT_SEMIBOLD if active else T.FONT,
                 horizontalAlignment="left", verticalAlignment="middle", padding=8.0)
    return {
        "visualType": "actionButton",
        "objects": {
            "icon": [props(show=False)],
            "text": [props(show=True), dict(text, selector={"id": "default"}),
                     dict(text, selector={"id": "hover"})],
            "fill": [dict(props(show=True, fillColor=colour(fill), transparency=0.0),
                          selector={"id": "default"}),
                     dict(props(show=True, fillColor=colour(T.COPPER if active else "#2A5A78"),
                                transparency=0.0), selector={"id": "hover"})],
            "outline": [props(show=False)],
            "shape": [props(tileShape="rectangle")],
        },
        "visualContainerObjects": {
            "visualLink": [props(show=True, type="PageNavigation",
                                 navigationSection=page_name)],
            "background": [props(show=False)], "border": [props(show=False)],
            "padding": [NO_PADDING]},
        "drillFilterOtherVisuals": True,
    }


def clear_button(label: str = "Reset filters") -> dict:
    return {
        "visualType": "actionButton",
        "objects": {
            "icon": [props(show=False)],
            "text": [props(show=True),
                     dict(props(text=label, fontColor=colour(T.INK_MUTED),
                                fontSize=float(T.TYPE["small"]), fontFamily=T.FONT,
                                horizontalAlignment="center"), selector={"id": "default"})],
            "fill": [props(show=True, fillColor=colour(T.WHITE), transparency=0.0)],
            "outline": [props(show=True, lineColor=colour(T.RULE), weight=1.0)],
            "shape": [props(tileShape="rectangle")],
        },
        "visualContainerObjects": {
            "visualLink": [props(show=True, type="ClearAllSlicers",
                                 tooltipPlaceholderText="Clear every filter on this page")],
            "background": [props(show=False)], "border": [props(show=False)]},
        "drillFilterOtherVisuals": True,
    }


# ---------------------------------------------------------------- pages and report
def page(name: str, display_name: str, width: int = 1280, height: int = 720,
         page_filters: dict | None = None, hidden: bool = False) -> dict:
    out = {"$schema": PAGE_SCHEMA, "name": name, "displayName": display_name,
           "displayOption": "FitToPage", "height": height, "width": width}
    if hidden:
        out["visibility"] = "HiddenInViewMode"
    if page_filters:
        out["filterConfig"] = page_filters
    return out


def pages_index(order: list[str], active: str) -> dict:
    return {"$schema": PAGES_SCHEMA, "pageOrder": order, "activePageName": active}


def report(theme_file: str) -> dict:
    versions = {"visual": "2.12.0", "page": "2.3.1", "report": "3.4.0"}
    return {
        "$schema": REPORT_SCHEMA,
        "themeCollection": {
            "baseTheme": {"name": "Fluent2-CY26SU08", "reportVersionAtImport": versions,
                          "type": "SharedResources"},
            "customTheme": {"name": theme_file, "type": "RegisteredResources",
                            "reportVersionAtImport": versions},
        },
        "objects": {"section": [props(verticalAlignment="Top")]},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "Fluent2-CY26SU08", "path": "BaseThemes/Fluent2-CY26SU08.json",
                        "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": theme_file, "path": theme_file, "type": "CustomTheme"}]},
        ],
        "settings": {
            "useStylableVisualContainerHeader": True,
            "exportDataMode": "AllowSummarized",
            "defaultDrillFilterOtherVisuals": True,
            "allowChangeFilterTypes": True,
            "useEnhancedTooltips": True,
            "useDefaultAggregateDisplayName": True,
            "isPersistentUserStateDisabled": True,
        },
    }


def version() -> dict:
    return {"$schema": VERSION_SCHEMA, "version": "2.0.0"}


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:8]
