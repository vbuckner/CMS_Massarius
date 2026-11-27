# CMS Massarius: notes for Claude

Read this first in every session on this repo. Keep it up to date when something here changes.

## What it is
CMS thoughts for Massarius: an email scanner that stores Outlook mail in a local MySQL database, tags it, and
(later) a "brain" style interface that can answer questions over it and run agents. The user's spec and to-do list is
`steps.md`; finished items get a tick after the `-` (`- ✓ text`).

## Hard rules (from steps.md, never break them)
- **Email content stays on this PC.** Never print or read subjects, senders, recipients, bodies, attachment names
  or sender domains into my own output: that would send them to Claude's cloud. Print only counts, structure,
  folder/mailbox names and errors. Analysis of the mail is done by local code or AnythingLLM (local Qwen).
  To look at the web page in the browser pane, run it on the fake data: `set CMS_DATABASE=cms_db_test` then
  `python server.py` (the tests fill cms_db_test), and check `/api/info` shows only "Test | Box" before any screenshot.
- No libraries where they are not needed. Allowed: `MySQLdb` (mysqlclient, MySQL driver) and `pywin32` (Outlook).
  Everything else is the standard library; the web page is plain HTML/CSS/JS with no CDN.
- MySQL is the local MySQL80 service only (port 3306, started by hand). Never touch the billing databases
  (billing_ms, central_db, temp_import_db) or MariaDB.
- Outlook is the logged-in classic Outlook through COM. Read only: never move, flag, mark read or change mail.
  (Opening an email from the page shows it in Outlook, which marks it read - that is the user's own click.)
- Never open the credentials files (`C:\dev\credentials\mysql.json`, `anythingllm.json`). The code reads them.
- Small version steps (v 0.0.1 -> v 0.0.2) unless told otherwise; the version is the `version:` line of steps.md
  (the page reads it from there). Every version gets an entry in `changelog.md`.
- The user commits and pushes; I do not.

## Layout
- `config/settings.json` port 8770, credentials folder, database (cms_db), mailboxes, days, schedule times,
  AnythingLLM workspace (cms-tagger), llmTagging on/off.
- `cms_db.py` settings, MySQL connection, tables, all queries. `ensure_tables()` creates/upgrades the tables.
- `outlook_reader.py` reads a mailbox (Inbox + sub folders, Sent Items) with a server-side date filter.
- `tagger.py` auto tags: rules from lookup_tags, then AnythingLLM (OpenAI-style endpoint of the workspace).
- `scan.py` the command line the scheduled task and the page run (`--days`, `--mailbox`, `--tag-only`, `--dry-run`,
  `--verbose`, `--log`).
- `server.py` + `web/` the page on http://127.0.0.1:8770 (Emails, Tags, Scan tabs; /open/<id> opens in Outlook).
- `scripts/schedule_scan.ps1` registers the Windows task "CMS Massarius scan".
- `tests/test_cms.py` unittest on fake data in cms_db_test: `python -m unittest tests.test_cms -v`.
- `logs/scan.log` (git-ignored) output of every scan.

## Tables (cms_db)
- `emails` unique (account, message_id). A rescan refreshes the row in place (same id, tags stay).
  Holds entry_id + store_id so Outlook can open it; tagged_at NULL = still to be tagged.
- `lookup_tags` tag types + rules (sender_patterns, keyword_patterns: one per line).
- `email_tags` status auto (the scan's, replaced on re-tag) / manual (the user's) / rejected (the scan may not add
  it again). source rules / llm / user.

## AnythingLLM
Installed (desktop), LLM provider is its built-in local runner with Qwen3-8B. The tagger needs a Developer API key
in `<credentialsPath>\anythingllm.json`: `{"url": "http://localhost:3001", "apiKey": "..."}`, which the user makes.
Without it (or with AnythingLLM closed) the scan logs that and tags by rules only.
