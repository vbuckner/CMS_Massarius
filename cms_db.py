"""MySQL side of CMS Massarius: settings, connection, tables and the queries the scan and the web page use.

Tables (database from settings.json, default cms_db):
  emails        one row per email per account (mailbox); unique on (account, message_id)
  lookup_tags   the tag types (ssp, client, internal, dashboard, ...) and the rules the auto tagger uses
  email_tags    which tags an email has. status: auto (set by the scan, may be replaced),
                manual (set or confirmed by you, never touched by the scan),
                rejected (you said "not this tag": the scan will not add it again)

The MySQL login comes from the credentials file named in settings.json; it is never printed.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SETTINGS_FILE = ROOT / "config" / "settings.json"
STEPS_FILE = ROOT / "steps.md"

DEFAULT_SETTINGS = {
    "port": 8770, "credentialsPath": r"C:\dev\credentials", "mysqlCredentialsFile": "mysql.json",
    "anythingllmCredentialsFile": "anythingllm.json", "database": "cms_db", "mailboxes": [], "days": 1,
    "scheduleTimes": ["09:00", "17:00"], "llmTagging": True, "anythingllmWorkspace": "cms-tagger",
    "llmBodyChars": 2000,
}


def read_settings():
    settings = dict(DEFAULT_SETTINGS)
    try:
        settings.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError):
        pass
    if os.environ.get("CMS_DATABASE"):              # e.g. cms_db_test for looking at the page with fake data
        settings["database"] = os.environ["CMS_DATABASE"]
    return settings


def version():
    """The 'version:' line of steps.md, e.g. 'v 0.0.2'."""
    try:
        for line in STEPS_FILE.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("version:"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def credentials_file(settings, key):
    """The file in credentialsPath (settings.json), else the repo's own credentials folder (git-ignored)."""
    path = Path(settings["credentialsPath"]) / settings[key]
    local = ROOT / "credentials" / settings[key]
    return local if not path.exists() and local.exists() else path


# ---------------------------------------------------------------- connection

def connect(settings=None, database=None):
    import MySQLdb
    settings = settings or read_settings()
    raw = json.loads(credentials_file(settings, "mysqlCredentialsFile").read_text(encoding="utf-8-sig"))

    def pick(*names, default=None):
        for n in names:
            if raw.get(n) not in (None, ""):
                return raw[n]
        return default

    conn = MySQLdb.connect(host=str(pick("host", "hostname", "server")), port=int(pick("port", default=3306)),
                           user=str(pick("user", "username", "login")),
                           password=str(pick("password", "passwd", "pwd")), charset="utf8mb4")
    db = database or settings["database"]
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db}` DEFAULT CHARACTER SET utf8mb4")
    cur.execute(f"USE `{db}`")
    return conn


# ---------------------------------------------------------------- tables

EMAILS = """
CREATE TABLE IF NOT EXISTS emails (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  account          VARCHAR(190)  NOT NULL,
  message_id       VARCHAR(500)  NOT NULL,
  folder           VARCHAR(500)  NULL,
  sent_on          DATETIME      NULL,
  received_at      DATETIME      NULL,
  from_name        VARCHAR(255)  NULL,
  from_email       VARCHAR(255)  NULL,
  to_recipients    TEXT          NULL,
  cc_recipients    TEXT          NULL,
  subject          VARCHAR(1000) NULL,
  body             MEDIUMTEXT    NULL,
  attachment_count INT           NOT NULL DEFAULT 0,
  attachment_names TEXT          NULL,
  conversation_id  VARCHAR(255)  NULL,
  categories       VARCHAR(500)  NULL,
  importance       TINYINT       NULL,
  is_read          TINYINT       NULL,
  entry_id         VARCHAR(512)  NULL,
  store_id         TEXT          NULL,
  tagged_at        DATETIME      NULL,
  loaded_at        DATETIME      NOT NULL,
  updated_at       DATETIME      NULL,
  UNIQUE KEY uq_account_message (account, message_id),
  KEY ix_received (account, received_at)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
"""

LOOKUP_TAGS = """
CREATE TABLE IF NOT EXISTS lookup_tags (
  id               INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  tag              VARCHAR(60)  NOT NULL,
  description      VARCHAR(500) NULL,
  sender_patterns  TEXT         NULL COMMENT 'one per line: part of the sender address, e.g. @massarius.com or pubmatic.com',
  keyword_patterns TEXT         NULL COMMENT 'one per line: word or phrase looked for in the subject',
  active           TINYINT      NOT NULL DEFAULT 1,
  sort_order       INT          NOT NULL DEFAULT 0,
  created_on       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_tag (tag)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
"""

EMAIL_TAGS = """
CREATE TABLE IF NOT EXISTS email_tags (
  id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  email_id   BIGINT UNSIGNED NOT NULL,
  tag_id     INT UNSIGNED    NOT NULL,
  status     ENUM('auto','manual','rejected') NOT NULL DEFAULT 'auto',
  source     VARCHAR(20)     NOT NULL COMMENT 'rules, llm or user',
  reason     VARCHAR(255)    NULL,
  created_on DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_on DATETIME        NULL ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_email_tag (email_id, tag_id),
  KEY ix_tag (tag_id, status),
  CONSTRAINT fk_email_tags_email FOREIGN KEY (email_id) REFERENCES emails (id) ON DELETE CASCADE,
  CONSTRAINT fk_email_tags_tag   FOREIGN KEY (tag_id)   REFERENCES lookup_tags (id)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
"""

# Starting tags. The sender patterns are public SSP domains, not taken from your mail; edit them on the Tags tab.
SEED_TAGS = [
    ("internal", "Sent by a Massarius colleague", "@massarius.com", "", 10),
    ("ssp", "Supply-side platform / ad exchange (Google, Magnite, PubMatic, ...)",
     "\n".join(["google.com", "doubleclick.net", "magnite.com", "rubiconproject.com", "pubmatic.com", "xandr.com",
                "indexexchange.com", "openx.com", "triplelift.com", "sovrn.com", "equativ.com", "smartadserver.com",
                "adform.com", "criteo.com", "teads.com", "teads.tv", "improvedigital.com", "adhese.com",
                "onetag.com", "sharethrough.com", "yieldmo.com", "freewheel.com", "seedtag.com", "richaudience.com",
                "adyoulike.com", "ogury.co", "amazon-adsystem.com", "smaato.com", "verve.com", "illumin.com"]),
     "", 20),
    ("client", "A publisher / client of Massarius", "", "", 30),
    ("dashboard", "Automated dashboard or scheduled report", "noreply\nno-reply\nlookerstudio",
     "dashboard\nscheduled report\ndaily report\nweekly report\nmonthly report", 40),
    ("invoice", "Invoice, payment, remittance or credit note", "",
     "invoice\nfactuur\nremittance\npayment\ncredit note\nstatement", 50),
    ("newsletter", "Newsletter, marketing or event mail", "", "newsletter\nwebinar\nunsubscribe", 60),
]


def _columns(cur, table):
    cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                (table,))
    return {r[0] for r in cur.fetchall()}


def _upgrade_emails(cur):
    """The first version (27 Nov) had mailbox / sender_name / sender_email and no Outlook ids: rename and add."""
    cols = _columns(cur, "emails")
    if not cols:
        return
    renames = [("mailbox", "account"), ("sender_name", "from_name"), ("sender_email", "from_email")]
    for old, new in renames:
        if old in cols and new not in cols:
            cur.execute(f"ALTER TABLE emails RENAME COLUMN {old} TO {new}")
    cols = _columns(cur, "emails")
    adds = [("sent_on", "DATETIME NULL AFTER folder"), ("entry_id", "VARCHAR(512) NULL AFTER is_read"),
            ("store_id", "TEXT NULL AFTER entry_id"), ("tagged_at", "DATETIME NULL AFTER store_id"),
            ("updated_at", "DATETIME NULL AFTER loaded_at")]
    for name, spec in adds:
        if name not in cols:
            cur.execute(f"ALTER TABLE emails ADD COLUMN {name} {spec}")
    cur.execute("SELECT INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'emails' AND INDEX_NAME = 'uq_mailbox_message'")
    if cur.fetchone():
        cur.execute("ALTER TABLE emails RENAME INDEX uq_mailbox_message TO uq_account_message")


def ensure_tables(conn):
    cur = conn.cursor()
    _upgrade_emails(cur)
    for sql in (EMAILS, LOOKUP_TAGS, EMAIL_TAGS):
        cur.execute(sql)
    cur.execute("SELECT COUNT(*) FROM lookup_tags")
    if cur.fetchone()[0] == 0:
        cur.executemany("INSERT INTO lookup_tags (tag, description, sender_patterns, keyword_patterns, sort_order) "
                        "VALUES (%s, %s, %s, %s, %s)", SEED_TAGS)
    conn.commit()


# ---------------------------------------------------------------- writing emails

EMAIL_COLUMNS = ["account", "message_id", "folder", "sent_on", "received_at", "from_name", "from_email",
                 "to_recipients", "cc_recipients", "subject", "body", "attachment_count", "attachment_names",
                 "conversation_id", "categories", "importance", "is_read", "entry_id", "store_id", "loaded_at"]
REFRESHED = [c for c in EMAIL_COLUMNS if c not in ("account", "message_id", "loaded_at")]


def save_emails(conn, rows):
    """Insert new emails, refresh the ones already there (same row id, so their tags stay). Returns (new, refreshed)."""
    if not rows:
        return 0, 0
    cur = conn.cursor()
    account = rows[0]["account"]
    ids = [r["message_id"] for r in rows]
    existing = set()
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        cur.execute(f"SELECT message_id FROM emails WHERE account = %s AND message_id IN ({','.join(['%s'] * len(chunk))})",
                    [account] + chunk)
        existing.update(r[0] for r in cur.fetchall())
    sql = (f"INSERT INTO emails ({', '.join(EMAIL_COLUMNS)}) VALUES ({', '.join(['%s'] * len(EMAIL_COLUMNS))}) AS new "
           f"ON DUPLICATE KEY UPDATE {', '.join(f'{c} = new.{c}' for c in REFRESHED)}, updated_at = new.loaded_at")
    cur.executemany(sql, [[r[c] for c in EMAIL_COLUMNS] for r in rows])
    conn.commit()
    return len(rows) - len(existing), len(existing)


# ---------------------------------------------------------------- tags

def active_tags(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, tag, description, sender_patterns, keyword_patterns FROM lookup_tags WHERE active = 1 "
                "ORDER BY sort_order, tag")
    return [{"id": r[0], "tag": r[1], "description": r[2] or "", "senders": _lines(r[3]), "keywords": _lines(r[4])}
            for r in cur.fetchall()]


def _lines(text):
    return [p.strip().lower() for p in (text or "").replace(";", "\n").replace(",", "\n").splitlines() if p.strip()]


def emails_to_tag(conn, account=None, limit=5000):
    cur = conn.cursor()
    sql = "SELECT id, from_name, from_email, to_recipients, subject, body FROM emails WHERE tagged_at IS NULL"
    args = []
    if account:
        sql += " AND account = %s"
        args.append(account)
    cur.execute(sql + " ORDER BY received_at DESC LIMIT %s", args + [limit])
    keys = ["id", "from_name", "from_email", "to_recipients", "subject", "body"]
    return [dict(zip(keys, r)) for r in cur.fetchall()]


def save_auto_tags(conn, email_id, proposals):
    """proposals: [(tag_id, source, reason)]. Replaces this email's auto tags; manual and rejected rows stay as they are."""
    cur = conn.cursor()
    cur.execute("DELETE FROM email_tags WHERE email_id = %s AND status = 'auto'", (email_id,))
    for tag_id, source, reason in proposals:
        cur.execute("INSERT IGNORE INTO email_tags (email_id, tag_id, status, source, reason) VALUES (%s, %s, 'auto', %s, %s)",
                    (email_id, tag_id, source, (reason or "")[:255]))
    cur.execute("UPDATE emails SET tagged_at = NOW() WHERE id = %s", (email_id,))
    conn.commit()


def set_tag(conn, email_id, tag_id, action):
    """Your amendments from the web page.
    add / confirm -> manual (kept for good), reject -> rejected (the scan will not add it again),
    clear -> the row is removed (the tag is the scan's call again)."""
    cur = conn.cursor()
    if action in ("add", "confirm"):
        cur.execute("INSERT INTO email_tags (email_id, tag_id, status, source, reason) VALUES (%s, %s, 'manual', 'user', '') "
                    "ON DUPLICATE KEY UPDATE status = 'manual'", (email_id, tag_id))
    elif action == "reject":
        cur.execute("INSERT INTO email_tags (email_id, tag_id, status, source, reason) VALUES (%s, %s, 'rejected', 'user', '') "
                    "ON DUPLICATE KEY UPDATE status = 'rejected'", (email_id, tag_id))
    elif action == "clear":
        cur.execute("DELETE FROM email_tags WHERE email_id = %s AND tag_id = %s", (email_id, tag_id))
    else:
        raise ValueError(f"unknown action {action!r}")
    conn.commit()


def queue_retag(conn, which):
    """which = 'untagged' (emails with no tag at all) or 'all'. Returns how many are queued for the next tagging run."""
    cur = conn.cursor()
    if which == "all":
        n = cur.execute("UPDATE emails SET tagged_at = NULL")
    elif which == "untagged":
        n = cur.execute("UPDATE emails e SET tagged_at = NULL WHERE NOT EXISTS "
                        "(SELECT 1 FROM email_tags t WHERE t.email_id = e.id)")
    else:
        raise ValueError("retag must be 'untagged' or 'all'")
    conn.commit()
    return n


def retag(conn, email_ids):
    """Ask the scan to tag these emails again (their auto tags are replaced on the next tagging run)."""
    if not email_ids:
        return 0
    cur = conn.cursor()
    n = cur.execute(f"UPDATE emails SET tagged_at = NULL WHERE id IN ({','.join(['%s'] * len(email_ids))})", email_ids)
    conn.commit()
    return n


# ---------------------------------------------------------------- reading for the web page

def list_emails(conn, account="", tag_id="", search="", limit=200, offset=0):
    cur = conn.cursor()
    where, args = ["1 = 1"], []
    if account:
        where.append("e.account = %s")
        args.append(account)
    if tag_id == "none":
        where.append("NOT EXISTS (SELECT 1 FROM email_tags t WHERE t.email_id = e.id AND t.status <> 'rejected')")
    elif tag_id:
        where.append("EXISTS (SELECT 1 FROM email_tags t WHERE t.email_id = e.id AND t.tag_id = %s AND t.status <> 'rejected')")
        args.append(int(tag_id))
    if search:
        where.append("(e.subject LIKE %s OR e.from_name LIKE %s OR e.from_email LIKE %s)")
        args += [f"%{search}%"] * 3
    cur.execute(f"SELECT COUNT(*) FROM emails e WHERE {' AND '.join(where)}", args)
    total = cur.fetchone()[0]
    cur.execute(f"SELECT e.id, e.account, e.received_at, e.sent_on, e.from_name, e.from_email, e.subject, "
                f"e.attachment_count, e.folder FROM emails e WHERE {' AND '.join(where)} "
                f"ORDER BY e.received_at DESC LIMIT %s OFFSET %s", args + [int(limit), int(offset)])
    keys = ["id", "account", "received_at", "sent_on", "from_name", "from_email", "subject", "attachment_count", "folder"]
    rows = [dict(zip(keys, r)) for r in cur.fetchall()]
    tags = tags_for(conn, [r["id"] for r in rows])
    for r in rows:
        r["tags"] = tags.get(r["id"], [])
    return total, rows


def tags_for(conn, email_ids):
    if not email_ids:
        return {}
    cur = conn.cursor()
    cur.execute("SELECT et.email_id, et.tag_id, lt.tag, et.status, et.source, et.reason FROM email_tags et "
                f"JOIN lookup_tags lt ON lt.id = et.tag_id WHERE et.email_id IN ({','.join(['%s'] * len(email_ids))}) "
                "ORDER BY lt.sort_order, lt.tag", email_ids)
    out = {}
    for email_id, tag_id, tag, status, source, reason in cur.fetchall():
        out.setdefault(email_id, []).append({"tag_id": tag_id, "tag": tag, "status": status, "source": source,
                                             "reason": reason or ""})
    return out


def get_email(conn, email_id):
    cur = conn.cursor()
    keys = ["id", "account", "folder", "sent_on", "received_at", "from_name", "from_email", "to_recipients",
            "cc_recipients", "subject", "body", "attachment_count", "attachment_names", "categories", "importance",
            "is_read", "entry_id", "store_id", "tagged_at", "loaded_at", "updated_at"]
    cur.execute(f"SELECT {', '.join(keys)} FROM emails WHERE id = %s", (email_id,))
    row = cur.fetchone()
    if not row:
        return None
    email = dict(zip(keys, row))
    email["tags"] = tags_for(conn, [email_id]).get(email_id, [])
    return email


def list_tags(conn):
    cur = conn.cursor()
    cur.execute("SELECT lt.id, lt.tag, lt.description, lt.sender_patterns, lt.keyword_patterns, lt.active, lt.sort_order, "
                "(SELECT COUNT(*) FROM email_tags et WHERE et.tag_id = lt.id AND et.status <> 'rejected') "
                "FROM lookup_tags lt ORDER BY lt.sort_order, lt.tag")
    keys = ["id", "tag", "description", "sender_patterns", "keyword_patterns", "active", "sort_order", "emails"]
    return [dict(zip(keys, r)) for r in cur.fetchall()]


def save_tag(conn, data):
    tag = (data.get("tag") or "").strip().lower()
    if not tag or len(tag) > 60:
        raise ValueError("a tag needs a name of 1 to 60 characters")
    values = [tag, (data.get("description") or "").strip()[:500], data.get("sender_patterns") or "",
              data.get("keyword_patterns") or "", 1 if data.get("active", True) else 0, int(data.get("sort_order") or 0)]
    cur = conn.cursor()
    if data.get("id"):
        cur.execute("UPDATE lookup_tags SET tag=%s, description=%s, sender_patterns=%s, keyword_patterns=%s, active=%s, "
                    "sort_order=%s WHERE id=%s", values + [int(data["id"])])
    else:
        cur.execute("INSERT INTO lookup_tags (tag, description, sender_patterns, keyword_patterns, active, sort_order) "
                    "VALUES (%s, %s, %s, %s, %s, %s)", values)
    conn.commit()


def accounts(conn):
    cur = conn.cursor()
    cur.execute("SELECT account, COUNT(*), MAX(received_at) FROM emails GROUP BY account ORDER BY account")
    return [{"account": a, "emails": n, "latest": latest} for a, n, latest in cur.fetchall()]
