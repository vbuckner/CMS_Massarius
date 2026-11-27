"""CMS Massarius web page: python server.py  ->  http://127.0.0.1:8770  (this PC only).

Standard library only (plus the MySQL driver and pywin32 the other modules need).
  GET  /                         the page (web/index.html)
  GET  /api/info                 version, mailboxes in settings, accounts in the table, tag list
  GET  /api/emails?account=&tag=&q=&limit=&offset=
  GET  /api/emails/<id>          one email with its body and tags
  POST /api/emails/<id>/tags     {"tag_id": n, "action": "add" | "confirm" | "reject" | "clear"}
  POST /api/emails/<id>/retag    tag this email again on the next tagging run
  GET  /api/tags                 lookup_tags with counts;  POST /api/tags  add or change one
  POST /api/scan                 {"mailboxes": [...], "days": n, "tag": true}  starts scan.py
  GET  /api/scan                 is a scan running + the end of logs/scan.log
  POST /api/tag-now              runs the tagging only (scan.py with no mailboxes)
  GET  /api/scans?days=14        the scans of the last 14 days (scan_info)
  GET  /api/scans/<id>           one scan with its summary rows (scan_details)
  GET  /open/<id>                opens that email in Outlook (a link you can use anywhere on this PC)
"""
import json
import mimetypes
import os
import subprocess
import sys
import threading
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cms_db

WEB = cms_db.ROOT / "web"
LOG = cms_db.ROOT / "logs" / "scan.log"
_scan = {"proc": None}
_lock = threading.Lock()


def as_json(value):
    def default(v):
        if isinstance(v, (datetime, date)):
            return v.isoformat(sep=" ") if isinstance(v, datetime) else v.isoformat()
        return str(v)
    return json.dumps(value, default=default).encode("utf-8")


def scan_running():
    proc = _scan["proc"]
    return proc is not None and proc.poll() is None


def start_scan(extra_args):
    with _lock:
        if scan_running():
            raise RuntimeError("a scan is already running")
        LOG.parent.mkdir(parents=True, exist_ok=True)
        _scan["proc"] = subprocess.Popen([sys.executable, str(cms_db.ROOT / "scan.py"), "--log", str(LOG),
                                          "--source", "page"] + extra_args,
                                         cwd=str(cms_db.ROOT), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def log_tail(lines=40):
    try:
        return LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    except OSError:
        return []


class Handler(BaseHTTPRequestHandler):
    server_version = "CMSMassarius"

    def log_message(self, fmt, *args):          # keep the console quiet
        pass

    # ------------------------------------------------ helpers
    def send(self, status, body, ctype="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def ok(self, value):
        self.send(200, as_json(value))

    def fail(self, status, message):
        self.send(status, as_json({"error": message}))

    def body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}") if length else {}

    def parts(self):
        url = urlparse(self.path)
        return [p for p in url.path.split("/") if p], {k: v[-1] for k, v in parse_qs(url.query).items()}

    # ------------------------------------------------ GET
    def do_GET(self):
        parts, query = self.parts()
        try:
            if not parts or parts[0] in ("index.html",):
                return self.static("index.html")
            if parts[0] == "web" and len(parts) == 2:
                return self.static(parts[1])
            if parts[0] == "open" and len(parts) == 2:
                return self.open_email(int(parts[1]))
            if parts[0] != "api":
                return self.fail(404, "not found")
            settings = cms_db.read_settings()
            if parts[1:] == ["scan"]:
                return self.ok({"running": scan_running(), "log": log_tail()})
            conn = cms_db.connect(settings)
            try:
                cms_db.ensure_tables(conn)
                if parts[1:] == ["info"]:
                    return self.ok({"version": cms_db.version(), "mailboxes": settings["mailboxes"],
                                    "days": settings["days"], "accounts": cms_db.accounts(conn),
                                    "tags": cms_db.list_tags(conn), "llmTagging": settings["llmTagging"]})
                if parts[1:] == ["emails"]:
                    total, rows = cms_db.list_emails(conn, query.get("account", ""), query.get("tag", ""),
                                                     query.get("q", ""), min(int(query.get("limit", 200)), 1000),
                                                     int(query.get("offset", 0)))
                    return self.ok({"total": total, "emails": rows})
                if len(parts) == 3 and parts[1] == "emails":
                    email = cms_db.get_email(conn, int(parts[2]))
                    if email:
                        email.pop("store_id", None)
                        email["open_link"] = f"/open/{email['id']}" if email.get("entry_id") else ""
                        email.pop("entry_id", None)
                    return self.ok(email) if email else self.fail(404, "no such email")
                if parts[1:] == ["tags"]:
                    return self.ok(cms_db.list_tags(conn))
                if parts[1:] == ["scans"]:
                    return self.ok(cms_db.list_scans(conn, int(query.get("days", 14))))
                if len(parts) == 3 and parts[1] == "scans":
                    scan = cms_db.get_scan(conn, int(parts[2]))
                    return self.ok(scan) if scan else self.fail(404, "no such scan")
            finally:
                conn.close()
            return self.fail(404, "not found")
        except Exception as err:
            return self.fail(500, f"{type(err).__name__}: {err}")

    def static(self, name):
        path = (WEB / name).resolve()
        if path.parent != WEB.resolve() or not path.is_file():
            return self.fail(404, "not found")
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self.send(200, path.read_bytes(), ctype)

    def open_email(self, email_id):
        conn = cms_db.connect()
        try:
            email = cms_db.get_email(conn, email_id)
        finally:
            conn.close()
        if not email or not email.get("entry_id"):
            return self.send(404, b"<p>This email has no Outlook id yet: it is filled in on the next scan.</p>",
                             "text/html; charset=utf-8")
        import outlook_reader
        try:
            outlook_reader.open_in_outlook(email["entry_id"], email["store_id"])
        except Exception as err:
            msg = f"<p>Outlook could not open it ({type(err).__name__}). It may have been moved or deleted; " \
                  f"the next scan refreshes the link.</p>"
            return self.send(410, msg.encode("utf-8"), "text/html; charset=utf-8")
        self.send(200, b"<p>Opened in Outlook. You can close this tab.</p><script>setTimeout(()=>window.close(),800)</script>",
                  "text/html; charset=utf-8")

    # ------------------------------------------------ POST
    def do_POST(self):
        parts, _ = self.parts()
        try:
            data = self.body()
            if parts[:1] != ["api"]:
                return self.fail(404, "not found")
            if parts[1:] == ["scan"]:
                settings = cms_db.read_settings()
                args = []
                for name in data.get("mailboxes") or []:
                    if name not in settings["mailboxes"]:
                        return self.fail(400, f"{name!r} is not in settings.json mailboxes")
                    args += ["--mailbox", name]
                if not args:
                    return self.fail(400, "pick at least one mailbox")
                days = int(data.get("days") or settings["days"])
                if not 1 <= days <= 365:
                    return self.fail(400, "days must be 1 to 365")
                args += ["--days", str(days)]
                if not data.get("tag", True):
                    args.append("--no-tag")
                start_scan(args)
                return self.ok({"started": True})
            if parts[1:] == ["tag-now"]:
                start_scan(["--tag-only"])
                return self.ok({"started": True})
            conn = cms_db.connect()
            try:
                if len(parts) == 4 and parts[1] == "emails" and parts[3] == "tags":
                    cms_db.set_tag(conn, int(parts[2]), int(data["tag_id"]), data.get("action", ""))
                    return self.ok(cms_db.get_email(conn, int(parts[2]))["tags"])
                if len(parts) == 4 and parts[1] == "emails" and parts[3] == "retag":
                    cms_db.retag(conn, [int(parts[2])])
                    return self.ok({"queued": True})
                if parts[1:] == ["tags"]:
                    cms_db.save_tag(conn, data)
                    return self.ok(cms_db.list_tags(conn))
            finally:
                conn.close()
            return self.fail(404, "not found")
        except RuntimeError as err:
            return self.fail(409, str(err))
        except (ValueError, KeyError) as err:
            return self.fail(400, str(err))
        except Exception as err:
            return self.fail(500, f"{type(err).__name__}: {err}")


def main():
    settings = cms_db.read_settings()
    port = int(os.environ.get("CMS_PORT") or settings["port"])     # CMS_PORT: a second copy, e.g. on the test data
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"CMS Massarius {cms_db.version()} on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
