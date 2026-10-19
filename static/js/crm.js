/* ════════════════════════════════════════════════════════
   crm.js — CRM tracking and Google Sheets sync
   ════════════════════════════════════════════════════════ */

let _crmRecords = [];
let _crmFilteredRecords = [];
let _crmSearchTerm = "";
let _crmSearchTimer = null;

async function buildCRMUI() {
  const container = document.getElementById("crm-content");
  container.replaceChildren();

  const bar = document.createElement("div");
  bar.style.cssText = "display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap";

  const syncBtn = document.createElement("button");
  syncBtn.className = "btn btn-primary";
  syncBtn.textContent = "📊 Sync to Google Sheets";
  syncBtn.addEventListener("click", syncSheets);

  const csvBtn = document.createElement("button");
  csvBtn.className = "btn btn-ghost";
  csvBtn.textContent = "⬇ Download CSV";
  csvBtn.addEventListener("click", downloadCSV);

  const followupBtn = document.createElement("button");
  followupBtn.className = "btn btn-outline";
  followupBtn.textContent = "🔔 Check Follow-ups";
  followupBtn.addEventListener("click", checkFollowups);

  bar.append(syncBtn, csvBtn, followupBtn);

  const sheetsGuide = document.createElement("div");
  sheetsGuide.id = "sheets-setup-guide";
  sheetsGuide.className = "card";
  sheetsGuide.style.cssText = "display:none;border-color:var(--warning);background:#fffbeb;margin-bottom:16px";

  const guideTitle = document.createElement("div");
  guideTitle.className = "card-title";
  guideTitle.textContent = "⚙️ Google Sheets Setup Required";

  const guideBody = document.createElement("div");
  guideBody.style.cssText = "font-size:13.5px;line-height:1.8;color:var(--text)";

  const steps = [
    ["1. Go to ", "Google Cloud Console", " → IAM & Admin → Service Accounts → Create Service Account"],
    ["2. Grant it no IAM role (it only needs Sheets access, not GCP access)"],
    ["3. Under Keys → Add Key → JSON → download the file"],
    ["4. Rename the file to ", "google-service-account.json", " and place it in the project root (next to ", "main.py", ")"],
    ["5. Open your Google Sheet → Share → paste the service account email (ends in @…iam.gserviceaccount.com) and grant Editor access"],
    ["6. Paste the Sheet ID in Settings (the part between /d/ and /edit in the URL)"],
    ["7. Click Sync to Google Sheets again"],
  ];

  steps.forEach((parts) => {
    const p = document.createElement("p");
    p.style.margin = "4px 0";
    parts.forEach((part, idx) => {
      if (idx % 2 === 1) {
        const code = document.createElement("code");
        code.style.cssText = "background:#f3f4f6;padding:1px 5px;border-radius:3px;font-size:12.5px";
        code.textContent = part;
        p.appendChild(code);
      } else {
        p.appendChild(document.createTextNode(part));
      }
    });
    guideBody.appendChild(p);
  });

  const csvFallback = document.createElement("p");
  csvFallback.style.cssText = "margin-top:12px;font-size:12.5px;color:var(--text-muted)";
  csvFallback.textContent = "In the meantime, use ⬇ Download CSV to export your records.";
  guideBody.appendChild(csvFallback);

  sheetsGuide.append(guideTitle, guideBody);
  container.appendChild(sheetsGuide);
  container.appendChild(bar);

  const fuCard = document.createElement("div");
  fuCard.className = "card";
  fuCard.id = "followups-card";
  fuCard.style.cssText = "display:none;border-color:var(--warning);background:#fffbeb";

  const fuTitle = document.createElement("div");
  fuTitle.className = "card-title";
  fuTitle.textContent = "🔔 Follow-ups Due";

  const fuBody = document.createElement("div");
  fuBody.id = "followups-body";

  fuCard.append(fuTitle, fuBody);
  container.appendChild(fuCard);

  const stats = document.createElement("div");
  stats.className = "stats-grid";
  stats.style.gridTemplateColumns = "repeat(4,1fr)";
  stats.id = "crm-stats";
  container.appendChild(stats);

  const tableCard = document.createElement("div");
  tableCard.className = "card";
  tableCard.id = "crm-table-card";
  container.appendChild(tableCard);

  loadCRM();
}

async function loadCRM() {
  try {
    _crmRecords = await API.get("/api/crm");
    _crmFilteredRecords = _crmRecords.slice();
    renderStats(_crmRecords);
    renderTableSection();
  } catch (e) {
    toast("Failed to load CRM: " + e.message, "error");
  }
}

function renderStats(records) {
  const stats = document.getElementById("crm-stats");
  if (!stats) return;

  const counts = { sent: 0, replied: 0, follow_up: 0, closed: 0 };
  records.forEach((r) => { if (counts[r.status] !== undefined) counts[r.status]++; });

  const defs = [
    { label: "Sent", key: "sent", icon: "📤" },
    { label: "Replied", key: "replied", icon: "💬" },
    { label: "Follow-up", key: "follow_up", icon: "🔔" },
    { label: "Closed", key: "closed", icon: "✅" },
  ];

  stats.replaceChildren();
  defs.forEach(({ label, key, icon }) => {
    const card = document.createElement("div");
    card.className = "stat-card";

    const iconEl = document.createElement("div");
    iconEl.className = "stat-icon";
    iconEl.textContent = icon;

    const val = document.createElement("div");
    val.className = "stat-value";
    val.textContent = counts[key];

    const lbl = document.createElement("div");
    lbl.className = "stat-label";
    lbl.textContent = label;

    card.append(iconEl, val, lbl);
    stats.appendChild(card);
  });
}

function renderTableSection() {
  const card = document.getElementById("crm-table-card");
  if (!card) return;
  card.replaceChildren();

  const header = document.createElement("div");
  header.style.cssText = "display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:16px";

  const titleWrap = document.createElement("div");
  const title = document.createElement("div");
  title.className = "card-title";
  title.textContent = `${_crmRecords.length} Outreach Records`;

  const summary = document.createElement("div");
  summary.id = "crm-search-summary";
  summary.style.cssText = "font-size:12.5px;color:var(--text-muted);margin-top:6px";
  summary.textContent = `Showing ${_crmFilteredRecords.length} of ${_crmRecords.length} records`;

  titleWrap.append(title, summary);

  const searchWrap = document.createElement("div");
  searchWrap.style.cssText = "display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0;flex:1;justify-content:flex-end";

  const searchInput = document.createElement("input");
  searchInput.type = "text";
  searchInput.id = "crm-search-input";
  searchInput.placeholder = "Search by company, email, subject, status...";
  searchInput.value = _crmSearchTerm;
  searchInput.style.cssText = "min-width:0;flex:1 1 320px;max-width:460px";
  searchInput.addEventListener("input", () => {
    clearTimeout(_crmSearchTimer);
    _crmSearchTimer = setTimeout(() => {
      _crmSearchTerm = searchInput.value || "";
      filterCRMRecords();
    }, 150);
  });

  const clearBtn = document.createElement("button");
  clearBtn.className = "btn btn-ghost btn-sm";
  clearBtn.textContent = "Clear";
  clearBtn.addEventListener("click", () => {
    _crmSearchTerm = "";
    searchInput.value = "";
    filterCRMRecords();
  });

  searchWrap.append(searchInput, clearBtn);
  header.append(titleWrap, searchWrap);
  card.appendChild(header);

  const list = document.createElement("div");
  list.id = "crm-record-list";
  card.appendChild(list);

  renderRecordsList();
}

function filterCRMRecords() {
  const term = _crmSearchTerm.trim().toLowerCase();
  if (!term) {
    _crmFilteredRecords = _crmRecords.slice();
  } else {
    _crmFilteredRecords = _crmRecords.filter((record) => {
      const haystack = [
        record.company_name,
        record.company_email,
        record.email_subject,
        record.status,
        record.notes,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(term);
    });
  }
  updateCRMSearchSummary();
  renderRecordsList();
}

function updateCRMSearchSummary() {
  const summary = document.getElementById("crm-search-summary");
  if (!summary) return;
  summary.textContent = `Showing ${_crmFilteredRecords.length} of ${_crmRecords.length} records`;
}

function renderRecordsList() {
  const list = document.getElementById("crm-record-list");
  if (!list) return;
  list.replaceChildren();

  if (!_crmRecords.length) {
    list.appendChild(makeCRMEmptyState("📊", "No outreach records yet", "Send emails from the Email Sender to create CRM records."));
    return;
  }

  if (!_crmFilteredRecords.length) {
    list.appendChild(makeCRMEmptyState("🔎", "No CRM records found for this search.", "Try a different company, email, subject, status, or clear the search."));
    return;
  }

  const grid = document.createElement("div");
  grid.className = "crm-record-grid clients-card-grid";

  _crmFilteredRecords.forEach((record) => {
    grid.appendChild(makeCRMRecordCard(record));
  });

  list.appendChild(grid);
}

function makeCRMEmptyState(iconText, heading, text) {
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.style.padding = "40px";

  const icon = document.createElement("div");
  icon.className = "empty-icon";
  icon.textContent = iconText;

  const h3 = document.createElement("h3");
  h3.textContent = heading;

  const p = document.createElement("p");
  p.textContent = text;

  empty.append(icon, h3, p);
  return empty;
}

function makeCRMRecordCard(record) {
  const card = document.createElement("div");
  card.className = "crm-record-card clients-client-card";
  card.id = `crm-row-${record.id}`;

  const top = document.createElement("div");
  top.className = "crm-record-top clients-card-top";

  const titleWrap = document.createElement("div");
  titleWrap.className = "crm-record-title-wrap";

  const title = document.createElement("div");
  title.className = "crm-record-title clients-card-title";
  title.textContent = record.company_name;

  const email = document.createElement("div");
  email.className = "crm-record-email clients-card-meta";
  email.textContent = record.company_email || "—";

  titleWrap.append(title, email);

  const statusBadge = document.createElement("span");
  const badgeMap = { sent: "badge-blue", replied: "badge-green", follow_up: "badge-yellow", closed: "badge-gray" };
  statusBadge.className = `badge ${badgeMap[record.status] || "badge-gray"}`;
  statusBadge.id = `crm-status-${record.id}`;
  statusBadge.textContent = record.status;

  top.append(titleWrap, statusBadge);

  const details = document.createElement("div");
  details.className = "crm-record-details clients-card-details";

  [
    ["Subject", record.email_subject || "—"],
    ["Website", record.company_website || "—"],
    ["Sent", record.sent_at ? new Date(record.sent_at).toLocaleDateString("en-AU") : "—"],
    ["Follow-up", formatFollowup(record)],
    ["Notes", record.notes || "—"],
  ].forEach(([labelText, valueText]) => {
    const row = document.createElement("div");
    row.className = "crm-record-row clients-card-row";

    const label = document.createElement("div");
    label.className = "crm-record-label clients-card-label";
    label.textContent = `${labelText}:`;

    let value;
    if (labelText === "Website" && valueText && valueText !== "—") {
      value = document.createElement("a");
      value.href = valueText;
      value.target = "_blank";
      value.rel = "noopener noreferrer";
      value.className = "crm-record-value crm-record-link clients-card-value";
      value.textContent = valueText;
    } else {
      value = document.createElement("div");
      value.className = "crm-record-value clients-card-value";
      value.textContent = valueText;
    }

    row.append(label, value);
    details.appendChild(row);
  });

  const actions = document.createElement("div");
  actions.className = "crm-record-actions clients-card-footer";

  const sel = document.createElement("select");
  sel.style.cssText = "padding:8px 10px;border:1px solid var(--border);border-radius:8px;font-size:12.5px;cursor:pointer;background:var(--surface)";
  ["sent", "replied", "follow_up", "closed"].forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s.replace("_", " ");
    if (s === record.status) opt.selected = true;
    sel.appendChild(opt);
  });
  sel.addEventListener("change", async () => {
    try {
      await API.patch(`/api/crm/${record.id}/status`, { status: sel.value });
      const badge = document.getElementById(`crm-status-${record.id}`);
      if (badge) {
        const badgeMap2 = { sent: "badge-blue", replied: "badge-green", follow_up: "badge-yellow", closed: "badge-gray" };
        badge.className = `badge ${badgeMap2[sel.value] || "badge-gray"}`;
        badge.textContent = sel.value;
      }
      const target = _crmRecords.find((item) => item.id === record.id);
      if (target) target.status = sel.value;
      const filtered = _crmFilteredRecords.find((item) => item.id === record.id);
      if (filtered) filtered.status = sel.value;
      renderStats(_crmRecords);
      toast("Status updated.", "success");
    } catch (e) {
      toast("Update failed: " + e.message, "error");
    }
  });

  const dncBtn = document.createElement("button");
  dncBtn.className = "btn btn-danger btn-sm";
  dncBtn.textContent = "🚫 Do Not Contact";
  dncBtn.addEventListener("click", () => markCRMDoNotContact(record.id));

  actions.append(sel, dncBtn);
  card.append(top, details, actions);
  return card;
}

function formatFollowup(record) {
  if (!record.follow_up_date) return "—";
  const fuDate = new Date(record.follow_up_date);
  const now = new Date();
  const base = fuDate.toLocaleDateString("en-AU");
  if (fuDate <= now && !record.follow_up_sent && record.status === "sent") {
    return `${base} (due)`;
  }
  return base;
}

async function syncSheets() {
  toast("Syncing to Google Sheets…", "info");
  try {
    const res = await API.post("/api/crm/sync-sheets");
    const guide = document.getElementById("sheets-setup-guide");
    if (res.setup_required) {
      if (guide) guide.style.display = "";
      toast("Google Sheets not configured — see setup guide below.", "error");
    } else {
      if (guide) guide.style.display = "none";
      toast(res.message, res.ok ? "success" : "error");
    }
  } catch (e) {
    toast("Sync failed: " + e.message, "error");
  }
}

async function downloadCSV() {
  try {
    const response = await fetch("/api/crm/export-csv");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "outreach-crm.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast("CSV downloaded.", "success");
  } catch (e) {
    toast("Download failed: " + e.message, "error");
  }
}

async function checkFollowups() {
  try {
    const due = await API.get("/api/crm/followups");
    const card = document.getElementById("followups-card");
    const body = document.getElementById("followups-body");
    if (!card || !body) return;

    if (!due.length) {
      card.style.display = "none";
      toast("No follow-ups due right now.", "success");
      return;
    }

    card.style.display = "";
    body.replaceChildren();

    due.forEach((item) => {
      const row = document.createElement("div");
      row.style.cssText =
        "display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;" +
        "padding:10px 0;border-bottom:1px solid var(--border)";

      const meta = document.createElement("div");
      const name = document.createElement("div");
      name.style.fontWeight = "600";
      name.textContent = item.company_name;
      const info = document.createElement("div");
      info.style.cssText = "font-size:12px;color:var(--text-muted)";
      info.textContent = `${item.company_email || "—"} · ${item.days_since_sent} days ago`;
      meta.append(name, info);

      const btn = document.createElement("button");
      btn.className = "btn btn-warning btn-sm";
      btn.textContent = "Send follow-up";
      btn.addEventListener("click", () => sendFollowup(item.id, btn));

      row.append(meta, btn);
      body.appendChild(row);
    });
  } catch (e) {
    toast("Follow-up check failed: " + e.message, "error");
  }
}

async function sendFollowup(recordId, btn) {
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Sending…";
  try {
    const res = await API.post(`/api/crm/followups/${recordId}/send`, { via: "auto" });
    toast(res.message, res.ok ? "success" : "error");
    if (res.ok) {
      await loadCRM();
      checkFollowups();
    }
  } catch (e) {
    toast("Follow-up send failed: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

async function markCRMDoNotContact(recordId) {
  const confirmed = window.confirm("Mark this company as unsubscribed / do not contact?");
  if (!confirmed) return;
  try {
    const res = await API.post(`/api/crm/${recordId}/do-not-contact`, {
      reason: "unsubscribed",
      notes: "Manual unsubscribe / do not contact.",
    });
    toast(res.message || "Marked as do not contact.", res.ok ? "success" : "error");
    if (res.ok) {
      loadCRM();
    }
  } catch (e) {
    toast("Error: " + e.message, "error");
  }
}

window.init_crm = buildCRMUI;
