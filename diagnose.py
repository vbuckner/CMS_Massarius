"""Turns an error into a short summary and a suggested fix, for the scan log, the scan summary and the page.

    explain(err) -> {"summary": "...", "fix": "...", "details": "<traceback>"}
"""
import traceback

# Outlook / COM error codes (HRESULTs) seen when Outlook is closed, busy or missing
COM_NOT_RUNNING = {-2147023174, -2147417848, -2147023170, -2147221021, -2147418111, -2147417846}
COM_NOT_INSTALLED = {-2147221005, -2147221164}


def _mysql_code(err):
    args = getattr(err, "args", ())
    return args[0] if args and isinstance(args[0], int) else None


def explain(err):
    name = type(err).__name__
    module = type(err).__module__ or ""
    text = str(err)
    low = f"{name} {text}".lower()
    code = _mysql_code(err)
    summary, fix = f"{name}: {text}"[:300], "See the details below; if it keeps happening, ask Claude with these details."

    if isinstance(err, ImportError):
        missing = getattr(err, "name", "") or text
        summary = f"A Python package is missing: {missing}"
        package = {"win32com": "pywin32", "pythoncom": "pywin32", "pywintypes": "pywin32", "MySQLdb": "mysqlclient"}
        fix = f"Install it in cmd:  py -3.14 -m pip install {package.get(missing.split('.')[0], missing)}"
    elif module.startswith("MySQLdb") or "mysql" in low:
        if code in (2002, 2003, 2006, 2013) or "can't connect" in low or "lost connection" in low:
            summary = "MySQL is not running (no answer on localhost:3306)"
            fix = "Start it: open cmd as administrator and run  net start MySQL80  (or Services > MySQL80 > Start), then try again."
        elif code == 1045:
            summary = "MySQL refused the login"
            fix = "Check the user and password in the mysql.json credentials file."
        elif code in (1205, 1213):
            summary = "MySQL was busy (a lock); nothing was saved for this step"
            fix = "Run the scan again; emails already stored are simply refreshed."
        else:
            summary = f"MySQL error {code or ''}: {text}"[:300]
            fix = "Check that MySQL80 is running (net start MySQL80); see the details for the exact message."
    elif name == "com_error" or module.startswith("pywintypes") or "win32com" in low:
        hresult = getattr(err, "hresult", None) or (err.args[0] if getattr(err, "args", None) else None)
        if hresult in COM_NOT_INSTALLED:
            summary = "Classic Outlook could not be started from Python"
            fix = "Check that classic Outlook (not the 'new Outlook' app) is installed and opens normally."
        elif hresult in COM_NOT_RUNNING:
            summary = "Outlook was closed, busy or restarting during the scan"
            fix = "Open classic Outlook, close any Outlook dialog that is waiting, then scan again."
        else:
            summary = f"Outlook (COM) error {hresult}: {text}"[:300]
            fix = "Make sure classic Outlook is open and not showing a dialog; if it continues, restart Outlook."
    elif isinstance(err, LookupError) and "not open in outlook" in low:
        summary = text.split(". Outlook has:")[0]
        fix = "Add that mailbox in Outlook (File > Account settings), or correct the name in config/settings.json."
    elif isinstance(err, FileNotFoundError):
        summary = f"A file was not found: {getattr(err, 'filename', '') or text}"
        fix = "If it is a credentials file, put it in C:\\dev\\credentials or the repo's credentials folder."
    elif "urlopen" in low or name in ("URLError", "ConnectionRefusedError", "TimeoutError", "HTTPError"):
        summary = f"AnythingLLM did not answer ({name})"
        fix = "Open AnythingLLM and check its API key (Settings > Developer API); the scan tags by rules meanwhile."

    details = "".join(traceback.format_exception(type(err), err, err.__traceback__)).strip()
    return {"summary": summary, "fix": fix, "details": details}


def log_block(err, context=""):
    """Lines for the log file. The page shows ERROR / FIX in red and folds the details away."""
    info = explain(err)
    lines = [f"!! ERROR: {context + ': ' if context else ''}{info['summary']}", f"!! FIX: {info['fix']}", "!! DETAILS >>>"]
    lines += info["details"].splitlines()
    lines.append("!! <<<")
    return info, lines
