"""Reads email from the running (classic) Outlook through its COM interface (pywin32).

Read only: nothing is moved, flagged, marked read or saved in Outlook.
Folders read per mailbox: the Inbox with its sub folders, and Sent Items when the mailbox has one.
The Outlook EntryID and StoreID are kept so the web page can open the email in Outlook later.
"""
import time
from datetime import datetime, timedelta, timezone

OL_INBOX, OL_SENT = 6, 5            # OlDefaultFolders
OL_MAIL = 43                        # OlObjectClass.olMail
PR_INTERNET_MESSAGE_ID = "http://schemas.microsoft.com/mapi/proptag/0x1035001F"
PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001F"          # on a recipient
PR_SENDER_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x5D01001F"   # on an email


def outlook():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()        # needed in every thread that talks to Outlook (the web server uses threads)
    return win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")


def mailbox_names(ns=None):
    ns = ns or outlook()
    return [ns.Stores.Item(i).DisplayName for i in range(1, ns.Stores.Count + 1)]


def local_time(value):
    """pywin32 hands Outlook times back as local time wrongly marked UTC: drop the zone."""
    if value is None:
        return None
    try:
        dt = datetime(value.year, value.month, value.day, value.hour, value.minute, value.second)
    except (AttributeError, ValueError):
        return None
    return None if dt.year >= 4501 else dt          # Outlook's "no date" is 4501-01-01


def smtp_address(address_entry, fallback=""):
    """The real e-mail address; Exchange users otherwise show as a long /o=ExchangeLabs/... path."""
    try:
        if address_entry is None:
            return fallback
        if address_entry.Type == "EX":
            user = address_entry.GetExchangeUser()
            if user is not None and user.PrimarySmtpAddress:
                return user.PrimarySmtpAddress
            dist = address_entry.GetExchangeDistributionList()
            if dist is not None and dist.PrimarySmtpAddress:
                return dist.PrimarySmtpAddress
        return address_entry.Address or fallback
    except Exception:
        return fallback


def recipients(item, kind):
    """'Name <address>; ...' for To (kind 1) or CC (kind 2).
    The address is read from the email itself (PR_SMTP_ADDRESS): about 20x quicker than looking every recipient up
    in the address book, which took ~1 s per email. The address book is only asked when the email has no address."""
    out = []
    for i in range(1, item.Recipients.Count + 1):
        r = item.Recipients.Item(i)
        if r.Type == kind:
            try:
                address = r.PropertyAccessor.GetProperty(PR_SMTP_ADDRESS)
            except Exception:
                address = ""
            out.append(f"{r.Name} <{address or smtp_address(r.AddressEntry, r.Address or '')}>")
    return "; ".join(out)


def sender_address(item):
    try:
        address = item.PropertyAccessor.GetProperty(PR_SENDER_SMTP_ADDRESS)
        if address:
            return address
    except Exception:
        pass
    return smtp_address(item.Sender, item.SenderEmailAddress or "")


def message_id(item):
    try:
        mid = item.PropertyAccessor.GetProperty(PR_INTERNET_MESSAGE_ID)
        if mid:
            return mid.strip()
    except Exception:
        pass
    return "entry:" + item.EntryID          # drafts and some internal mails have no Message-ID


def find_store(ns, name):
    for i in range(1, ns.Stores.Count + 1):
        store = ns.Stores.Item(i)
        if store.DisplayName.lower() == name.lower():
            return store
    raise LookupError(f"mailbox {name!r} is not open in Outlook. Outlook has: " + ", ".join(mailbox_names(ns)))


def folders_to_read(store):
    result = []

    def walk(folder, path):
        result.append((path, folder))
        for i in range(1, folder.Folders.Count + 1):
            sub = folder.Folders.Item(i)
            walk(sub, f"{path}/{sub.Name}")

    for kind in (OL_INBOX, OL_SENT):
        try:
            top = store.GetDefaultFolder(kind)
        except Exception:
            continue                     # e.g. a shared mailbox without its own Sent Items
        if kind == OL_INBOX:
            walk(top, top.Name)
        else:
            result.append((top.Name, top))
    return result


def read_mailbox(name, days, ns=None, say=None):
    """(account, rows, skipped, per_folder) for the last `days` days of one mailbox.
    say: optional function for progress lines (folder names and counts only)."""
    ns = ns or outlook()
    store = find_store(ns, name)
    account = store.DisplayName
    store_id = store.StoreID
    since_utc = datetime.now(timezone.utc) - timedelta(days=days)
    # Outlook filters on the server side: much quicker than walking a big folder.
    date_filter = '@SQL="urn:schemas:httpmail:datereceived" >= \'%s\'' % since_utc.strftime("%Y-%m-%d %H:%M")
    now = datetime.now().replace(microsecond=0)
    rows, skipped, per_folder = {}, 0, []

    if say:
        say(f"{account}: listing folders")
    folders = folders_to_read(store)
    if say:
        say(f"{account}: {len(folders)} folders")
    for path, folder in folders:
        count = 0
        started = time.time()
        try:
            items = folder.Items.Restrict(date_filter)
            if say and items.Count:
                say(f"  {path}: {items.Count} items in range ({time.time() - started:.1f}s)")
        except Exception:
            per_folder.append((path, "could not be filtered"))
            continue
        item = items.GetFirst()
        while item is not None:
            if say and count and count % 25 == 0:
                say(f"    {count} read ({time.time() - started:.1f}s)")
            if getattr(item, "Class", None) != OL_MAIL:
                skipped += 1                          # meeting requests, read receipts, ...
            else:
                mid = message_id(item)
                if mid not in rows:                   # the same mail in two folders: keep the first
                    names = [item.Attachments.Item(i).FileName for i in range(1, item.Attachments.Count + 1)]
                    rows[mid] = {
                        "account": account, "message_id": mid[:500], "folder": path[:500],
                        "sent_on": local_time(item.SentOn), "received_at": local_time(item.ReceivedTime),
                        "from_name": (item.SenderName or "")[:255],
                        "from_email": sender_address(item)[:255],
                        "to_recipients": recipients(item, 1), "cc_recipients": recipients(item, 2),
                        "subject": (item.Subject or "")[:1000], "body": item.Body or "",
                        "attachment_count": len(names), "attachment_names": "; ".join(names),
                        "conversation_id": (item.ConversationID or "")[:255],
                        "categories": (item.Categories or "")[:500],
                        "importance": item.Importance, "is_read": 0 if item.UnRead else 1,
                        "entry_id": item.EntryID, "store_id": store_id, "loaded_at": now,
                    }
                    count += 1
            item = items.GetNext()
        per_folder.append((path, count))
    return account, list(rows.values()), skipped, per_folder


def open_in_outlook(entry_id, store_id):
    """Shows the email in an Outlook window. Note: Outlook marks an email read when it is opened."""
    ns = outlook()
    ns.GetItemFromID(entry_id, store_id).Display()
