"""
Drive Power BI Desktop's own user interface to open a PBIP project, and report what it did.

    python -m src.powerbi.desktop [path/to/project.pbip]

Why this exists
---------------
Phase 6A validated the semantic model by deploying it over TMSL to the Analysis Services
engine that Desktop runs behind itself, and executing real DAX there. That is a genuine
engine test, and it passed. It is also **not** a test of the project on disk: the engine has
no reserved table names and TMSL carries no `///` comments, so a project could be valid in
the engine and refused by Desktop -- which is exactly what happened on the first attempt to
open it (P6B-D-01, P6B-D-02).

Native file-format validation and semantic-engine validation are separate control surfaces.
This module is the first one. It opens the `.pbip` the way a person does -- Desktop's File >
Open dialog, driven through UI Automation -- and reads back either the loaded project's
window title or the text of the dialog Desktop raised instead. `.pbip` has no file
association on this machine and the Store build ignores a command-line argument, so the
dialog is the only native route; it is also the honest one, because it exercises the same
parser a reviewer's double-click would.

What it can and cannot claim
----------------------------
* **Can**: the project parsed, the model schema was accepted, the tables and measures and
  relationships Desktop loaded can be counted through its session database.
* **Cannot**: that every partition refreshed -- a PBIP opens without data and Desktop refreshes
  on request. The engine deployment (`deploy.py`) covers refresh and evaluation; the two are
  run together and reported separately.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import config as C

#: Desktop's window is "Untitled - Power BI Desktop" with nothing open and just the project
#: name once one is loaded, so the window is found by process rather than by title.
PROCESS = "PBIDesktop.exe"
#: The dialogs Desktop raises when it will not open a project, in the order seen.
REFUSALS = ("Issues were found", "Unable to open document")
#: Bars and dialogs that are not refusals and are dismissed without comment.
NOISE = ("Sign in", "What's new")


#: UI automation takes the keyboard and the mouse. It must not do that while a person is
#: using the machine, so every entry point waits for the input devices to have been idle
#: for this long, and gives up -- reporting why -- if they never are.
IDLE_SECONDS = 15
IDLE_WAIT = 600


def idle_seconds() -> float:
    """Seconds since the last keyboard or mouse input, from GetLastInputInfo."""
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0


def wait_idle(min_idle: int = IDLE_SECONDS, max_wait: int = IDLE_WAIT) -> str:
    """Block until the machine has been idle for `min_idle` seconds. Returns "" or a reason."""
    t0 = time.time()
    while time.time() - t0 < max_wait:
        idle = idle_seconds()
        if idle >= min_idle:
            return ""
        time.sleep(min(5, max(1, min_idle - idle)))
    return (f"the machine is in use (input within the last {idle_seconds():.0f}s for "
            f"{max_wait}s); UI automation was not started")


def _pywinauto():
    try:
        from pywinauto import Application, timings  # noqa: F401
        return Application
    except ImportError:
        return None


def version() -> str:
    """The installed Desktop build, from the Store package, or "" when it is not installed."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-AppxPackage -Name Microsoft.MicrosoftPowerBIDesktop | "
         "Select-Object -ExpandProperty Version"],
        capture_output=True, text=True, timeout=60).stdout.strip()
    return out.splitlines()[0] if out else ""


def _pids() -> list[int]:
    """Every running Desktop process id, oldest first."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process PBIDesktop -ErrorAction SilentlyContinue | "
         "Sort-Object StartTime | Select-Object -ExpandProperty Id"],
        capture_output=True, text=True, timeout=30).stdout
    return [int(x) for x in out.split() if x.strip().isdigit()]


def window(pid: int | None = None):
    """The main window of one Desktop process (the oldest by default), or None with a reason."""
    Application = _pywinauto()
    if Application is None:
        return None, "pywinauto is not installed"
    pids = _pids()
    if not pids:
        return None, "Power BI Desktop is not running"
    try:
        app = Application(backend="uia").connect(process=pid or pids[0], timeout=10)
        return app.top_window(), None
    except Exception as exc:                                  # pragma: no cover - environment
        return None, f"could not attach to Power BI Desktop: {exc.__class__.__name__}"


def _dialogs(win) -> list:
    """Top-level modal children of the main window, as (title, wrapper)."""
    out = []
    for child in win.children():
        title = child.window_text()
        # Desktop's modals are Dialogs; its progress windows ("Refresh") are titled Panes.
        # Every untitled child is chrome, so a title is what marks a modal.
        if title:
            out.append((title, child))
    return out


def _dialog_text(dlg) -> str:
    parts = []
    for c in dlg.descendants(control_type="Text"):
        t = c.window_text()
        if t and t not in parts:
            parts.append(t)
    return " | ".join(parts)


def dismiss(win) -> list[str]:
    """Close every refusal or noise dialog that is up. Returns the titles closed."""
    closed = []
    for title, dlg in _dialogs(win):
        if title not in REFUSALS + NOISE:
            continue
        for b in dlg.descendants(control_type="Button"):
            if b.window_text() in ("Close", "Cancel", "OK"):
                b.click_input()
                closed.append(title)
                time.sleep(1)
                break
    return closed


def _launcher():
    """
    The window to press Ctrl+O in.

    A Desktop window with nothing loaded opens the file in place; one with a document loaded
    hands the file to a **new process** and keeps its own title. The blank window is preferred
    so the outcome is read from one place, and the caller is told which case it got.
    """
    for pid in _pids():
        win, _ = window(pid)
        if win is not None and win.window_text().startswith("Untitled"):
            return win, pid, True
    pids = _pids()
    win, _ = window(pids[0]) if pids else (None, None)
    return win, (pids[0] if pids else None), False


def open_project(path, wait: int = 300) -> dict:
    """
    Open a `.pbip` in Desktop through File > Open, and say what happened.

    Returns `opened` (bool), `title`, `refusal` (the text of the dialog Desktop raised, or
    ""), `pid` (the process that holds the result, so a caller can close it), `seconds`, and
    `why` when the attempt could not be made at all -- no Desktop, no pywinauto -- which a
    control reports as NOT_EXECUTED rather than FAIL, because an untested project is not a
    broken one.
    """
    from pywinauto.keyboard import send_keys

    path = os.path.abspath(str(path))
    expected = Path(path).stem
    busy = wait_idle()
    if busy:
        return dict(opened=False, title="", refusal="", pid=None, seconds=0.0, why=busy)
    t0 = time.time()
    win, pid, in_place = _launcher()
    if win is None:
        return dict(opened=False, title="", refusal="", pid=None, seconds=0.0,
                    why="Power BI Desktop is not running")
    before = set(_pids())
    title_before = win.window_text()
    win.set_focus()
    time.sleep(0.5)
    dismiss(win)
    send_keys("^o")
    dlg = None
    for _ in range(20):
        time.sleep(0.5)
        for title, d in _dialogs(win):
            if title == "Open":
                dlg = d
        if dlg is not None:
            break
    if dlg is None:
        return dict(opened=False, title=title_before, refusal="", pid=pid,
                    seconds=round(time.time() - t0, 1),
                    why="Desktop did not show its Open dialog on Ctrl+O")
    edit = next(e for e in dlg.descendants(control_type="Edit")
                if e.window_text() == "File name:")
    edit.set_edit_text(path)
    next(b for b in dlg.descendants(control_type="SplitButton")
         if b.window_text() == "Open").click_input()

    target, target_pid = (win, pid) if in_place else (None, None)
    title = title_before
    while time.time() - t0 < wait:
        time.sleep(3)
        if target is None:
            new = sorted(set(_pids()) - before)
            if new:
                target_pid = new[0]
                target, _ = window(target_pid)
            if target is None:
                continue
        try:
            title = target.window_text()
        except Exception:
            target, _ = window(target_pid)
            title = target.window_text() if target else ""
            if target is None:
                continue
        for dtitle, d in _dialogs(target):
            if dtitle in REFUSALS:
                return dict(opened=False, title=title, refusal=_dialog_text(d),
                            pid=target_pid, seconds=round(time.time() - t0, 1), why="")
        if title.startswith(expected) and (not in_place or title != title_before):
            return dict(opened=True, title=title, refusal="", pid=target_pid,
                        seconds=round(time.time() - t0, 1), why="")
    return dict(opened=False, title=title, refusal="", pid=target_pid,
                seconds=round(time.time() - t0, 1),
                why=f"no result within {wait}s: title still {title!r}")


def close_instance(pid: int, save: bool = False) -> bool:
    """Close one Desktop process without saving, answering its prompt if it asks."""
    from pywinauto.keyboard import send_keys
    if wait_idle():
        return False
    win, _ = window(pid)
    if win is None:
        return False
    win.set_focus()
    time.sleep(0.3)
    dismiss(win)
    send_keys("%{F4}")
    answers = ("Save",) if save else ("Don't save", "Don't Save")
    for _ in range(20):
        time.sleep(1)
        if pid not in _pids():
            return True
        try:
            for title, d in _dialogs(win):
                for b in d.descendants(control_type="Button"):
                    if b.window_text() in answers:
                        b.click_input()
                        break
        except Exception:
            pass
    return pid not in _pids()


def refresh(pid: int | None = None, wait: int = 900) -> dict:
    """
    Home > Refresh > Schema and data, through the ribbon, and wait for Desktop to settle.

    A PBIP opens with no data. This is the native refresh -- Desktop's own Power Query reading
    the partitions the TMDL declares -- and it is what proves the project loads its data, not
    only its schema. Returns `done` and any dialog Desktop raised meanwhile.
    """
    busy = wait_idle()
    if busy:
        return dict(done=False, dialogs={}, why=busy)
    win, why = window(pid)
    if win is None:
        return dict(done=False, dialogs={}, why=why)
    from pywinauto.keyboard import send_keys
    win.set_focus()
    time.sleep(0.5)
    # A project opened in place leaves Desktop's Home pane over the ribbon; Escape closes it.
    send_keys("{ESC}")
    time.sleep(1.5)
    def bars():
        # A dismissed bar stays in the UI Automation tree, hidden; only a visible one counts.
        return sorted({b.window_text().strip() for b in win.descendants(control_type="Text")
                       if ("need to be manually refreshed" in b.window_text()
                           or "incomplete or no data" in b.window_text())
                       and b.is_visible()})

    def press() -> bool:
        buttons = [b for b in win.descendants(control_type="Button")
                   if b.window_text().strip() == "Refresh" and b.is_visible()]
        if not buttons:
            return False
        buttons[0].click_input()
        time.sleep(1.5)
        items = [m for m in win.descendants() if m.window_text().strip() == "Schema and data"
                 and m.is_visible()]
        if items:
            items[0].click_input()
        # else the split button's top half refreshes directly; nothing more to choose
        return True

    t0 = time.time()
    seen: dict[str, str] = {}
    remaining = bars()
    progressed = False
    attempts = 0
    pressed_at = 0.0
    while time.time() - t0 < wait:
        # Desktop occasionally swallows the first press while its Home pane is still
        # settling after an open: with no progress window inside twenty seconds and the
        # "no data" bars still up, press again (three times at most).
        if not progressed and (attempts == 0 or time.time() - pressed_at > 20) and attempts < 3:
            if not press():
                return dict(done=False, dialogs={}, why="no Refresh button on the ribbon")
            attempts += 1
            pressed_at = time.time()
        time.sleep(4)
        dl = _dialogs(win)
        for t, d in dl:
            if t == "Edit Parameters":
                # Desktop asks to confirm the M parameters the first time a copy of the
                # project is refreshed from a new location; the declared value is right.
                for b in d.descendants(control_type="Button"):
                    if b.window_text() == "OK":
                        b.click_input()
                        break
                progressed = True
                continue
            if t == "Refresh":                      # the progress window is not a problem
                progressed = True
                continue
            seen[t] = _dialog_text(d)[:300]
        remaining = bars()
        # done when the progress window has gone and the "no data" bars with it
        if not dl and not remaining and time.time() - pressed_at > 8:
            break
        if seen:
            break
    return dict(done=not remaining and not seen, dialogs=seen, why="; ".join(remaining))


def page_tabs(pid: int | None = None) -> list[str]:
    """The names of the report's page tabs, in order, as Desktop shows them."""
    win, _ = window(pid)
    if win is None:
        return []
    out = []
    for t in win.descendants(control_type="TabItem"):
        name = t.window_text().strip()
        # ribbon tabs and pane tabs are TabItems too; report pages are named "NN Title"
        if re.match(r"^\d\d ", name) and name not in out:
            out.append(name)
    return out


def report_view(pid: int | None = None) -> bool:
    """Switch Desktop to Report view (the page tabs only exist there)."""
    win, _ = window(pid)
    if win is None:
        return False
    for t in win.descendants(control_type="TabItem"):
        if t.window_text().strip() == "Report view":
            t.click_input()
            time.sleep(1.5)
            return True
    return False


def goto_page(name: str, pid: int | None = None) -> bool:
    """Click a page tab by its display name."""
    win, _ = window(pid)
    if win is None:
        return False
    for t in win.descendants(control_type="TabItem"):
        if t.window_text().strip() == name:
            try:
                t.select()
            except Exception:
                t.click_input()
            time.sleep(2.5)
            return True
    return False


def visual_errors(pid: int | None = None) -> list[str]:
    """
    Text Desktop puts on a visual that failed: "Couldn't load the data", "See details",
    "Something's wrong", or the fields-missing message. Empty when every visual rendered.
    """
    win, _ = window(pid)
    if win is None:
        return []
    signs = ("couldn't load", "can't display", "see details", "something's wrong",
             "couldn't retrieve", "fix this", "error")
    ignore = ("copilot",)
    out = []
    for t in win.descendants(control_type="Text"):
        text = t.window_text()
        low = text.lower() if text else ""
        if low and any(sign in low for sign in signs) and not any(i in low for i in ignore)                 and text not in out:
            out.append(text[:160])
    return out


def collapse_panes(pid: int | None = None) -> int:
    """
    Collapse the Filters, Visualizations and Data panes so the canvas gets the width.

    Desktop names every collapse chevron "Collapse"; the three pane headers are the ones
    in the top band of the content area, rightmost first.
    """
    win, _ = window(pid)
    if win is None:
        return 0
    rect = win.rectangle()
    band_top, band_bottom = rect.top + int(rect.height() * 0.20), rect.top + int(rect.height() * 0.30)
    chevrons = []
    for b in win.descendants(control_type="Button"):
        try:
            if b.window_text().strip() == "Collapse" and b.is_visible():
                r = b.rectangle()
                if band_top <= r.top <= band_bottom and r.left > rect.left + rect.width() * 0.5:
                    chevrons.append((r.left, b))
        except Exception:
            pass
    done = 0
    for _, b in sorted(chevrons, key=lambda t: -t[0]):
        try:
            b.click_input()
            done += 1
            time.sleep(0.7)
        except Exception:
            pass
    return done


COPPER_RGB = (0xB0, 0x7A, 0x45)


def capture_page(path: Path | str, pid: int | None = None, mark_px: int = 64,
                 page_size: tuple[int, int] = (1280, 720)) -> bool:
    """
    The report page alone, cropped out of Desktop's window at whatever zoom it is shown.

    Every page has the copper mark at its top-left corner, exactly `mark_px` tall at canvas
    scale. The first copper pixel in the canvas area is the page's origin, the mark's height
    in pixels gives the zoom, and the page is `page_size` scaled from there. No chrome, no
    panes, no page tabs -- and no dependence on what Desktop paints around the page.
    """
    from PIL import Image
    tmp = Path(str(path) + ".full.png")
    if not screenshot(tmp, pid):
        return False
    im = Image.open(tmp).convert("RGB")
    tmp.unlink(missing_ok=True)
    w, h = im.size
    px = im.load()

    def copper(x, y):
        r, g, b = px[x, y]
        return (abs(r - COPPER_RGB[0]) < 12 and abs(g - COPPER_RGB[1]) < 12
                and abs(b - COPPER_RGB[2]) < 12)

    origin = None
    for y in range(int(h * 0.22), int(h * 0.9)):
        for x in range(int(w * 0.03), int(w * 0.6)):
            if copper(x, y) and copper(x + 1, y + 2):
                origin = (x, y)
                break
        if origin:
            break
    if origin is None:
        return False
    x0, y0 = origin

    def navy(x, y):
        r, g, b = px[x, y]
        return abs(r - 0x1B) < 12 and abs(g - 0x49) < 12 and abs(b - 0x65) < 12

    # the rail runs the full page height down the column just inside the mark: copper for
    # the mark, navy to the page's bottom edge -- a run exactly `page_size[1]` tall at scale
    y1 = y0
    while y1 < h - 1 and (copper(x0 + 1, y1 + 1) or navy(x0 + 1, y1 + 1)):
        y1 += 1
    scale = (y1 - y0 + 1) / page_size[1]
    box = (x0, y0, min(w, round(x0 + page_size[0] * scale)),
           min(h, round(y0 + page_size[1] * scale)))
    im.crop(box).save(str(path))
    return True


def screenshot(path: Path | str, pid: int | None = None) -> bool:
    """
    Capture one Desktop window to a PNG, and nothing else.

    Rendered from the window's own handle with `PrintWindow`, not grabbed from the screen:
    a screen grab of the window's rectangle captures whatever is in front of it, which on a
    machine someone is using is their browser, not the report. Returns False if it could not.
    """
    try:
        import ctypes
        import win32gui
        import win32ui
        from PIL import Image

        win, _ = window(pid)
        if win is None:
            return False
        hwnd = win.handle
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width, height = right - left, bottom - top
        if width <= 0 or height <= 0:
            return False
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bmp)
        # PW_RENDERFULLCONTENT: composed windows (Desktop is WebView-hosted) render fully
        ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
        info = bmp.GetInfo()
        image = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]),
                                 bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1)
        win32gui.DeleteObject(bmp.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)
        image.save(str(path))
        return True
    except Exception:                                         # pragma: no cover - environment
        return False


def session_counts(pid: int | None = None) -> dict | None:
    """
    Table, measure and relationship counts from the model Desktop itself loaded.

    Desktop's session database is a GUID beside the TMSL-deployed `NorthstarSemantic*`
    catalog, and it is the one the PBIP was parsed into. Counting there, rather than in the
    deployed catalog, is what makes this a statement about the native project.
    """
    from . import dax
    port = dax.find_port(pid)
    dll = dax._adomd_path()
    if port is None or dll is None:
        return None
    try:
        import clr  # noqa: F401
        from System.Reflection import Assembly
        Assembly.LoadFrom(dll)
        from Microsoft.AnalysisServices.AdomdClient import AdomdConnection
        probe = AdomdConnection(f"Data Source=localhost:{port}")
        probe.Open()
        cmd = probe.CreateCommand()
        cmd.CommandText = "SELECT [CATALOG_NAME] FROM $SYSTEM.DBSCHEMA_CATALOGS"
        reader = cmd.ExecuteReader()
        catalogs = []
        while reader.Read():
            catalogs.append(str(reader.GetValue(0)))
        reader.Close()
        probe.Close()
        session = [c for c in catalogs if "Northstar" not in c]
        if not session:
            return None
        con = AdomdConnection(f"Data Source=localhost:{port};Initial Catalog={session[0]}")
        con.Open()

        def count(expr):
            c = con.CreateCommand()
            c.CommandText = f'EVALUATE ROW ( "n", COUNTROWS ( {expr} ) )'
            r = c.ExecuteReader()
            r.Read()
            v = int(r.GetValue(0) or 0)
            r.Close()
            return v

        def names(expr, col):
            c = con.CreateCommand()
            c.CommandText = f'EVALUATE SELECTCOLUMNS ( {expr}, "n", {col} )'
            r = c.ExecuteReader()
            out = []
            while r.Read():
                out.append(str(r.GetValue(0)))
            r.Close()
            return sorted(out)

        out = dict(catalog=session[0],
                   tables=names("INFO.TABLES ()", "[Name]"),
                   measures=count("INFO.MEASURES ()"),
                   relationships=count("INFO.RELATIONSHIPS ()"),
                   active_relationships=count("FILTER ( INFO.RELATIONSHIPS (), [IsActive] )"))
        con.Close()
        return out
    except Exception:                                         # pragma: no cover - environment
        return None


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    path = args[0] if args else str(C.PBIP_DIR / f"{C.PROJECT}.pbip")
    result = open_project(path)
    for k, v in result.items():
        print(f"  {k:10} {v}")
    if result["opened"] and "--refresh" in argv:
        print("  refresh   ", refresh(result["pid"]))
    if result["opened"]:
        counts = session_counts(result["pid"])
        if counts:
            print(f"  loaded     {len(counts['tables'])} tables, {counts['measures']} measures, "
                  f"{counts['relationships']} relationships "
                  f"({counts['active_relationships']} active) in {counts['catalog']}")
    return 0 if result["opened"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
