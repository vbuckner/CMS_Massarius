"""Tests with made-up emails in a separate database, cms_db_test (never cms_db).

    python -m unittest tests.test_cms -v          (MySQL80 must be running)

Also leaves cms_db_test filled with the fake emails, so the web page can be looked at without real mail:
    set CMS_DATABASE=cms_db_test  then  python server.py
"""
import unittest
from datetime import datetime, timedelta

import cms_db
import tagger

TEST_DB = "cms_db_test"


def fake(n, **over):
    now = datetime(2026, 11, 27, 9, 0)
    row = {"account": "Test | Box", "message_id": f"<fake-{n}@example.test>", "folder": "Inbox",
           "sent_on": now - timedelta(hours=n), "received_at": now - timedelta(hours=n),
           "from_name": f"Sender {n}", "from_email": f"sender{n}@example.test", "to_recipients": "Me <me@example.test>",
           "cc_recipients": "", "subject": f"Fake email {n}", "body": f"Body of fake email {n}.", "attachment_count": 0,
           "attachment_names": "", "conversation_id": "", "categories": "", "importance": 1, "is_read": 1,
           "entry_id": f"ENTRY{n}", "store_id": "STORE", "loaded_at": now}
    row.update(over)
    return row


class CmsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = dict(cms_db.read_settings(), database=TEST_DB, llmTagging=False)
        cls.conn = cms_db.connect(cls.settings)
        cur = cls.conn.cursor()
        for t in ("email_tags", "emails", "lookup_tags"):
            cur.execute(f"DROP TABLE IF EXISTS {t}")
        cms_db.ensure_tables(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_1_save_insert_then_refresh_keeps_id(self):
        rows = [fake(1, from_email="anna@massarius.com", subject="Lunch"),
                fake(2, from_email="reports@pubmatic.com", subject="Your daily report"),
                fake(3, subject="Invoice 2026-11 attached"),
                fake(4)]
        self.assertEqual(cms_db.save_emails(self.conn, rows), (4, 0))
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM emails WHERE message_id = '<fake-1@example.test>'")
        first_id = cur.fetchone()[0]
        rows[0]["subject"] = "Lunch (changed)"
        self.assertEqual(cms_db.save_emails(self.conn, rows), (0, 4))
        cur.execute("SELECT id, subject, updated_at IS NOT NULL FROM emails WHERE message_id = '<fake-1@example.test>'")
        self.assertEqual(cur.fetchone(), (first_id, "Lunch (changed)", 1))

    def test_2_rules_tagging(self):
        tagger.tag_new_emails(self.conn, self.settings, say=lambda _t: None)
        got = {}
        for e in cms_db.list_emails(self.conn, limit=50)[1]:
            got[e["from_email"]] = sorted(t["tag"] for t in e["tags"])
        self.assertEqual(got["anna@massarius.com"], ["internal"])
        self.assertEqual(got["reports@pubmatic.com"], ["dashboard", "ssp"])
        self.assertEqual(got["sender3@example.test"], ["invoice"])
        self.assertEqual(got["sender4@example.test"], [])
        self.assertEqual(cms_db.emails_to_tag(self.conn), [])

    def test_3_amendments_survive_retagging(self):
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM emails WHERE from_email = 'reports@pubmatic.com'")
        email_id = cur.fetchone()[0]
        tag_id = {t["tag"]: t["id"] for t in cms_db.list_tags(self.conn)}
        cms_db.set_tag(self.conn, email_id, tag_id["dashboard"], "reject")
        cms_db.set_tag(self.conn, email_id, tag_id["client"], "add")
        cms_db.set_tag(self.conn, email_id, tag_id["ssp"], "confirm")
        cms_db.retag(self.conn, [email_id])
        tagger.tag_new_emails(self.conn, self.settings, say=lambda _t: None)
        tags = {t["tag"]: t["status"] for t in cms_db.get_email(self.conn, email_id)["tags"]}
        self.assertEqual(tags, {"dashboard": "rejected", "client": "manual", "ssp": "manual"})
        cms_db.set_tag(self.conn, email_id, tag_id["dashboard"], "clear")
        cms_db.retag(self.conn, [email_id])
        tagger.tag_new_emails(self.conn, self.settings, say=lambda _t: None)
        tags = {t["tag"]: t["status"] for t in cms_db.get_email(self.conn, email_id)["tags"]}
        self.assertEqual(tags["dashboard"], "auto")

    def test_4_filters(self):
        tag_id = {t["tag"]: t["id"] for t in cms_db.list_tags(self.conn)}
        total, _ = cms_db.list_emails(self.conn, tag_id=str(tag_id["invoice"]))
        self.assertEqual(total, 1)
        total, _ = cms_db.list_emails(self.conn, tag_id="none")
        self.assertEqual(total, 1)
        total, _ = cms_db.list_emails(self.conn, search="Lunch")
        self.assertEqual(total, 1)

    def test_5_llm_reply_parsing(self):
        class FakeLLM:
            def ask(self, system, user):
                return '<think>hmm</think>\n{"tags": ["SSP", "nope", "client"]}'
        tags = cms_db.active_tags(self.conn)
        got = sorted(t for t, _s, _r in tagger.llm_tags(FakeLLM(), fake(9), tags, 100))
        ids = {t["tag"]: t["id"] for t in tags}
        self.assertEqual(got, sorted([ids["ssp"], ids["client"]]))


if __name__ == "__main__":
    unittest.main()
