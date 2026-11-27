"""Auto tagging, all on this PC.

1. Rules: each tag in lookup_tags has sender patterns (part of the sender address) and subject keywords.
2. AnythingLLM (local, Qwen): asked to pick tags from the same list for each email. Used when settings.json has
   "llmTagging": true and the credentials file anythingllm.json exists: {"url": "http://localhost:3001", "apiKey": "..."}
   (make the key in AnythingLLM: Settings > Developer API). If AnythingLLM is not running, only the rules are used.

The result goes in email_tags with status 'auto'. Tags you set or rejected on the web page are never changed.
"""
import json
import re
import urllib.error
import urllib.request

import cms_db


# ---------------------------------------------------------------- rules

def rule_tags(email, tags):
    sender = (email.get("from_email") or "").lower() + " " + (email.get("from_name") or "").lower()
    subject = (email.get("subject") or "").lower()
    found = []
    for t in tags:
        hit = next((p for p in t["senders"] if p in sender), None)
        if hit:
            found.append((t["id"], "rules", f"sender matches {hit}"))
            continue
        hit = next((k for k in t["keywords"] if k in subject), None)
        if hit:
            found.append((t["id"], "rules", f"subject has '{hit}'"))
    return found


# ---------------------------------------------------------------- AnythingLLM

class AnythingLLM:
    def __init__(self, settings):
        path = cms_db.credentials_file(settings, "anythingllmCredentialsFile")
        creds = json.loads(path.read_text(encoding="utf-8-sig"))
        self.url = (creds.get("url") or "http://localhost:3001").rstrip("/")
        self.key = creds.get("apiKey") or creds.get("api_key") or creds.get("key")
        if not self.key:
            raise ValueError(f"{path.name} has no apiKey")
        self.workspace = settings["anythingllmWorkspace"]

    def _call(self, method, path, body=None, timeout=300):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
                                              "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")

    def check(self):
        """Raises when AnythingLLM is not reachable or the key is wrong; makes the workspace when it is missing."""
        self._call("GET", "/api/v1/auth", timeout=10)
        found = self._call("GET", f"/api/v1/workspace/{self.workspace}", timeout=10)
        ws = found.get("workspace")
        if not ws:                                   # [] or None when there is no such workspace
            made = self._call("POST", "/api/v1/workspace/new", {"name": self.workspace}, timeout=30)
            self.workspace = made["workspace"]["slug"]

    def ask(self, system, user):
        try:
            reply = self._call("POST", "/api/v1/openai/chat/completions",
                               {"model": self.workspace, "temperature": 0, "stream": False,
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
            return reply["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as err:
            if err.code != 404:
                raise
        reply = self._call("POST", f"/api/v1/workspace/{self.workspace}/chat",
                           {"message": system + "\n\n" + user, "mode": "chat", "sessionId": "cms-tagger"})
        return reply.get("textResponse") or ""


SYSTEM = ("You sort emails for Massarius, an ad-tech company that helps publishers earn from advertising. "
          "Pick every tag from the list that fits the email; pick none if nothing fits. "
          "Reply with JSON only, like {\"tags\": [\"ssp\", \"invoice\"]}. /no_think")


def llm_tags(llm, email, tags, body_chars):
    listing = "\n".join(f"- {t['tag']}: {t['description']}" for t in tags)
    text = (f"Tags:\n{listing}\n\nEmail\nFrom: {email.get('from_name') or ''} <{email.get('from_email') or ''}>\n"
            f"To: {(email.get('to_recipients') or '')[:300]}\nSubject: {email.get('subject') or ''}\n\n"
            f"{(email.get('body') or '')[:body_chars]}")
    answer = llm.ask(SYSTEM, text)
    answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.S)
    match = re.search(r"\{.*\}", answer, flags=re.S)
    names = []
    if match:
        try:
            names = json.loads(match.group(0)).get("tags", [])
        except (ValueError, AttributeError):
            names = []
    by_name = {t["tag"]: t["id"] for t in tags}
    return [(by_name[n.lower()], "llm", "AnythingLLM") for n in names if isinstance(n, str) and n.lower() in by_name]


# ---------------------------------------------------------------- run

def tag_new_emails(conn, settings, say=print):
    """Tags every email that has not been tagged yet (new ones, or ones sent back with 'tag again')."""
    tags = cms_db.active_tags(conn)
    emails = cms_db.emails_to_tag(conn)
    if not emails:
        say("tagging: nothing new to tag")
        return
    llm = None
    if settings.get("llmTagging"):
        try:
            llm = AnythingLLM(settings)
            llm.check()
        except FileNotFoundError:
            say("tagging: AnythingLLM not used - no anythingllm.json in the credentials folder (rules only)")
            llm = None
        except Exception as err:
            say(f"tagging: AnythingLLM not used - {type(err).__name__}: {err} (rules only)")
            llm = None
    counts = {"rules": 0, "llm": 0, "llm_errors": 0}
    for email in emails:
        proposals = rule_tags(email, tags)
        if llm is not None:
            try:
                ruled = {p[0] for p in proposals}
                extra = [p for p in llm_tags(llm, email, tags, settings.get("llmBodyChars", 2000)) if p[0] not in ruled]
                proposals += extra
                counts["llm"] += len(extra)
            except Exception:
                counts["llm_errors"] += 1
        counts["rules"] += sum(1 for p in proposals if p[1] == "rules")
        cms_db.save_auto_tags(conn, email["id"], proposals)
    say(f"tagging: {len(emails)} emails, {counts['rules']} tags from rules, {counts['llm']} from AnythingLLM"
        + (f", {counts['llm_errors']} AnythingLLM errors" if counts["llm_errors"] else ""))
