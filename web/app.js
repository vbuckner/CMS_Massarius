// CMS Massarius page: plain JavaScript, talks to server.py on this PC only.
// The tabs only show / hide their sections; each section loads its data in the background (fetch),
// so switching tabs never throws away what you typed.
"use strict";
const $ = (sel) => document.querySelector(sel);
const PAGE = 100;
const state = { offset: 0, total: 0, selected: null, tags: [], info: null, tagsLoaded: false, emailsShown: false };

function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) node.append(kid);
  return node;
}

async function api(path, body) {
  const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data.error || res.statusText) + (data.fix ? "\n\nWhat to do: " + data.fix : ""));
  return data;
}

const store = {      // per-browser conveniences (may be unavailable in a private window)
  get(key, fallback) { try { const v = localStorage.getItem("cms." + key); return v === null ? fallback : v; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem("cms." + key, value); } catch { /* ignore */ } },
};

function short(dt) { return dt ? dt.slice(0, 16) : ""; }
function showError(err) { alert(err.message || err); }

// ------------------------------------------------ info icon
$("#info-btn").addEventListener("click", (e) => {
  e.stopPropagation();
  const pop = $("#info-pop"), open = pop.hidden;
  pop.hidden = !open;
  $("#info-btn").setAttribute("aria-expanded", String(open));
});
document.addEventListener("click", (e) => {      // capture: also closes when a button stops the click
  if (!$("#info-pop").hidden && !$("#info-pop").contains(e.target) && !$("#info-btn").contains(e.target)) {
    $("#info-pop").hidden = true;
    $("#info-btn").setAttribute("aria-expanded", "false");
  }
}, true);

// ------------------------------------------------ tabs (show / hide only)
function showTab(name) {
  document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => { t.hidden = t.id !== "tab-" + name; });
  if (name === "settings" && !state.tagsLoaded) loadTags();
  if (name === "scan") pollScan();
  if (name === "emails") return loadScans();
}
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

// Settings sub menu (Tags for now; more items can be added the same way)
document.querySelectorAll(".subtabs button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".subtabs button").forEach((x) => x.classList.toggle("active", x === b));
  document.querySelectorAll(".subtab").forEach((s) => { s.hidden = s.id !== "sub-" + b.dataset.sub; });
}));

// ------------------------------------------------ info + filters
async function loadInfo() {
  const info = await api("/api/info");
  state.info = info;
  state.tags = info.tags;
  $("#version").textContent = info.version;
  const acc = $("#f-account"), keepAcc = acc.value;
  acc.replaceChildren(el("option", { value: "" }, "All accounts"),
    ...info.accounts.map((a) => el("option", { value: a.account }, `${a.account} (${a.emails})`)));
  acc.value = keepAcc;
  const tg = $("#f-tag"), keepTag = tg.value;
  tg.replaceChildren(el("option", { value: "" }, "All tags"), el("option", { value: "none" }, "No tag"),
    el("option", { value: "important" }, "! Important (AnythingLLM)"),
    ...info.tags.map((t) => el("option", { value: t.id }, `${t.tag} (${t.emails})`)));
  tg.value = keepTag;
  if (!$("#s-boxes").children.length) {          // build once, so ticks you changed are kept
    $("#s-days").value = info.days;
    $("#s-boxes").replaceChildren(...info.mailboxes.map((m) =>
      el("label", {}, el("input", { type: "checkbox", value: m, checked: true }), " " + m)));
  }
}

// ------------------------------------------------ scan summary (Emails tab)
async function loadScans() {
  const pick = $("#sum-pick"), keep = pick.value;
  const scans = await api("/api/scans?days=14").catch(() => null);
  if (!scans) return;
  pick.replaceChildren(el("option", { value: "" }, scans.length ? "Choose a scan from the last two weeks..." : "No scans in the last two weeks"),
    ...scans.map((s) => el("option", { value: s.id }, scanLabel(s))));
  pick.value = keep;
}
function scanLabel(s) {
  const what = s.mode === "scan" ? `${s.days} day${s.days === 1 ? "" : "s"}, ${s.emails_new} new` : `${s.mode}, ${s.emails_tagged} tagged`;
  const imp = s.important ? `, ${s.important} important` : "";
  const status = s.status === "ok" ? "" : ` [${s.status}]`;
  return `${short(s.started_at)}  ${s.source}  ${what}${imp}${status}`;
}
$("#sum-pick").addEventListener("change", async () => {
  const id = $("#sum-pick").value, box = $("#sum-body");
  if (!id) { box.hidden = true; return; }
  box.hidden = false;
  box.replaceChildren(el("p", { class: "muted" }, "Loading..."));
  try { renderSummary(await api("/api/scans/" + id)); }
  catch (err) { box.replaceChildren(el("p", { class: "error" }, err.message)); }
});
function renderSummary(s) {
  const by = (kind) => s.details.filter((d) => d.kind === kind);
  const accounts = by("account"), tags = by("tag"), important = by("important"), notes = by("note"), errors = by("error");
  const meta = [`Started ${short(s.started_at)}`, s.finished_at ? `finished ${short(s.finished_at)}` : "still running",
    `by ${s.source}`, s.mode === "scan" ? `${s.days} day(s) back` : s.mode, `status ${s.status}`].join(" · ");
  const parts = [
    el("div", { class: "summary-meta" }, meta),
    s.mailboxes ? el("div", { class: "summary-meta muted" }, "Mailboxes: " + s.mailboxes) : null,
    s.message ? el("div", { class: "summary-meta error" }, s.message) : null,
    accounts.length ? [el("h4", {}, "Accounts"), el("table", {}, accounts.map((d) => el("tr", {}, el("td", {}, d.label), el("td", {}, d.text))))] : null,
    [el("h4", {}, `Tags given in this run (${s.emails_tagged} emails tagged)`),
      tags.length ? el("div", {}, tags.map((d) => el("span", { class: "count-chip" }, `${d.label} ${d.value}`))) : el("div", { class: "muted" }, "none")],
    [el("h4", {}, `Looks important (AnythingLLM) - ${important.length}`),
      important.length ? el("table", {}, important.map((d) => el("tr", { class: "clickable", title: "Show this email", onclick: () => showEmail(d.email_id) },
        el("td", {}, short(d.received_at)), el("td", {}, d.account || ""), el("td", {}, d.from_name || ""),
        el("td", {}, d.subject || "(no subject)"), el("td", { class: "why" }, d.text || ""))))
        : el("div", { class: "muted" }, "none flagged")],
    notes.length ? [el("h4", {}, "Notes"), notes.map((d) => el("div", { class: "muted" }, `${d.label}: ${d.text}${d.fix ? " - " + d.fix : ""}`))] : null,
    errors.length ? [el("h4", {}, "Errors"), errors.map((d) => el("div", { class: "err-row" },
      el("div", { class: "error" }, `${d.label}: ${d.text}${d.value ? " (" + d.value + ")" : ""}`),
      d.fix ? el("div", { class: "fix" }, "What to do: " + d.fix) : null,
      d.trace ? el("details", {}, el("summary", {}, "details"), el("pre", {}, d.trace)) : null))] : null];
  $("#sum-body").replaceChildren(...parts.flat(3).filter(Boolean));
}

// ------------------------------------------------ email list (hidden until you ask for it)
function chip(t, emailId, withActions) {
  const title = t.status === "auto" ? `auto (${t.source}${t.reason ? ": " + t.reason : ""})` : t.status;
  const node = el("span", { class: "chip " + t.status, title }, t.tag);
  if (withActions) {
    const act = (action, label, tip) => el("button", { title: tip, onclick: (e) => { e.stopPropagation(); setTag(emailId, t.tag_id, action); } }, label);
    if (t.status === "auto") node.append(act("confirm", "✓", "Keep this tag"), act("reject", "×", "Not this tag (the scan will not add it again)"));
    if (t.status === "manual") node.append(act("clear", "×", "Remove this tag"));
    if (t.status === "rejected") node.append(act("clear", "↺", "Undo the rejection"));
  }
  return node;
}

function showList() {
  state.emailsShown = true;
  $("#e-split").hidden = false;
  return loadEmails();
}

let searchTimer = null;
async function loadEmails() {
  const q = new URLSearchParams({ account: $("#f-account").value, tag: $("#f-tag").value, q: $("#f-search").value.trim(), limit: PAGE, offset: state.offset });
  try {
    const data = await api("/api/emails?" + q);
    state.total = data.total;
    $("#e-count").textContent = data.total ? `${state.offset + 1}-${state.offset + data.emails.length} of ${data.total}` : "no emails";
    $("#e-rows").replaceChildren(...data.emails.map((e) => el("tr", { class: e.id === state.selected ? "selected" : "", onclick: () => openDetail(e.id) },
      el("td", {}, short(e.received_at)),
      el("td", {}, e.account),
      el("td", { title: e.from_email || "" }, e.from_name || e.from_email || ""),
      el("td", {}, e.important ? el("span", { class: "imp", title: e.important_why || "looks important" }, "!") : null,
        (e.subject || "(no subject)") + (e.attachment_count ? " 📎" : "")),
      el("td", {}, e.tags.filter((t) => t.status !== "rejected").map((t) => chip(t, e.id, false))))));
    $("#e-prev").disabled = state.offset === 0;
    $("#e-next").disabled = state.offset + PAGE >= state.total;
  } catch (err) { $("#e-rows").replaceChildren(el("tr", {}, el("td", { colspan: 5, class: "error" }, err.message))); }
}
["#f-account", "#f-tag"].forEach((s) => $(s).addEventListener("change", () => { state.offset = 0; showList(); }));
$("#f-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { state.offset = 0; showList(); }, 300); });
$("#e-show").addEventListener("click", () => { state.offset = 0; showList(); });
$("#e-prev").addEventListener("click", () => { state.offset = Math.max(0, state.offset - PAGE); loadEmails(); });
$("#e-next").addEventListener("click", () => { state.offset += PAGE; loadEmails(); });

async function showEmail(id) {
  if (!state.emailsShown) await showList();
  $("#e-split").hidden = false;
  openDetail(id);
  $("#e-split").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ------------------------------------------------ email detail
async function openDetail(id) {
  state.selected = id;
  const e = await api("/api/emails/" + id).catch(showError);
  if (!e) return;
  const used = new Set(e.tags.map((t) => t.tag_id));
  const pick = el("select", {}, el("option", { value: "" }, "Add a tag..."),
    ...state.tags.filter((t) => t.active && !used.has(t.id)).map((t) => el("option", { value: t.id }, t.tag)));
  pick.addEventListener("change", () => pick.value && setTag(id, Number(pick.value), "add"));
  const box = $("#detail");
  box.hidden = false;
  box.replaceChildren(
    el("h2", {}, e.important ? el("span", { class: "imp" }, "!") : null, e.subject || "(no subject)"),
    el("dl", {},
      el("dt", {}, "Account"), el("dd", {}, e.account),
      el("dt", {}, "From"), el("dd", {}, `${e.from_name || ""} <${e.from_email || ""}>`),
      el("dt", {}, "To"), el("dd", {}, e.to_recipients || ""),
      e.cc_recipients ? [el("dt", {}, "CC"), el("dd", {}, e.cc_recipients)] : null,
      el("dt", {}, "Sent on"), el("dd", {}, short(e.sent_on)),
      el("dt", {}, "Received"), el("dd", {}, short(e.received_at)),
      el("dt", {}, "Folder"), el("dd", {}, e.folder || ""),
      e.attachment_count ? [el("dt", {}, "Attachments"), el("dd", {}, e.attachment_names)] : null,
      e.important ? [el("dt", {}, "Important"), el("dd", { class: "why" }, e.important_why || "yes (AnythingLLM)")] : null),
    el("div", { class: "tagbox" }, e.tags.map((t) => chip(t, id, true)), pick),
    el("div", { class: "legend muted" }, "Dashed = set by the scan (✓ keep, × not this). Filled = yours. Struck through = rejected."),
    el("div", { class: "actions" },
      e.open_link ? el("a", { href: e.open_link, target: "_blank", title: "Outlook marks the email as read when it opens" }, el("button", {}, "Open in Outlook")) : el("span", { class: "muted" }, "Outlook link comes with the next scan"),
      el("button", { title: "Replace the scan's tags on the next tagging run", onclick: () => api(`/api/emails/${id}/retag`, {}).then(() => alert("Queued: it is tagged again on the next scan or 'Tag untagged emails'.")).catch(showError) }, "Tag again")),
    el("div", { class: "body" }, e.body || ""));
  if (state.emailsShown) loadEmails();
}

async function setTag(emailId, tagId, action) {
  try {
    await api(`/api/emails/${emailId}/tags`, { tag_id: tagId, action });
    await openDetail(emailId);
  } catch (err) { showError(err); }
}

// ------------------------------------------------ tags tab
// Loaded once; after that each row is only replaced when you save it, so unsaved rows stay as they are.
async function loadTags() {
  const tags = await api("/api/tags").catch(showError);
  if (!tags) return;
  state.tags = tags;
  state.tagsLoaded = true;
  $("#t-rows").replaceChildren(...tags.map((t) => tagRow(t)));
}

function tagRow(t) {
  const isNew = !t.id;
  const f = {
    tag: el("input", { value: t.tag || "", placeholder: "name" }), description: el("input", { value: t.description || "" }),
    sender_patterns: el("textarea", {}, t.sender_patterns || ""), keyword_patterns: el("textarea", {}, t.keyword_patterns || ""),
    sort_order: el("input", { type: "number", value: t.sort_order ?? 0 }), active: el("input", { type: "checkbox", checked: t.active !== 0 }),
  };
  const cancel = el("button", { title: isNew ? "Remove this new line" : "Undo the changes in this line" }, "Cancel");
  const save = el("button", {}, "Save");
  const row = el("tr", { class: isNew ? "dirty" : "saved" },
    el("td", {}, f.tag), el("td", {}, f.description), el("td", {}, f.sender_patterns), el("td", {}, f.keyword_patterns),
    el("td", {}, f.sort_order), el("td", {}, f.active), el("td", {}, isNew ? "" : String(t.emails)), el("td", {}, save, cancel));
  cancel.hidden = !isNew;
  const markDirty = () => { row.classList.add("dirty"); row.classList.remove("saved"); cancel.hidden = false; };
  Object.values(f).forEach((input) => { input.addEventListener("input", markDirty); input.addEventListener("change", markDirty); });
  cancel.addEventListener("click", () => { if (isNew) row.remove(); else row.replaceWith(tagRow(t)); });
  save.addEventListener("click", async () => {
    try {
      const name = f.tag.value.trim().toLowerCase();
      const list = await api("/api/tags", { id: t.id, tag: f.tag.value, description: f.description.value, sender_patterns: f.sender_patterns.value,
        keyword_patterns: f.keyword_patterns.value, sort_order: f.sort_order.value, active: f.active.checked });
      state.tags = list;
      const saved = list.find((x) => (t.id ? x.id === t.id : x.tag === name));
      if (saved) row.replaceWith(tagRow(saved));
      loadInfo();
    } catch (err) { showError(err); }
  });
  return row;
}

function addTagRow() {
  const row = tagRow({ active: 1, sort_order: 100 });
  $("#t-rows").append(row);
  row.scrollIntoView({ behavior: "smooth", block: "center" });
  row.querySelector("input").focus({ preventScroll: true });
}
$("#t-add").addEventListener("click", addTagRow);
$("#t-add-top").addEventListener("click", addTagRow);

// ------------------------------------------------ scan tab
// The log: "!! ERROR" / "!! FIX" lines in red, the "!! DETAILS >>> ... !! <<<" block folded away.
function renderLog(lines) {
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("!! ERROR:")) out.push(el("div", { class: "err" }, line.slice(3)));
    else if (line.startsWith("!! FIX:")) out.push(el("div", { class: "fix" }, "What to do:" + line.slice(7)));
    else if (line === "!! DETAILS >>>") {
      const body = [];
      while (++i < lines.length && lines[i] !== "!! <<<") body.push(lines[i]);
      out.push(el("details", {}, el("summary", {}, "error details (click to open)"), el("pre", {}, body.join("\n"))));
    } else out.push(el("div", {}, line || " "));
  }
  const box = $("#s-log");
  box.replaceChildren(...out);
  box.scrollTop = box.scrollHeight;
}

let pollTimer = null;
async function pollScan() {
  clearTimeout(pollTimer);
  const s = await api("/api/scan?since=" + Number(store.get("logSince", 0))).catch(() => null);
  if (!s) return;
  state.logSize = s.size;
  renderLog(s.log);
  $("#s-spinner").hidden = !s.running;
  $("#s-state").textContent = s.running ? "scanning..." : "";
  $("#s-run").disabled = $("#s-tagnow").disabled = s.running;
  if (s.running) pollTimer = setTimeout(pollScan, 1500);
  else if (state.wasRunning) scanFinished();
  state.wasRunning = s.running;
}

async function scanFinished() {
  loadInfo();
  if (state.emailsShown) loadEmails();
  await showTab("emails");                       // jump to the Emails tab and show this run's summary
  const first = $("#sum-pick").options[1];
  if (first) { $("#sum-pick").value = first.value; $("#sum-pick").dispatchEvent(new Event("change")); }
}

$("#s-clear").addEventListener("click", (e) => {
  e.preventDefault();                            // the button sits in the log's fold-out header
  store.set("logSince", state.logSize || 0);
  $("#s-log").replaceChildren();
});
$("#s-run").addEventListener("click", async () => {
  const mailboxes = [...document.querySelectorAll("#s-boxes input:checked")].map((i) => i.value);
  try { await api("/api/scan", { mailboxes, days: Number($("#s-days").value), tag: $("#s-tag").checked }); pollScan(); }
  catch (err) { showError(err); }
});
$("#s-tagnow").addEventListener("click", async () => {
  try { await api("/api/tag-now", {}); pollScan(); } catch (err) { showError(err); }
});

// ------------------------------------------------ start
loadInfo().then(loadScans).catch((err) => { $("#e-count").textContent = err.message; });
