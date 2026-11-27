# Changelog

Newest first. One entry per version (the `version:` line in steps.md).

## v 0.0.2 (2026-11-27)
- Web page (`python server.py`, http://127.0.0.1:8770): title "CMS Massarius" with the version in smaller text and the
  info icon (white i, light blue circle, 1 px dark grey border, glows on hover, click toggles the info pop up).
- Tabs: **Emails** (filter by account / tag / search, detail with body, tags you can keep / reject / add,
  "Open in Outlook"), **Tags** (edit the tag list and its rules), **Scan** (pick mailboxes and days, scan now,
  tag untagged, log).
- `scan.py` reads your mailbox, Massarius | Billing and Massarius | Finance (settings.json) read only, with a
  server-side date filter; addresses are read from the email itself (about 20x quicker than the address book).
- MySQL `cms_db`: `emails` now has account, from, to, cc, sent on, received, subject, body, ... plus the Outlook
  ids to open it; a rescan refreshes an email in place, so its tags stay. New `lookup_tags` (internal, ssp, client,
  dashboard, invoice, newsletter with starting rules) and `email_tags` (auto / manual / rejected).
- Auto tagging on every scan: rules first, then AnythingLLM (local Qwen) when its API key file is in place.
  Your manual and rejected tags are never changed by the scan.
- Scheduled task "CMS Massarius scan" (scripts/schedule_scan.ps1) replaces the playground test task.
- `CLAUDE.md` (notes for Claude), this changelog, tests on fake data (`python -m unittest tests.test_cms -v`).

## v 0.0.1 (2026-11-27)
- Repo started with steps.md and .gitignore.
- Before the repo: a test script loaded the last days of your own mailbox into `cms_db.emails` and a scheduled
  task ran it at 09:00 and 17:00.
