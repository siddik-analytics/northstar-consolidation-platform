"""
Execute DAX against the semantic model, in Power BI Desktop.

The `P6-XAR` controls compare what Power BI reports with what the marts hold. That comparison
is only worth anything if the Power BI side is **the real thing** -- the actual DAX, evaluated
by the actual engine, over the actual model. Re-implementing each measure in SQL and comparing
the two would be comparing two things the same person wrote on the same afternoon.

So this connects to the Analysis Services instance that Power BI Desktop starts behind itself
when a project is open, and runs `EVALUATE`. If Desktop is not running, or no model is loaded,
every DAX-dependent control reports `NOT_EXECUTED` and says so. It never falls back to a SQL
re-implementation and calls that a Power BI value.

## Finding the instance

Desktop starts a private `msmdsrv.exe` on an ephemeral port. The Store build does not write
`msmdsrv.port.txt` anywhere findable, so the port is taken from the listening socket of the
process itself, which is what it actually is rather than what a file says it should be.

## The client library

The assembly ships with Desktop as `Microsoft.PowerBI.AdomdClient.dll`, and its types live in
the `Microsoft.AnalysisServices.AdomdClient` namespace -- the file name and the namespace do
not match, and importing the former fails with a bare `ModuleNotFoundError` that suggests the
package is missing when it is not.
"""

from __future__ import annotations

import decimal
import glob
import os
import subprocess
from pathlib import Path

_CONNECTION: object | None = None
_UNAVAILABLE: str | None = None

ADOMD_CANDIDATES = (
    r"C:\Program Files\WindowsApps\Microsoft.MicrosoftPowerBIDesktop_*_x64__8wekyb3d8bbwe"
    r"\bin\Microsoft.PowerBI.AdomdClient.dll",
    r"C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll",
    r"C:\Program Files (x86)\Microsoft Power BI Desktop\bin"
    r"\Microsoft.PowerBI.AdomdClient.dll",
)


def _powershell(script: str) -> str:
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                             capture_output=True, text=True, timeout=90)
        return out.stdout.strip()
    except Exception:
        return ""


def find_port() -> int | None:
    """The port Desktop's own Analysis Services instance is listening on."""
    raw = _powershell(
        "$p = Get-Process msmdsrv -ErrorAction SilentlyContinue; "
        "if ($p) { Get-NetTCPConnection -State Listen -OwningProcess $p.Id "
        "-ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty LocalPort }")
    digits = "".join(c for c in raw.splitlines()[0] if c.isdigit()) if raw else ""
    return int(digits) if digits else None


def _adomd_path() -> str | None:
    """
    Locate the ADOMD assembly.

    The Store build lives under `C:\\Program Files\\WindowsApps`, which denies directory
    *enumeration* to a normal user while still permitting a direct open. So a glob finds
    nothing and reports the DLL missing when it is sitting right there -- the install location
    has to be asked for by name and the exact path tested, never searched for.
    """
    install = _powershell(
        "(Get-AppxPackage -Name 'Microsoft.MicrosoftPowerBIDesktop'"
        " -ErrorAction SilentlyContinue).InstallLocation")
    if install:
        candidate = os.path.join(install.splitlines()[0].strip(), "bin",
                                 "Microsoft.PowerBI.AdomdClient.dll")
        if os.path.exists(candidate):
            return candidate

    for pattern in ADOMD_CANDIDATES:
        if "*" in pattern:
            try:
                hits = sorted(glob.glob(pattern), reverse=True)
            except OSError:
                hits = []
            for hit in hits:
                if os.path.exists(hit):
                    return hit
        elif os.path.exists(pattern):
            return pattern
    return None


def connect() -> tuple[object | None, str | None]:
    """Returns (connection, reason_unavailable). Cached; safe to call repeatedly."""
    global _CONNECTION, _UNAVAILABLE
    if _CONNECTION is not None or _UNAVAILABLE is not None:
        return _CONNECTION, _UNAVAILABLE

    port = find_port()
    if port is None:
        _UNAVAILABLE = ("Power BI Desktop is not running, so no Analysis Services instance "
                        "exists to execute DAX against")
        return None, _UNAVAILABLE

    dll = _adomd_path()
    if dll is None:
        _UNAVAILABLE = "the ADOMD client assembly that ships with Desktop was not found"
        return None, _UNAVAILABLE

    try:
        import clr  # noqa: F401  (pythonnet)
        from System.Reflection import Assembly
        Assembly.LoadFrom(dll)
        # The DLL is named ...PowerBI.AdomdClient; the namespace is AnalysisServices.
        from Microsoft.AnalysisServices.AdomdClient import AdomdConnection
        # The catalog has to be named. Desktop's database is a GUID it assigns per session,
        # so it is discovered rather than configured; without it every INFO query returns
        # nothing and the model looks empty when it is loaded and fine.
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
        if not catalogs:
            _UNAVAILABLE = (f"Desktop is running on port {port} but has no model loaded; "
                            f"open the PBIP project before running DAX controls")
            return None, _UNAVAILABLE
        # Prefer our own deployed model when it is there. Desktop's own session database is
        # a GUID and, with no PBIP loaded, is empty -- connecting to it makes a live engine
        # look like a broken one.
        preferred = next((c for c in catalogs if "Northstar" in c), catalogs[0])
        con = AdomdConnection(
            f"Data Source=localhost:{port};Initial Catalog={preferred}")
        con.Open()
        _CONNECTION = con
    except Exception as exc:                                  # pragma: no cover - environment
        _UNAVAILABLE = f"could not connect to localhost:{port}: {exc.__class__.__name__}: {exc}"
        return None, _UNAVAILABLE
    return _CONNECTION, None


def reset() -> None:
    """
    Forget the cached connection.

    The catalog is chosen when the connection opens, so a connection made before the model was
    deployed points at Desktop's own empty session database and keeps reporting an empty model
    long after a real one exists beside it.
    """
    global _CONNECTION, _UNAVAILABLE
    if _CONNECTION is not None:
        try:
            _CONNECTION.Close()
        except Exception:
            pass
    _CONNECTION, _UNAVAILABLE = None, None


def available() -> tuple[bool, str]:
    con, why = connect()
    return con is not None, why or f"connected to Desktop on port {find_port()}"


def _py(value):
    if value is None:
        return None
    if isinstance(value, decimal.Decimal):
        return float(value)
    for attr in ("ToString",):
        if hasattr(value, attr) and not isinstance(value, (int, float, str, bool)):
            try:
                return float(str(value))
            except (TypeError, ValueError):
                return str(value)
    return value


def query(dax: str) -> list[tuple]:
    """Execute DAX and return rows. Raises if Desktop is unavailable -- callers check first."""
    con, why = connect()
    if con is None:
        raise RuntimeError(why)
    cmd = con.CreateCommand()
    cmd.CommandText = dax
    reader = cmd.ExecuteReader()
    rows = []
    try:
        while reader.Read():
            rows.append(tuple(_py(reader.GetValue(i)) for i in range(reader.FieldCount)))
    finally:
        reader.Close()
    return rows


def scalar(expression: str) -> float | None:
    """Evaluate one measure expression to a single value."""
    rows = query(f'EVALUATE ROW ( "v", {expression} )')
    return rows[0][0] if rows and rows[0] else None


def measure_at(measure: str, period_key: int | None = None,
               extra: str = "") -> float | None:
    """
    Evaluate `[Measure]` in a stated filter context.

    The filter is written the way a report writes one -- a period and, optionally, a scenario
    -- so what is measured is the measure as a reader would meet it, not a stripped version of
    it that only exists in the control.
    """
    filters = []
    if period_key is not None:
        filters.append(f"'Date'[period_key] = {period_key}")
    if extra:
        filters.append(extra)
    inner = f"[{measure}]"
    if filters:
        inner = f"CALCULATE ( {inner}, {', '.join(filters)} )"
    return scalar(inner)


def model_loaded() -> bool:
    """Whether a model with our tables is actually loaded, not merely a server running."""
    try:
        rows = query("EVALUATE ROW ( \"n\", COUNTROWS ( INFO.TABLES () ) )")
        return bool(rows and rows[0][0])
    except Exception:
        return False


def table_names() -> list[str]:
    try:
        return sorted(r[0] for r in query(
            'EVALUATE SELECTCOLUMNS ( INFO.TABLES (), "n", [Name] )'))
    except Exception:
        return []
