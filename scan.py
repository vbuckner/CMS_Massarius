"""Scan the mailboxes into MySQL and tag the new emails. Run by the scheduled task and by the web page.

    python scan.py                                   # settings.json mailboxes and days
    python scan.py --days 30
    python scan.py --mailbox "Massarius | Billing" --mailbox "Massarius | Finance"
    python scan.py --no-tag                          # read only, no tagging
    python scan.py --tag-only                        # no Outlook: tag the emails not tagged yet
    python scan.py --retag untagged                  # no Outlook: tag again the emails with no tag (or: all)
    python scan.py --dry-run                         # read and count, write nothing
    python scan.py --log logs/scan.log               # output to the log file (the scheduled task does this)

Emails already in the table are refreshed in place (same row id), so their tags stay.
Only counts are printed: no subjects, senders or bodies.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import cms_db
import outlook_reader
import tagger


def run(args, settings):
    if args.tag_only or args.retag:
        conn = cms_db.connect(settings)
        cms_db.ensure_tables(conn)
        if args.retag:
            print(f"retag: {cms_db.queue_retag(conn, args.retag)} emails queued ({args.retag})")
        tagger.tag_new_emails(conn, settings, say=lambda text: print("  " + text))
        conn.close()
        print("tag only: done")
        return 0
    mailboxes = args.mailbox or settings["mailboxes"]
    days = args.days or settings["days"]
    print(f"scan: {len(mailboxes)} mailbox(es), last {days} day(s)" + (" (dry run)" if args.dry_run else ""))
    conn = None if args.dry_run else cms_db.connect(settings)
    if conn is not None:
        cms_db.ensure_tables(conn)
    ns = outlook_reader.outlook()
    failed = 0
    for name in mailboxes:
        try:
            account, rows, skipped, per_folder = outlook_reader.read_mailbox(
                name, days, ns, say=(lambda text: print("    " + text, flush=True)) if args.verbose else None)
            folders = ", ".join(f"{path} {count}" for path, count in per_folder if count)
            print(f"  {account}: {len(rows)} emails ({folders or 'none'}; {skipped} non-email items skipped)")
            if conn is not None and rows:
                new, refreshed = cms_db.save_emails(conn, rows)
                print(f"    saved: {new} new, {refreshed} refreshed")
        except Exception as err:
            failed += 1
            print(f"  {name}: FAILED - {type(err).__name__}: {err}")
    if conn is not None and not args.no_tag:
        tagger.tag_new_emails(conn, settings, say=lambda text: print("  " + text))
    if conn is not None:
        conn.close()
    print("scan: done" + (f", {failed} mailbox(es) failed" if failed else ""))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Outlook -> cms_db.emails, then auto tagging")
    ap.add_argument("--days", type=int, help="how many days back (default: settings.json)")
    ap.add_argument("--mailbox", action="append", help="mailbox as Outlook names it; repeat for more (default: settings.json)")
    ap.add_argument("--no-tag", action="store_true", help="do not tag the new emails")
    ap.add_argument("--tag-only", action="store_true", help="no Outlook: only tag the emails not tagged yet")
    ap.add_argument("--retag", choices=["untagged", "all"],
                    help="no Outlook: tag again the emails with no tag, or all emails (your own tags are kept)")
    ap.add_argument("--dry-run", action="store_true", help="read and count only, write nothing")
    ap.add_argument("--verbose", action="store_true", help="progress per folder (names and counts only)")
    ap.add_argument("--log", help="append the output to this file (the scheduled task has no window)")
    args = ap.parse_args(argv)
    settings = cms_db.read_settings()
    if not args.log:
        return run(args, settings)
    log_path = Path(args.log)
    if not log_path.is_absolute():
        log_path = cms_db.ROOT / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8", buffering=1) as log:
        sys.stdout = sys.stderr = log
        print(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} ===")
        try:
            return run(args, settings)
        except BaseException:
            import traceback
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    sys.exit(main())
