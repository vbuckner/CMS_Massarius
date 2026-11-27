# Changelog

Newest first. One entry per version (the `version:` line in steps.md).

## v 0.0.5 (2026-11-27)
- Menu: Scan, Emails on the left; a cog button on the right opens **Settings**, which has its own sub menu
  (Tags for now - the tag editor moved there).
- Scan tab: a bin button clears the log view (the log file itself is kept; the page remembers where you cleared).
  While a scan runs, a spinner of rainbow balls circles next to "Log"; when the run ends it hides and the page
  jumps to the Emails tab with that run's summary open.
- Errors are caught and explained (new `diagnose.py`): a red one-line summary, a "What to do" suggestion
  (e.g. MySQL not running -> `net start MySQL80`; Outlook closed or busy; a missing Python package; a mailbox not
  open in Outlook; AnythingLLM not answering) and the full details folded away (click to open) - in the log, in the
  scan summary (`scan_details` gets `fix` and `trace`), and in the page's own error messages.
- `CMS_LOG` lets a test copy of the page use its own log file.

## v 0.0.4 (2026-11-27)
- Menu: order Tags, Scan, Emails (Emails still opens first). Full 3D buttons in light purple with a lighter band
  (gradient leaning 75 degrees from the x axis, about 24 px in from the left; `--tab-angle` / `--tab-band` in
  style.css); the selected one is sunken. The tabs only show / hide their sections (nothing is reloaded).
- Emails tab: a "Scan summary" box at the top - pick any scan of the last two weeks and its summary loads in a
  scrollable box (max 400 px): accounts, tags given, emails AnythingLLM flags as important (click one to see it),
  notes and errors. The email list stays hidden until you use a filter, search, or "Show emails".
  New filter "! Important (AnythingLLM)"; important emails show a red "!" and the reason.
- Tags tab: loaded once, so switching tabs keeps unsaved edits. Saved rows light green, changed / new rows orange,
  Cancel removes a new row or undoes the changes, a second "Add a tag" button at the top (jumps to the new row).
- Scan tab: the log can be folded away.
- Every run is recorded: new tables `scan_info` (date/time, who started it, mode, days, mailboxes, counts, status)
  and `scan_details` (rows per account, per tag, important emails, notes, errors). `emails` gets `scan_id`
  (the scan that first stored it), `important` and `important_why`.
- Experiment: AnythingLLM is asked in the same call whether an email looks important (needs action soon) and why.
  Only new / re-tagged emails get this; the 1,165 already stored are not asked until a `--retag all`.
- The scheduled task now passes `--source schedule`; runs from the page are `page`, from cmd `cli`.
- `CMS_PORT` lets a second copy of the page run next to yours (used to check the page on the test data).

## v 0.0.3 (2026-11-27)
- AnythingLLM tagging switched on: the API key file is found in the repo's own `credentials` folder as well as in
  C:\dev\credentials. AnythingLLM's workspace `cms-tagger` was made by the code; about 5 s per email.
- `python scan.py --retag untagged` (or `all`): tag emails again without reading Outlook; your own tags are kept.
- Tagging prints progress every 25 emails when AnythingLLM is used.

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
