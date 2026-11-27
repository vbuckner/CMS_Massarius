// CMS Massarius page: plain JavaScript, talks to server.py on this PC only.
"use strict";
const $ = (sel) => document.querySelector(sel);
const PAGE = 100;
const state = { offset: 0, total: 0, selected: null, tags: [], info: null };

function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined) node.append(kid);
  return node;
}

async function api(path, body) {
  const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

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

// ------------------------------------------------ tabs
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
  document.querySelectorAll(".tab").forEach((t) => { t.hidden = t.id !== "tab-" + b.dataset.tab; });
  if (b.dataset.tab === "tags") loadTags();
  if (b.dataset.tab === "scan") pollScan();
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
    ...info.tags.map((t) => el("option", { value: t.id }, `${t.tag} (${t.emails})`)));
  tg.value = keepTag;
  $("#s-days").value = info.days;
  $("#s-boxes").replaceChildren(...info.mailboxes.map((m) =>
    el("label", {}, el("input", { type: "checkbox", value: m, checked: true }), " " + m)));
}

// ------------------------------------------------ email list
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
      el("td", {}, (e.subject || "(no subject)") + (e.attachment_count ? " 📎" : "")),
      el("td", {}, e.tags.filter((t) => t.status !== "rejected").map((t) => chip(t, e.id, false))))));
    $("#e-prev").disabled = state.offset === 0;
    $("#e-next").disabled = state.offset + PAGE >= state.total;
  } catch (err) { $("#e-rows").replaceChildren(el("tr", {}, el("td", { colspan: 5, class: "error" }, err.message))); }
}
["#f-account", "#f-tag"].forEach((s) => $(s).addEventListener("change", () => { state.offset = 0; loadEmails(); }));
$("#f-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { state.offset = 0; loadEmails(); }, 300); });
$("#e-prev").addEventListener("click", () => { state.offset = Math.max(0, state.offset - PAGE); loadEmails(); });
$("#e-next").addEventListener("click", () => { state.offset += PAGE; loadEmails(); });

// ------------------------------------------------ email detail
async function openDetail(id) {
  state.selected = id;
  document.querySelectorAll("#e-rows tr").forEach((tr) => tr.classList.remove("selected"));
  const e = await api("/api/emails/" + id).catch(showError);
  if (!e) return;
  const used = new Set(e.tags.map((t) => t.tag_id));
  const pick = el("select", {}, el("option", { value: "" }, "Add a tag..."),
    ...state.tags.filter((t) => t.active && !used.has(t.id)).map((t) => el("option", { value: t.id }, t.tag)));
  pick.addEventListener("change", () => pick.value && setTag(id, Number(pick.value), "add"));
  const box = $("#detail");
  box.hidden = false;
  box.replaceChildren(
    el("h2", {}, e.subject || "(no subject)"),
    el("dl", {},
      el("dt", {}, "Account"), el("dd", {}, e.account),
      el("dt", {}, "From"), el("dd", {}, `${e.from_name || ""} <${e.from_email || ""}>`),
      el("dt", {}, "To"), el("dd", {}, e.to_recipients || ""),
      e.cc_recipients ? [el("dt", {}, "CC"), el("dd", {}, e.cc_recipients)] : null,
      el("dt", {}, "Sent on"), el("dd", {}, short(e.sent_on)),
      el("dt", {}, "Received"), el("dd", {}, short(e.received_at)),
      el("dt", {}, "Folder"), el("dd", {}, e.folder || ""),
      e.attachment_count ? [el("dt", {}, "Attachments"), el("dd", {}, e.attachment_names)] : null),
    el("div", { class: "tagbox" }, e.tags.map((t) => chip(t, id, true)), pick),
    el("div", { class: "legend muted" }, "Dashed = set by the scan (✓ keep, × not this). Filled = yours. Struck through = rejected."),
    el("div", { class: "actions" },
      e.open_link ? el("a", { href: e.open_link, target: "_blank", title: "Outlook marks the email as read when it opens" }, el("button", {}, "Open in Outlook")) : el("span", { class: "muted" }, "Outlook link comes with the next scan"),
      el("button", { title: "Replace the scan's tags on the next tagging run", onclick: () => api(`/api/emails/${id}/retag`, {}).then(() => alert("Queued: it is tagged again on the next scan or 'Tag untagged emails'.")).catch(showError) }, "Tag again")),
    el("div", { class: "body" }, e.body || ""));
  loadEmails();
}

async function setTag(emailId, tagId, action) {
  try {
    await api(`/api/emails/${emailId}/tags`, { tag_id: tagId, action });
    await openDetail(emailId);
  } catch (err) { showError(err); }
}

// ------------------------------------------------ tags tab
async function loadTags() {
  const tags = await api("/api/tags").catch(showError);
  if (!tags) return;
  state.tags = tags;
  $("#t-rows").replaceChildren(...tags.map(tagRow));
}
function tagRow(t) {
  const f = {
    tag: el("input", { value: t.tag || "" }), description: el("input", { value: t.description || "" }),
    sender_patterns: el("textarea", {}, t.sender_patterns || ""), keyword_patterns: el("textarea", {}, t.keyword_patterns || ""),
    sort_order: el("input", { type: "number", value: t.sort_order ?? 0 }), active: el("input", { type: "checkbox", checked: t.active !== 0 }),
  };
  const save = el("button", { onclick: async () => {
    try {
      await api("/api/tags", { id: t.id, tag: f.tag.value, description: f.description.value, sender_patterns: f.sender_patterns.value,
        keyword_patterns: f.keyword_patterns.value, sort_order: f.sort_order.value, active: f.active.checked });
      await loadTags(); await loadInfo();
    } catch (err) { showError(err); }
  } }, "Save");
  return el("tr", {}, el("td", {}, f.tag), el("td", {}, f.description), el("td", {}, f.sender_patterns), el("td", {}, f.keyword_patterns),
    el("td", {}, f.sort_order), el("td", {}, f.active), el("td", {}, t.id ? String(t.emails) : ""), el("td", {}, save));
}
$("#t-add").addEventListener("click", () => $("#t-rows").append(tagRow({ active: 1, sort_order: 100 })));

// ------------------------------------------------ scan tab
let pollTimer = null;
async function pollScan() {
  clearTimeout(pollTimer);
  const s = await api("/api/scan").catch(() => null);
  if (!s) return;
  $("#s-log").textContent = s.log.join("\n");
  $("#s-log").scrollTop = $("#s-log").scrollHeight;
  $("#s-state").textContent = s.running ? "(running...)" : "";
  $("#s-run").disabled = $("#s-tagnow").disabled = s.running;
  if (s.running) pollTimer = setTimeout(pollScan, 1500);
  else if (state.wasRunning) { loadInfo(); loadEmails(); }
  state.wasRunning = s.running;
}
$("#s-run").addEventListener("click", async () => {
  const mailboxes = [...document.querySelectorAll("#s-boxes input:checked")].map((i) => i.value);
  try { await api("/api/scan", { mailboxes, days: Number($("#s-days").value), tag: $("#s-tag").checked }); pollScan(); }
  catch (err) { showError(err); }
});
$("#s-tagnow").addEventListener("click", async () => {
  try { await api("/api/tag-now", {}); pollScan(); } catch (err) { showError(err); }
});

// ------------------------------------------------ start
loadInfo().then(loadEmails).catch((err) => { $("#e-rows").replaceChildren(el("tr", {}, el("td", { colspan: 5, class: "error" }, err.message))); });
