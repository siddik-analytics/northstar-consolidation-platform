"""
Compare two workbooks cell by cell.

    python tools/workbook_diff.py OLD.xlsx NEW.xlsx

A workbook's bytes move for reasons that have nothing to do with what it says -- a build id
stamped in a property, a zip member reordered, a digest embedded on the lineage sheet. Saying
"the digest changed" is therefore not a finding, and neither is "the digest is the same" a
proof. This walks every sheet and every cell of both files and reports what actually differs,
split into numeric differences (which would be economic drift) and text differences (which
are usually identifiers or stamps).

Run against the cached values, so what is compared is what a reader sees rather than the
formula behind it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import openpyxl


def load(path: Path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = {}
    for ws in wb.worksheets:
        cells = {}
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None:
                    cells[c.coordinate] = c.value
        out[ws.title] = cells
    wb.close()
    return out


def main(argv: list[str]) -> int:
    old, new = load(Path(argv[0])), load(Path(argv[1]))

    only_old = sorted(set(old) - set(new))
    only_new = sorted(set(new) - set(old))
    if only_old or only_new:
        print(f"sheets only in old: {only_old}")
        print(f"sheets only in new: {only_new}")

    numeric_diffs, text_diffs, added, removed = [], [], [], []
    for sheet in sorted(set(old) & set(new)):
        o, n = old[sheet], new[sheet]
        for coord in sorted(set(o) | set(n)):
            a, b = o.get(coord), n.get(coord)
            if a == b:
                continue
            if a is None:
                added.append((sheet, coord, b))
            elif b is None:
                removed.append((sheet, coord, a))
            elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
                numeric_diffs.append((sheet, coord, a, b, abs(a - b)))
            else:
                text_diffs.append((sheet, coord, a, b))

    print(f"sheets compared        : {len(set(old) & set(new))}")
    print(f"cells with a value     : {sum(len(v) for v in new.values()):,}")
    print(f"NUMERIC differences    : {len(numeric_diffs)}")
    print(f"text differences       : {len(text_diffs)}")
    print(f"cells added / removed  : {len(added)} / {len(removed)}")

    if numeric_diffs:
        print("\nNUMERIC DIFFERENCES -- these would be economic drift:")
        for sheet, coord, a, b, d in sorted(numeric_diffs, key=lambda x: -x[4])[:40]:
            print(f"  {sheet:28} {coord:>7}  {a!r:>20} -> {b!r:<20} delta {d:,.6f}")

    if text_diffs:
        print("\ntext differences by sheet:")
        by_sheet: dict[str, int] = {}
        for sheet, *_ in text_diffs:
            by_sheet[sheet] = by_sheet.get(sheet, 0) + 1
        for sheet, count in sorted(by_sheet.items(), key=lambda x: -x[1]):
            print(f"  {sheet:28} {count:>6}")
        print("\n  sample:")
        for sheet, coord, a, b in text_diffs[:12]:
            print(f"  {sheet:24} {coord:>7}  {str(a)[:38]!r:<40} -> {str(b)[:38]!r}")

    print("\nVERDICT:", "NO NUMERIC CHANGE" if not numeric_diffs
          else f"{len(numeric_diffs)} NUMERIC CELLS CHANGED")
    return 1 if numeric_diffs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
