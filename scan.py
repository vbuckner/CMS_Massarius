"""Scan the mailboxes into MySQL and tag the new emails. Run by the scheduled task and by the web page.

    python scan.py                                   # settings.json mailboxes and days
    python scan.py --days 30
    python scan.py --mailbox "Massarius | Billing" --mailbox "Massarius | Finance"
    python scan.py --no-tag                          # read only, no tagging
    python scan.py --tag-only                        # no Outlook: tag the emails not tagged yet
    python scan.py --retag untagged                  # no Outlook: tag again the emails with no tag (or: all)
    python scan.py --dry-run                         # read and count, write nothing
    python scan.py --log logs/scan.log               # output to the log file (the scheduled task does this)
    python scan.py --source schedule                 # who started it: schedule, page or cli (default)

Emails already in the table are refreshed in place (same row id), so their tags stay.
Every run (not a dry run) is recorded in scan_info, with its summary rows in scan_details: per account,
per tag, the emails AnythingLLM thinks are important, and errors. The page shows them on the Emails tab.
Only counts are printed: no subjects, senders or bodies.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import cms_db
import diagnose
import outlook_reader
import tagger


def say(text):
    print("  " + text, flush=True)


def record_tagging(conn, scan_id, summary):
    for tag, n in sorted(summary["per_tag"].items(), key=lambda kv: (-kv[1], kv[0])):
        cms_db.add_scan_detail(conn, scan_id, "tag", tag, n)
    for email_id, why in summary["important"]:
        cms_db.add_scan_detail(conn, scan_id, "important", None, None, why, email_id)
    if summary["tagged"] and not summary["llm_used"]:
        cms_db.add_scan_detail(conn, scan_id, "note", "AnythingLLM", None, "not used: tagged by rules only",
                               fix="Open AnythingLLM (and check its API key file) so the next scan uses it too.")
    if summary["llm_errors"]:
        cms_db.add_scan_detail(conn, scan_id, "error", "AnythingLLM", summary["llm_errors"], "emails it could not tag",
                               fix="Check AnythingLLM is open; use 'Tag again' or  python scan.py --retag untagged  later.")


def record_failure(conn, scan_id, err, context, read_total=0, new_total=0):
    """Puts a stopped run in scan_info / scan_details (if MySQL itself still answers)."""
    info = diagnose.explain(err)
    try:
        cms_db.add_scan_detail(conn, scan_id, "error", context, None, info["summary"], fix=info["fix"],
                               trace=info["details"])
        cms_db.finish_scan_info(conn, scan_id, "failed", read_total, new_total, message=info["summary"])
    except Exception:
        pass


def run_tag_only(args, settings):
    conn = cms_db.connect(settings)
    cms_db.ensure_tables(conn)
    mode = f"retag-{args.retag}" if args.retag else "tag-only"
    scan_id = cms_db.start_scan_info(conn, args.source, mode)
    try:
        if args.retag:
            print(f"retag: {cms_db.queue_retag(conn, args.retag)} emails queued ({args.retag})")
        summary = tagger.tag_new_emails(conn, settings, say=say)
        record_tagging(conn, scan_id, summary)
        cms_db.finish_scan_info(conn, scan_id, "ok", emails_tagged=summary["tagged"],
                                important=len(summary["important"]))
    except Exception as err:
        record_failure(conn, scan_id, err, mode)
        raise
    finally:
        conn.close()
    print(f"{mode}: done")
    return 0


def run(args, settings):
    if args.tag_only or args.retag:
        return run_tag_only(args, settings)
    mailboxes = args.mailbox or settings["mailboxes"]
    days = args.days or settings["days"]
    print(f"scan: {len(mailboxes)} mailbox(es), last {days} day(s)" + (" (dry run)" if args.dry_run else ""))
    conn = None if args.dry_run else cms_db.connect(settings)
    scan_id = None
    if conn is not None:
        cms_db.ensure_tables(conn)
        scan_id = cms_db.start_scan_info(conn, args.source, "scan", days, mailboxes, not args.no_tag)
    failed, read_total, new_total, summary = 0, 0, 0, None
    try:
        ns = outlook_reader.outlook()
        for name in mailboxes:
            try:
                account, rows, skipped, per_folder = outlook_reader.read_mailbox(
                    name, days, ns, say=(lambda text: print("    " + text, flush=True)) if args.verbose else None)
                folders = ", ".join(f"{path} {count}" for path, count in per_folder if count)
                print(f"  {account}: {len(rows)} emails ({folders or 'none'}; {skipped} non-email items skipped)")
                read_total += len(rows)
                if conn is not None:
                    new, refreshed = 0, 0
                    if rows:
                        for r in rows:
                            r["scan_id"] = scan_id
                        new, refreshed = cms_db.save_emails(conn, rows)
                        print(f"    saved: {new} new, {refreshed} refreshed")
                    new_total += new
                    cms_db.add_scan_detail(conn, scan_id, "account", account, new,
                                           f"{len(rows)} read: {new} new, {refreshed} refreshed")
            except Exception as err:
                failed += 1
                info, lines = diagnose.log_block(err, name)
                print("\n".join(lines))
                if conn is not None:
                    cms_db.add_scan_detail(conn, scan_id, "error", name, None, info["summary"], fix=info["fix"],
                                           trace=info["details"])
        if conn is not None and not args.no_tag:
            summary = tagger.tag_new_emails(conn, settings, say=say)
            record_tagging(conn, scan_id, summary)
    except Exception as err:
        if conn is not None:
            record_failure(conn, scan_id, err, "scan", read_total, new_total)
            conn.close()
        raise
    if conn is not None:
        cms_db.finish_scan_info(conn, scan_id, "failed" if failed else "ok", read_total, new_total,
                                summary["tagged"] if summary else 0, len(summary["important"]) if summary else 0,
                                f"{failed} mailbox(es) failed" if failed else "")
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
    ap.add_argument("--source", default="cli", choices=["schedule", "page", "cli"], help="who started this run")
    ap.add_argument("--log", help="append the output to this file (the scheduled task has no window)")
    args = ap.parse_args(argv)
    settings = cms_db.read_settings()
    if not args.log:
        return guarded(args, settings)
    log_path = Path(args.log)
    if not log_path.is_absolute():
        log_path = cms_db.ROOT / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8", buffering=1) as log:
        sys.stdout = sys.stderr = log
        print(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} ===")
        return guarded(args, settings)


def guarded(args, settings):
    """Runs the scan; a stop is written as ERROR (summary) / FIX (what to do) / DETAILS (folded on the page)."""
    try:
        return run(args, settings)
    except Exception as err:
        _info, lines = diagnose.log_block(err, "scan stopped")
        print("\n".join(lines))
        return 1


if __name__ == "__main__":
    sys.exit(main())
