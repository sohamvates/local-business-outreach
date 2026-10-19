/* ════════════════════════════════════════════════════════
   sender.js — Email Sender page
   ════════════════════════════════════════════════════════ */

let _approvedEmails = [];
let _resumeStatus = { exists: false, filename: "resume.pdf", size_bytes: 0 };
let _senderStatus = { deliverability_safe_mode: true };
let _senderSettings = {};

async function buildSenderUI() {
  const container = document.getElementById("sender-content");

  const routingCard = document.createElement("div");
  routingCard.className = "card";
  routingCard.style.marginBottom = "16px";

  const routingTitle = document.createElement("div");
  routingTitle.className = "card-title";
  routingTitle.textContent = "📤 Smart Email Routing";

  const routingInfo = document.createElement("div");
  routingInfo.style.cssText = "font-size:13.5px;color:var(--text-muted);margin-top:8px;line-height:1.7";

  const agencyLine = document.createElement("div");
  agencyLine.id = "sender-route-agencies";
  agencyLine.textContent = "Agencies → Gmail mailbox";

  const clientLine = document.createElement("div");
  clientLine.id = "sender-route-clients";
  clientLine.textContent = "Potential clients → custom mailbox";

  const autoNote = document.createElement("div");
  autoNote.style.cssText = "margin-top:8px;font-size:12px;color:var(--text-muted)";
  autoNote.textContent = "Routing is automatic based on the company type — no manual selection needed.";

  const safeModeNotice = document.createElement("div");
  safeModeNotice.id = "deliverability-safe-mode-notice";
  safeModeNotice.style.cssText =
    "display:none;margin-top:12px;padding:12px 14px;border:1px solid #f59e0b;" +
    "border-radius:10px;background:#fffbeb;color:#92400e;font-size:13px;font-weight:600";
  safeModeNotice.textContent =
    "Safe Mode is ON: batch sending is blocked, individual reviewed sends are allowed.";

  routingInfo.append(agencyLine, clientLine, autoNote, safeModeNotice);

  const resumeRow = document.createElement("div");
  resumeRow.style.cssText = "display:flex;align-items:center;gap:8px;margin-top:14px";

  const resumeCb = document.createElement("input");
  resumeCb.type = "checkbox";
  resumeCb.id = "attach-resume-cb";

  const resumeLabel = document.createElement("label");
  resumeLabel.setAttribute("for", "attach-resume-cb");
  resumeLabel.style.cssText = "font-size:13.5px;cursor:pointer";
  resumeLabel.textContent = "Attach resume PDF — agency emails only";

  resumeRow.append(resumeCb, resumeLabel);
  routingCard.append(
    routingTitle,
    routingInfo,
    resumeRow,
    makeResumeManagerCard(),
    makeDeliverabilityChecklistCard(),
    makeTestEmailCard()
  );

  const listCard = document.createElement("div");
  listCard.className = "card";

  const listHeader = document.createElement("div");
  listHeader.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px";

  const listTitle = document.createElement("div");
  listTitle.className = "card-title";
  listTitle.id = "sender-list-title";
  listTitle.textContent = "Approved Emails";

  const sendAllBtn = document.createElement("button");
  sendAllBtn.className = "btn btn-primary";
  sendAllBtn.id = "send-all-btn";
  sendAllBtn.textContent = "📤 Send All";
  sendAllBtn.addEventListener("click", sendAll);

  listHeader.append(listTitle, sendAllBtn);

  const listBody = document.createElement("div");
  listBody.id = "sender-list";

  listCard.append(listHeader, listBody);
  container.replaceChildren(routingCard, listCard);

  await loadResumeStatus();
  await loadSenderContext();
  renderSafeModeState();
  renderDeliverabilityChecklist();
  loadApproved();
}

function makeResumeManagerCard() {
  const wrap = document.createElement("div");
  wrap.style.cssText = "margin-top:16px;padding-top:16px;border-top:1px solid var(--border)";

  const title = document.createElement("div");
  title.style.cssText = "font-weight:600;font-size:14px;margin-bottom:8px";
  title.textContent = "Resume PDF";

  const status = document.createElement("div");
  status.id = "resume-status";
  status.style.cssText = "font-size:13px;color:var(--text-muted);margin-bottom:10px";
  status.textContent = "Checking resume status…";

  const row = document.createElement("div");
  row.style.cssText = "display:flex;align-items:center;gap:10px;flex-wrap:wrap";

  const input = document.createElement("input");
  input.type = "file";
  input.id = "resume-upload";
  input.accept = "application/pdf,.pdf";

  const uploadBtn = document.createElement("button");
  uploadBtn.className = "btn btn-ghost btn-sm";
  uploadBtn.textContent = "Upload resume PDF";
  uploadBtn.addEventListener("click", uploadResume);

  row.append(input, uploadBtn);
  wrap.append(title, status, row);
  return wrap;
}

function makeDeliverabilityChecklistCard() {
  const wrap = document.createElement("div");
  wrap.style.cssText = "margin-top:16px;padding-top:16px;border-top:1px solid var(--border)";

  const title = document.createElement("div");
  title.style.cssText = "font-weight:600;font-size:14px;margin-bottom:8px";
  title.textContent = "Deliverability Checklist";

  const list = document.createElement("div");
  list.id = "deliverability-checklist";
  list.style.cssText = "display:grid;gap:8px";

  wrap.append(title, list);
  return wrap;
}

function makeTestEmailCard() {
  const wrap = document.createElement("div");
  wrap.style.cssText = "margin-top:16px;padding-top:16px;border-top:1px solid var(--border)";

  const title = document.createElement("div");
  title.style.cssText = "font-weight:600;font-size:14px;margin-bottom:4px";
  title.textContent = "Test Email";

  const sub = document.createElement("div");
  sub.style.cssText = "font-size:12.5px;color:var(--text-muted);margin-bottom:14px";
  sub.textContent = "Send a real test email to yourself without creating a lead, draft, campaign, or CRM record.";

  const grid = document.createElement("div");
  grid.className = "form-grid";
  grid.append(
    makeTestField("test-recipient-email", "Recipient Email", "email", "you@example.com"),
    makeTestSenderSelect(),
    makeTestField("test-subject", "Subject", "text", "Test email"),
    makeTestField("test-body", "Body", "textarea", "This is a test email from Nearletter.")
  );

  const quickActions = document.createElement("div");
  quickActions.style.cssText = "display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:12px";

  const quickGmailBtn = document.createElement("button");
  quickGmailBtn.className = "btn btn-outline btn-sm";
  quickGmailBtn.textContent = "Send test to my Gmail via Gmail SMTP";
  quickGmailBtn.addEventListener("click", () => sendQuickGmailTest("gmail"));

  const quickCustomBtn = document.createElement("button");
  quickCustomBtn.className = "btn btn-outline btn-sm";
  quickCustomBtn.textContent = "Send test to my Gmail via Custom SMTP";
  quickCustomBtn.addEventListener("click", () => sendQuickGmailTest("custom"));

  quickActions.append(quickGmailBtn, quickCustomBtn);

  const actions = document.createElement("div");
  actions.style.cssText = "display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:14px";

  const previewBtn = document.createElement("button");
  previewBtn.className = "btn btn-ghost";
  previewBtn.id = "preview-test-email-btn";
  previewBtn.textContent = "Preview test email";
  previewBtn.addEventListener("click", previewTestEmail);

  const btn = document.createElement("button");
  btn.className = "btn btn-primary";
  btn.id = "send-test-email-btn";
  btn.textContent = "Send test email";
  btn.addEventListener("click", sendTestEmail);

  const result = document.createElement("span");
  result.id = "test-email-result";
  result.style.cssText = "font-size:13px";

  const previewCard = document.createElement("div");
  previewCard.id = "test-email-preview";
  previewCard.className = "card";
  previewCard.style.cssText = "display:none;margin-top:14px;background:var(--surface-2);padding:18px";

  actions.append(previewBtn, btn, result);
  wrap.append(title, sub, grid, quickActions, actions, previewCard);
  return wrap;
}

function makeTestField(id, labelText, type, value) {
  const group = document.createElement("div");
  group.className = "form-group";
  if (type === "textarea") group.classList.add("full");

  const label = document.createElement("label");
  label.setAttribute("for", id);
  label.textContent = labelText;

  let input;
  if (type === "textarea") {
    input = document.createElement("textarea");
    input.rows = 4;
  } else {
    input = document.createElement("input");
    input.type = type;
  }
  input.id = id;
  input.value = value;

  group.append(label, input);
  return group;
}

function makeTestSenderSelect() {
  const group = document.createElement("div");
  group.className = "form-group";

  const label = document.createElement("label");
  label.setAttribute("for", "test-sender-type");
  label.textContent = "Sender Type";

  const select = document.createElement("select");
  select.id = "test-sender-type";
  [["gmail", "gmail"], ["custom", "custom"]].forEach(([value, text]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    select.appendChild(option);
  });

  group.append(label, select);
  return group;
}

async function loadResumeStatus() {
  const status = document.getElementById("resume-status");
  if (!status) return;

  try {
    const res = await API.get("/api/send/resume");
    _resumeStatus = res;
    status.style.color = res.exists ? "var(--success)" : "var(--error)";
    status.textContent = res.exists
      ? `Resume found: ${res.filename} (${Math.round((res.size_bytes || 0) / 1024)} KB)`
      : "Resume missing: upload static/assets/resume.pdf before sending with attachment.";
  } catch (e) {
    status.style.color = "var(--error)";
    status.textContent = "Could not load resume status: " + e.message;
  }
}

async function loadSenderContext() {
  try {
    const [status, settings] = await Promise.all([
      API.get("/api/send/status"),
      API.get("/api/settings"),
    ]);
    _senderStatus = status || { deliverability_safe_mode: true };
    _senderSettings = settings || {};
    renderRoutingAddresses();
  } catch (_) {
    _senderStatus = { deliverability_safe_mode: true };
    _senderSettings = {};
  }
}

function renderRoutingAddresses() {
  const gmail = (_senderSettings.GMAIL_SMTP_USER || "").trim() || "not configured";
  const custom = (_senderSettings.CUSTOM_SMTP_USER || "").trim() || "not configured";
  const agency = document.getElementById("sender-route-agencies");
  const client = document.getElementById("sender-route-clients");
  if (agency) agency.textContent = `Agencies → ${gmail} (Gmail)`;
  if (client) client.textContent = `Potential clients → ${custom} (custom mailbox)`;
}

function deliverabilitySafeModeOn() {
  return !!_senderStatus?.deliverability_safe_mode;
}

function renderSafeModeState() {
  const notice = document.getElementById("deliverability-safe-mode-notice");
  if (notice) notice.style.display = deliverabilitySafeModeOn() ? "" : "none";

  const sendAllBtn = document.getElementById("send-all-btn");
  if (sendAllBtn) {
    sendAllBtn.disabled = deliverabilitySafeModeOn();
    sendAllBtn.title = deliverabilitySafeModeOn()
      ? "Safe Mode is ON: batch sending is blocked, individual reviewed sends are allowed."
      : "";
  }
}

function renderDeliverabilityChecklist() {
  const container = document.getElementById("deliverability-checklist");
  if (!container) return;

  const items = [
    "SPF configured? manual check",
    "DKIM configured? manual check",
    "DMARC configured? manual check",
    "Gmail test passed inbox? manual check",
    "Custom SMTP test passed inbox? manual check",
  ];

  container.replaceChildren(
    ...items.map((text) => {
      const row = document.createElement("div");
      row.style.cssText =
        "display:flex;align-items:center;gap:8px;padding:8px 10px;border:1px solid var(--border);" +
        "border-radius:8px;background:var(--surface)";
      const icon = document.createElement("span");
      icon.textContent = "⬜";
      const label = document.createElement("span");
      label.style.cssText = "font-size:13px;color:var(--text-muted)";
      label.textContent = text;
      row.append(icon, label);
      return row;
    })
  );
}

async function uploadResume() {
  const input = document.getElementById("resume-upload");
  const file = input?.files?.[0];
  if (!file) {
    toast("Select a PDF file first.", "error");
    return;
  }
  if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
    toast("Resume upload must be a PDF file.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch("/api/send/resume", { method: "POST", body: formData });
    const res = await response.json();
    toast(res.message, res.ok ? "success" : "error");
    if (res.ok) {
      if (input) input.value = "";
      await loadResumeStatus();
      previewTestEmail();
    }
  } catch (e) {
    toast("Resume upload failed: " + e.message, "error");
  }
}

async function loadApproved() {
  const list = document.getElementById("sender-list");
  const titleEl = document.getElementById("sender-list-title");
  if (!list) return;

  list.replaceChildren();
  const loading = document.createElement("div");
  loading.style.cssText = "text-align:center;padding:30px;color:var(--text-muted)";
  loading.textContent = "Loading approved emails…";
  list.appendChild(loading);

  try {
    _approvedEmails = await API.get("/api/send/approved");
    if (titleEl) titleEl.textContent = `Approved Emails (${_approvedEmails.length})`;
    renderApproved(_approvedEmails, list);
  } catch (e) {
    list.textContent = "Failed to load: " + e.message;
  }
}

function hasBlockedDeliverabilityWarnings(email) {
  const notes = (email?.review_notes || "").toLowerCase();
  return (
    notes.includes("spam words") ||
    notes.includes("deliverability terms") ||
    notes.includes("all caps") ||
    notes.includes("punctuation") ||
    notes.includes("subject truncated") ||
    notes.includes("subject warning")
  );
}

function renderApproved(emails, container) {
  container.replaceChildren();

  if (!emails.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.style.padding = "40px";
    const icon = document.createElement("div");
    icon.className = "empty-icon";
    icon.textContent = "📭";
    const h3 = document.createElement("h3");
    h3.textContent = "No approved emails";
    const p = document.createElement("p");
    p.textContent = "Approve emails in the Review Queue to send them here.";
    const navBtn = document.createElement("button");
    navBtn.className = "btn btn-outline btn-sm";
    navBtn.textContent = "Go to Review Queue →";
    navBtn.addEventListener("click", () => navigate("review"));
    empty.append(icon, h3, p, navBtn);
    container.appendChild(empty);
    return;
  }

  const list = document.createElement("div");
  list.className = "data-list";
  emails.forEach((email) => {
    const hasWarnings = hasBlockedDeliverabilityWarnings(email);
    const card = document.createElement("article");
    card.className = "data-card";
    card.id = `send-row-${email.id}`;
    if (email.review_notes) card.title = email.review_notes;

    const top = document.createElement("div");
    top.className = "data-card-top";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "send-checkbox";
    cb.value = email.id;
    cb.checked = true;
    cb.disabled = hasWarnings;

    const main = document.createElement("div");
    main.className = "data-card-main";

    const title = document.createElement("div");
    title.className = "data-card-title";
    title.textContent = email.company_name;

    const toLine = document.createElement("div");
    toLine.className = "data-card-line";
    const toLabel = document.createElement("span");
    toLabel.className = "data-card-label";
    toLabel.textContent = "To";
    toLine.append(toLabel, document.createTextNode(email.company_email || "No email"));

    const subjectLine = document.createElement("div");
    subjectLine.className = "data-card-line";
    const subjectLabel = document.createElement("span");
    subjectLabel.className = "data-card-label";
    subjectLabel.textContent = "Subject";
    subjectLine.append(subjectLabel, document.createTextNode(email.subject || "—"));

    main.append(title, toLine, subjectLine);
    top.append(cb, main);

    const actions = document.createElement("div");
    actions.className = "data-card-actions";
    const badge = document.createElement("span");
    badge.className = hasWarnings ? "badge badge-red" : "badge badge-green";
    badge.id = `send-status-${email.id}`;
    badge.textContent = hasWarnings ? "warning" : "ready";
    const sendBtn = document.createElement("button");
    sendBtn.className = "btn btn-primary btn-sm";
    sendBtn.textContent = "Send";
    sendBtn.id = `send-btn-${email.id}`;
    sendBtn.addEventListener("click", () => sendOne(email.id, sendBtn));
    if (hasWarnings) {
      sendBtn.disabled = true;
      sendBtn.title = `Fix deliverability warnings before sending: ${email.review_notes || "review_notes present"}`;
    }
    actions.append(badge, sendBtn);

    card.append(top, actions);
    list.appendChild(card);
  });
  container.appendChild(list);
}

function _attachResume() {
  return document.getElementById("attach-resume-cb")?.checked ?? false;
}

function _testEmailPreviewData() {
  const attachResume = _attachResume();
  let attachmentStatus = "not attached";
  if (attachResume) {
    attachmentStatus = _resumeStatus.exists ? "attached" : "missing resume";
  }

  return {
    senderType: document.getElementById("test-sender-type")?.value || "gmail",
    recipient: document.getElementById("test-recipient-email")?.value || "",
    subject: document.getElementById("test-subject")?.value || "",
    body: document.getElementById("test-body")?.value || "",
    attachmentStatus,
  };
}

function previewTestEmail() {
  const card = document.getElementById("test-email-preview");
  if (!card) return;

  const data = _testEmailPreviewData();
  card.style.display = "";
  card.replaceChildren();

  const title = document.createElement("div");
  title.className = "card-title";
  title.textContent = "Preview";

  const meta = document.createElement("div");
  meta.className = "kv-grid";
  meta.style.marginBottom = "14px";

  [
    ["Sender type", data.senderType],
    ["Recipient", data.recipient || "—"],
    ["Subject", data.subject || "—"],
    ["Attachment", data.attachmentStatus],
    ["Check after send", "Open Gmail > Show original > check SPF, DKIM, DMARC."],
  ].forEach(([labelText, valueText]) => {
    const label = document.createElement("div");
    label.style.cssText = "font-weight:600;color:var(--text-muted)";
    label.textContent = labelText;

    const value = document.createElement("div");
    value.style.color = labelText === "Attachment" && valueText === "missing resume" ? "var(--error)" : "var(--text)";
    value.textContent = valueText;

    meta.append(label, value);
  });

  const bodyLabel = document.createElement("div");
  bodyLabel.style.cssText = "font-weight:600;font-size:13px;color:var(--text-muted);margin-bottom:8px";
  bodyLabel.textContent = "Body";

  const body = document.createElement("div");
  body.style.cssText =
    "white-space:pre-wrap;font-size:13.5px;line-height:1.6;color:var(--text);" +
    "background:var(--surface);padding:14px;border:1px solid var(--border);border-radius:6px";
  body.textContent = data.body || "—";

  if (data.attachmentStatus === "missing resume") {
    const warning = document.createElement("div");
    warning.style.cssText = "margin-bottom:12px;font-size:12.5px;color:var(--error);font-weight:600";
    warning.textContent = "Resume attachment is marked, but static/assets/resume.pdf is missing. Upload it before sending.";
    card.append(title, warning, meta, bodyLabel, body);
    return;
  }

  card.append(title, meta, bodyLabel, body);
}

function renderTestEmailResult(res) {
  const card = document.getElementById("test-email-preview");
  if (!card || !res?.ok) return;

  const details = document.createElement("div");
  details.className = "kv-grid";
  details.style.marginTop = "14px";

  [
    ["Sender type", res.sender_type || "—"],
    ["SMTP host", res.smtp_host || "—"],
    ["From header", res.from_header || "—"],
    ["Envelope sender", res.envelope_sender || "—"],
    ["Reply-To", res.reply_to || "—"],
    ["Message-ID", res.message_id || "—"],
    ["Date", res.date || "—"],
  ].forEach(([labelText, valueText]) => {
    const label = document.createElement("div");
    label.style.cssText = "font-weight:600;color:var(--text-muted)";
    label.textContent = labelText;

    const value = document.createElement("div");
    value.textContent = valueText;
    details.append(label, value);
  });

  const note = document.createElement("div");
  note.style.cssText = "margin-top:12px;font-size:12.5px;color:var(--text-muted)";
  note.textContent = res.show_original_instructions || "Open Gmail > Show original > check SPF, DKIM, DMARC.";

  card.append(details, note);
}

async function sendTestEmail() {
  const btn = document.getElementById("send-test-email-btn");
  const result = document.getElementById("test-email-result");
  if (!btn || !result) return;

  const preview = _testEmailPreviewData();
  if (preview.attachmentStatus === "missing resume") {
    result.style.color = "var(--error)";
    result.textContent = "✕ Resume PDF is missing. Upload it before sending with attachment.";
    previewTestEmail();
    toast("Resume PDF is missing. Upload it before sending with attachment.", "error");
    return;
  }

  btn.disabled = true;
  btn.textContent = "Sending…";
  result.textContent = "";

  try {
    const res = await API.post("/api/send/test-email", {
      recipient_email: document.getElementById("test-recipient-email")?.value || "",
      via: document.getElementById("test-sender-type")?.value || "gmail",
      subject: document.getElementById("test-subject")?.value || "",
      body: document.getElementById("test-body")?.value || "",
      attach_resume: _attachResume(),
    });
    result.style.color = res.ok ? "var(--success)" : "var(--error)";
    result.textContent = res.ok ? "✓ " + res.message : "✕ " + res.message;
    renderTestEmailResult(res);
    toast(res.message, res.ok ? "success" : "error");
  } catch (e) {
    result.style.color = "var(--error)";
    result.textContent = "✕ " + e.message;
    toast("Test send failed: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Send test email";
  }
}

async function sendQuickGmailTest(via) {
  const gmailAddress = (_senderSettings.GMAIL_SMTP_USER || "").trim();
  if (!gmailAddress) {
    toast("Set your Gmail address in Settings first.", "error");
    return;
  }

  const recipient = document.getElementById("test-recipient-email");
  const senderType = document.getElementById("test-sender-type");
  if (recipient) recipient.value = gmailAddress;
  if (senderType) senderType.value = via;

  previewTestEmail();
  await sendTestEmail();
}

async function sendOne(emailId, btn) {
  const email = _approvedEmails.find((item) => item.id === emailId);
  if (hasBlockedDeliverabilityWarnings(email)) {
    toast(`Fix deliverability warnings before sending: ${email.review_notes || "review_notes present"}`, "error");
    return;
  }

  if (!btn) return;
  const origText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Sending…";

  const badge = document.getElementById(`send-status-${emailId}`);

  try {
    const res = await API.post(`/api/send/${emailId}`, { via: "auto", attach_resume: _attachResume() });
    if (res.ok) {
      if (badge) { badge.className = "badge badge-blue"; badge.textContent = "sent"; }
      btn.textContent = "✓ Sent";
      toast(res.message, "success");
    } else {
      if (badge) { badge.className = "badge badge-red"; badge.textContent = "failed"; }
      btn.disabled = false;
      btn.textContent = origText;
      toast(res.message, "error");
    }
  } catch (e) {
    btn.disabled = false;
    btn.textContent = origText;
    toast("Send failed: " + e.message, "error");
  }
}

async function sendAll() {
  if (deliverabilitySafeModeOn()) {
    toast("Safe Mode is ON: batch sending is blocked, individual reviewed sends are allowed.", "error");
    return;
  }
  if (_approvedEmails.some(hasBlockedDeliverabilityWarnings)) {
    const blocked = _approvedEmails.find(hasBlockedDeliverabilityWarnings);
    toast(`Fix deliverability warnings before sending: ${blocked?.review_notes || "review_notes present"}`, "error");
    return;
  }

  const selected = [...document.querySelectorAll(".send-checkbox:checked")].map((cb) =>
    parseInt(cb.value)
  );
  if (!selected.length) {
    toast("No emails selected.", "error");
    return;
  }

  const btn = document.getElementById("send-all-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Sending…"; }

  try {
    const res = await API.post("/api/send/batch", { email_ids: selected, via: "auto", attach_resume: _attachResume() });
    const msg = `Sent ${res.sent}, failed ${res.failed}.` + (res.errors?.length ? ` Errors: ${res.errors.join("; ")}` : "");
    toast(msg, res.ok ? "success" : "error");
    loadApproved();
  } catch (e) {
    toast("Batch send failed: " + e.message, "error");
  } finally {
    if (btn) {
      btn.disabled = deliverabilitySafeModeOn();
      btn.textContent = "📤 Send All";
    }
  }
}

window.init_sender = buildSenderUI;
