/* ════════════════════════════════════════════════════════
   review.js — Review Queue page
   ════════════════════════════════════════════════════════ */

let _editingId = null;

async function buildReviewUI() {
  const container = document.getElementById("review-content");
  container.replaceChildren();

  // Filter tabs
  const tabs = document.createElement("div");
  tabs.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px";
  ["Pending", "Approved", "All"].forEach((label, i) => {
    const btn = document.createElement("button");
    btn.className = i === 0 ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm";
    btn.textContent = label;
    btn.addEventListener("click", () => {
      tabs.querySelectorAll("button").forEach((b) =>
        b.className = b === btn ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm"
      );
      loadEmails(label.toLowerCase(), container);
    });
    tabs.appendChild(btn);
  });
  container.appendChild(tabs);

  loadEmails("pending", container);
}

async function loadEmails(filter, container) {
  // Remove previous list
  const prev = document.getElementById("review-list");
  if (prev) prev.remove();

  const list = document.createElement("div");
  list.id = "review-list";
  container.appendChild(list);

  const loading = document.createElement("div");
  loading.style.cssText = "text-align:center;padding:30px;color:var(--text-muted)";
  loading.textContent = "Loading…";
  list.appendChild(loading);

  try {
    const endpoint = filter === "all" ? "/api/review/all" : "/api/review";
    let emails = await API.get(endpoint);
    if (filter === "approved") emails = emails.filter ? emails : (await API.get("/api/review/all")).filter((e) => e.status === "approved");
    if (filter === "approved") {
      const all = await API.get("/api/review/all");
      emails = all.filter((e) => e.status === "approved");
    }
    renderEmails(emails, list);
  } catch (e) {
    list.textContent = "Failed to load emails: " + e.message;
  }
}

function renderEmails(emails, container) {
  container.replaceChildren();

  if (!emails.length) {
    const empty = document.createElement("div");
    empty.className = "card";
    const es = document.createElement("div");
    es.className = "empty-state";
    const icon = document.createElement("div");
    icon.className = "empty-icon";
    icon.textContent = "📬";
    const h3 = document.createElement("h3");
    h3.textContent = "No emails here";
    const p = document.createElement("p");
    p.textContent = "Generate emails with the AI Engine to see them here.";
    es.append(icon, h3, p);
    empty.appendChild(es);
    container.appendChild(empty);
    return;
  }

  emails.forEach((email) => {
    const card = document.createElement("div");
    card.className = "card";
    card.id = `email-card-${email.id}`;
    card.style.marginBottom = "16px";

    // Header
    const header = document.createElement("div");
    header.style.cssText = "display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px;min-width:0";

    const meta = document.createElement("div");
    meta.style.cssText = "flex:1;min-width:0";

    const companyEl = document.createElement("div");
    companyEl.style.cssText = "font-weight:700;font-size:15px;color:var(--text);overflow-wrap:break-word";
    companyEl.textContent = email.company_name;

    const emailMeta = document.createElement("div");
    emailMeta.style.cssText = "font-size:12px;color:var(--text-muted);margin-top:3px;overflow-wrap:break-word";
    emailMeta.textContent = `To: ${email.company_email || "no email"} · From: ${email.from_address || "—"}`;

    meta.append(companyEl, emailMeta);

    const statusBadge = document.createElement("span");
    const badgeClass = { pending: "badge-yellow", approved: "badge-green", discarded: "badge-red", sent: "badge-blue" };
    statusBadge.className = `badge ${badgeClass[email.status] || "badge-gray"}`;
    statusBadge.id = `status-badge-${email.id}`;
    statusBadge.textContent = email.status;

    header.append(meta, statusBadge);

    // Subject
    const subject = document.createElement("div");
    subject.style.cssText = "font-weight:600;font-size:14px;margin-bottom:8px;color:var(--text);overflow-wrap:break-word";
    subject.id = `subject-${email.id}`;
    subject.textContent = `Subject: ${email.subject}`;

    // Body (collapsible)
    const body = document.createElement("pre");
    body.id = `body-${email.id}`;
    body.style.cssText =
      "white-space:pre-wrap;overflow-wrap:break-word;font-family:inherit;font-size:13.5px;color:var(--text-muted);" +
      "background:var(--surface-2);padding:14px;border-radius:6px;border:1px solid var(--border);" +
      "max-height:200px;overflow-y:auto;line-height:1.6";
    body.textContent = email.body;

    // Edit form (hidden until Edit clicked)
    const editForm = document.createElement("div");
    editForm.id = `edit-form-${email.id}`;
    editForm.style.display = "none";

    const subjectInput = document.createElement("input");
    subjectInput.type = "text";
    subjectInput.id = `edit-subject-${email.id}`;
    subjectInput.style.cssText = "width:100%;margin-bottom:8px";

    const bodyInput = document.createElement("textarea");
    bodyInput.id = `edit-body-${email.id}`;
    bodyInput.rows = 10;
    bodyInput.style.cssText = "width:100%;resize:vertical;font-family:inherit;font-size:13.5px";

    const editActions = document.createElement("div");
    editActions.style.cssText = "display:flex;gap:8px;margin-top:8px";

    const saveBtn = document.createElement("button");
    saveBtn.className = "btn btn-primary btn-sm";
    saveBtn.textContent = "💾 Save";
    saveBtn.addEventListener("click", () => saveEdit(email.id));

    const cancelBtn = document.createElement("button");
    cancelBtn.className = "btn btn-ghost btn-sm";
    cancelBtn.textContent = "Cancel";
    cancelBtn.addEventListener("click", () => closeEdit(email.id, email));

    editActions.append(saveBtn, cancelBtn);
    editForm.append(subjectInput, bodyInput, editActions);

    // Deliverability warnings (from AI sanitizer) — built here, appended below
    let warnBox = null;
    if (email.review_notes) {
      warnBox = document.createElement("div");
      warnBox.style.cssText =
        "background:#fffbeb;border:1px solid #fde68a;border-radius:6px;" +
        "padding:10px 14px;margin-bottom:12px;font-size:12px;color:#92400e";
      const warnTitle = document.createElement("strong");
      warnTitle.textContent = "⚠ Deliverability notes: ";
      warnBox.appendChild(warnTitle);
      warnBox.appendChild(document.createTextNode(email.review_notes));
    }

    // Action buttons
    const actions = document.createElement("div");
    actions.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;padding-top:12px;border-top:1px solid var(--border)";

    if (email.status === "pending") {
      const approveBtn = document.createElement("button");
      approveBtn.className = "btn btn-success btn-sm";
      approveBtn.textContent = "✓ Approve";
      approveBtn.addEventListener("click", () => approveEmail(email.id));

      const discardBtn = document.createElement("button");
      discardBtn.className = "btn btn-danger btn-sm";
      discardBtn.textContent = "✕ Discard";
      discardBtn.addEventListener("click", () => discardEmail(email.id));

      const editBtn = document.createElement("button");
      editBtn.className = "btn btn-ghost btn-sm";
      editBtn.textContent = "✏ Edit";
      editBtn.addEventListener("click", () => openEdit(email));

      const dncBtn = document.createElement("button");
      dncBtn.className = "btn btn-danger btn-sm";
      dncBtn.textContent = "🚫 Mark Do Not Contact";
      dncBtn.addEventListener("click", () => markDoNotContact(email.id));

      actions.append(approveBtn, discardBtn, editBtn, dncBtn);
    } else if (email.status === "approved") {
      const sendBtn = document.createElement("button");
      sendBtn.className = "btn btn-primary btn-sm";
      sendBtn.textContent = "📤 Send now";
      sendBtn.addEventListener("click", () => navigate("sender"));

      const editBtn = document.createElement("button");
      editBtn.className = "btn btn-ghost btn-sm";
      editBtn.textContent = "✏ Edit";
      editBtn.addEventListener("click", () => openEdit(email));

      const dncBtn = document.createElement("button");
      dncBtn.className = "btn btn-danger btn-sm";
      dncBtn.textContent = "🚫 Mark Do Not Contact";
      dncBtn.addEventListener("click", () => markDoNotContact(email.id));

      actions.append(sendBtn, editBtn, dncBtn);
    } else {
      const dncBtn = document.createElement("button");
      dncBtn.className = "btn btn-danger btn-sm";
      dncBtn.textContent = "🚫 Mark Do Not Contact";
      dncBtn.addEventListener("click", () => markDoNotContact(email.id));
      actions.append(dncBtn);
    }

    // warnBox sits between body and editForm; omitted when null
    card.append(header, subject, body, ...(warnBox ? [warnBox] : []), editForm, actions);
    container.appendChild(card);
  });

  // Update sidebar badge
  const pending = emails.filter((e) => e.status === "pending").length;
  const badge = document.getElementById("review-badge");
  if (badge) {
    badge.textContent = pending;
    badge.style.display = pending > 0 ? "" : "none";
  }
}

function openEdit(email) {
  const form = document.getElementById(`edit-form-${email.id}`);
  const body = document.getElementById(`body-${email.id}`);
  const subj = document.getElementById(`subject-${email.id}`);
  if (!form) return;

  document.getElementById(`edit-subject-${email.id}`).value = email.subject;
  document.getElementById(`edit-body-${email.id}`).value = email.body;

  form.style.display = "";
  body.style.display = "none";
  subj.style.display = "none";
  _editingId = email.id;
}

function closeEdit(emailId, email) {
  const form = document.getElementById(`edit-form-${emailId}`);
  const body = document.getElementById(`body-${emailId}`);
  const subj = document.getElementById(`subject-${emailId}`);
  if (form) form.style.display = "none";
  if (body) body.style.display = "";
  if (subj) subj.style.display = "";
  _editingId = null;
}

async function saveEdit(emailId) {
  const subject = document.getElementById(`edit-subject-${emailId}`)?.value;
  const body = document.getElementById(`edit-body-${emailId}`)?.value;
  try {
    const res = await API.patch(`/api/review/${emailId}/edit`, { subject, body });
    const savedSubject = res.subject || subject;
    const savedBody = res.body || body;
    // Update displayed values
    const bodyEl = document.getElementById(`body-${emailId}`);
    const subjEl = document.getElementById(`subject-${emailId}`);
    if (bodyEl) bodyEl.textContent = savedBody;
    if (subjEl) subjEl.textContent = `Subject: ${savedSubject}`;
    closeEdit(emailId, { subject: savedSubject, body: savedBody });
    toast("Email updated.", "success");
  } catch (e) {
    toast("Save failed: " + e.message, "error");
  }
}

async function approveEmail(emailId) {
  try {
    await API.patch(`/api/review/${emailId}/approve`);
    const badge = document.getElementById(`status-badge-${emailId}`);
    if (badge) {
      badge.className = "badge badge-green";
      badge.textContent = "approved";
    }
    // Rebuild action buttons
    const card = document.getElementById(`email-card-${emailId}`);
    const actions = card?.querySelector("div:last-child");
    if (actions) {
      actions.replaceChildren();
      const sendBtn = document.createElement("button");
      sendBtn.className = "btn btn-primary btn-sm";
      sendBtn.textContent = "📤 Send now";
      sendBtn.addEventListener("click", () => navigate("sender"));
      actions.appendChild(sendBtn);
    }
    toast("Email approved.", "success");
  } catch (e) {
    toast("Error: " + e.message, "error");
  }
}

async function discardEmail(emailId) {
  try {
    await API.patch(`/api/review/${emailId}/discard`);
    const card = document.getElementById(`email-card-${emailId}`);
    if (card) card.style.opacity = "0.4";
    const badge = document.getElementById(`status-badge-${emailId}`);
    if (badge) {
      badge.className = "badge badge-red";
      badge.textContent = "discarded";
    }
    toast("Email discarded.", "info");
  } catch (e) {
    toast("Error: " + e.message, "error");
  }
}

async function markDoNotContact(emailId) {
  const confirmed = window.confirm("Mark this company as unsubscribed / do not contact?");
  if (!confirmed) return;
  try {
    const res = await API.post(`/api/review/${emailId}/do-not-contact`, {
      reason: "unsubscribed",
      notes: "Manual unsubscribe / do not contact.",
    });
    toast(res.message || "Marked as do not contact.", res.ok ? "success" : "error");
    if (res.ok) {
      buildReviewUI();
    }
  } catch (e) {
    toast("Error: " + e.message, "error");
  }
}

window.init_review = buildReviewUI;
