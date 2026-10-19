/* ════════════════════════════════════════════════════════
   ai_engine.js — AI email generation page
   ════════════════════════════════════════════════════════ */

let _aiPollTimer = null;
let _allCompanies = [];
let _aiStats = null;
const _generateButtons = [];

function buildAIEngineUI() {
  const container = document.getElementById("ai-engine-content");

  // ── Sender context card ────────────────────────────────
  const ctxCard = document.createElement("div");
  ctxCard.className = "card";

  const ctxTitle = document.createElement("div");
  ctxTitle.className = "card-title";
  ctxTitle.textContent = "✉️ Sender Context";

  const ctxSub = document.createElement("div");
  ctxSub.className = "card-subtitle";
  ctxSub.textContent = "Claude uses this to personalise each email on your behalf.";

  const grid = document.createElement("div");
  grid.className = "form-grid";

  grid.append(
    _field("ai-sender-name", "Your Name", "text", "Your name"),
    _field("ai-sender-role", "Your Role", "text", "Your role"),
    _field("ai-sender-company", "Your Company", "text", "Your company"),
    _field("ai-sender-email", "Sender Email", "email", "you@example.com"),
  );

  const vpGroup = document.createElement("div");
  vpGroup.className = "form-group full";
  const vpLabel = document.createElement("label");
  vpLabel.textContent = "Value Proposition";
  vpLabel.setAttribute("for", "ai-value-prop");
  const vpInput = document.createElement("textarea");
  vpInput.id = "ai-value-prop";
  vpInput.rows = 2;
  vpInput.style.resize = "vertical";
  vpInput.value =
    "We help Australian businesses build modern, high-performance digital experiences " +
    "using React, Next.js, and AI-powered solutions.";
  vpGroup.append(vpLabel, vpInput);
  grid.appendChild(vpGroup);

  ctxCard.append(ctxTitle, ctxSub, grid);

  // ── Company selection card ─────────────────────────────
  const selCard = document.createElement("div");
  selCard.className = "card";

  const selTitle = document.createElement("div");
  selTitle.className = "card-title";
  selTitle.textContent = "🏢 Select Companies";

  const selSub = document.createElement("div");
  selSub.className = "card-subtitle";
  selSub.textContent =
    "Only eligible companies are shown. Companies already contacted or with existing drafts are excluded.";

  const filterRow = document.createElement("div");
  filterRow.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px";

  ["All", "Agencies", "Clients"].forEach((f) => {
    const btn = document.createElement("button");
    btn.className = f === "All" ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm";
    btn.textContent = f;
    btn.dataset.filter = f.toLowerCase();
    btn.addEventListener("click", () => {
      filterRow.querySelectorAll("button").forEach((b) =>
        b.className = b === btn ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm"
      );
      renderCompanyList(f.toLowerCase());
    });
    filterRow.appendChild(btn);
  });

  const companyList = document.createElement("div");
  companyList.id = "ai-company-list";

  const summary = document.createElement("div");
  summary.id = "ai-company-summary";
  summary.style.cssText = "font-size:12.5px;color:var(--text-muted);margin-bottom:10px";

  const topActions = document.createElement("div");
  topActions.style.cssText =
    "display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;" +
    "margin-bottom:12px;padding:12px 14px;border:1px solid var(--border);" +
    "border-radius:12px;background:var(--bg)";

  const topActionsNote = document.createElement("div");
  topActionsNote.style.cssText = "font-size:12.5px;color:var(--text-muted)";
  topActionsNote.textContent = "Select one or more eligible companies, then generate drafts.";

  const selActions = document.createElement("div");
  selActions.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;padding-top:12px;border-top:1px solid var(--border)";

  const selAllBtn = document.createElement("button");
  selAllBtn.className = "btn btn-ghost btn-sm";
  selAllBtn.textContent = "Select all";
  selAllBtn.addEventListener("click", () => {
    document.querySelectorAll(".company-checkbox").forEach((cb) => {
      if (!cb.disabled) cb.checked = true;
    });
    syncGenerateButtonsState();
  });

  const selNoneBtn = document.createElement("button");
  selNoneBtn.className = "btn btn-ghost btn-sm";
  selNoneBtn.textContent = "Deselect all";
  selNoneBtn.addEventListener("click", () => {
    document.querySelectorAll(".company-checkbox").forEach((cb) => {
      cb.checked = false;
    });
    syncGenerateButtonsState();
  });

  const generateBtn = document.createElement("button");
  generateBtn.className = "btn btn-primary";
  generateBtn.textContent = "🤖 Generate Emails";
  generateBtn.style.marginLeft = "auto";
  generateBtn.addEventListener("click", startGeneration);

  const topGenerateBtn = document.createElement("button");
  topGenerateBtn.className = "btn btn-primary";
  topGenerateBtn.textContent = "🤖 Generate Emails";
  topGenerateBtn.addEventListener("click", startGeneration);

  _generateButtons.length = 0;
  _generateButtons.push(topGenerateBtn, generateBtn);

  topActions.append(topActionsNote, topGenerateBtn);
  selActions.append(selAllBtn, selNoneBtn, generateBtn);
  selCard.append(selTitle, selSub, filterRow, summary, topActions, companyList, selActions);

  // ── Progress card (hidden until job starts) ────────────
  const progCard = document.createElement("div");
  progCard.className = "card";
  progCard.id = "ai-progress-card";
  progCard.style.display = "none";

  const progTitle = document.createElement("div");
  progTitle.className = "card-title";
  progTitle.textContent = "⏳ Generating emails…";

  const progBar = document.createElement("div");
  progBar.style.cssText = "height:8px;background:var(--border);border-radius:4px;overflow:hidden;margin:12px 0 6px";
  const progFill = document.createElement("div");
  progFill.id = "ai-prog-fill";
  progFill.style.cssText = "height:100%;background:var(--primary);width:0%;transition:width .4s";
  progBar.appendChild(progFill);

  const progMsg = document.createElement("div");
  progMsg.id = "ai-prog-msg";
  progMsg.style.cssText = "font-size:12.5px;color:var(--text-muted)";

  progCard.append(progTitle, progBar, progMsg);

  container.replaceChildren(ctxCard, selCard, progCard);
  loadCompanies();
}

async function loadCompanies() {
  const list = document.getElementById("ai-company-list");
  if (!list) return;

  try {
    const response = await API.get("/api/ai/companies");
    const companies = Array.isArray(response)
      ? response
      : Array.isArray(response.companies)
        ? response.companies
        : [];

    _aiStats = response && !Array.isArray(response)
      ? (response.stats || response.summary || null)
      : null;

    _allCompanies = companies;
    renderAIStats(_aiStats);
    renderCompanyList("all");
  } catch (e) {
    list.textContent = "Failed to load companies: " + e.message;
  }
}

function renderAIStats(stats) {
  const el = document.getElementById("ai-company-summary");
  if (!el) return;
  if (!stats) {
    el.textContent = "";
    return;
  }
  const eligible = stats.eligible_companies ?? 0;
  const contacted = stats.excluded_already_contacted ?? 0;
  const drafts = stats.excluded_already_has_draft ?? 0;
  const noEmail = stats.excluded_no_email ?? 0;
  el.textContent = `Eligible companies: ${eligible} · Excluded already contacted: ${contacted} · Excluded already has draft: ${drafts} · Excluded no email: ${noEmail}`;
}

function renderCompanyList(filter) {
  const list = document.getElementById("ai-company-list");
  if (!list) return;
  list.replaceChildren();

  const safeCompanies = Array.isArray(_allCompanies) ? _allCompanies : [];

  const visible = safeCompanies.filter((c) => {
    if (filter === "agencies") return c.type === "agency";
    if (filter === "clients") return c.type === "client";
    return true;
  });

  if (!visible.length) {
    const msg = document.createElement("div");
    msg.style.cssText = "color:var(--text-muted);font-size:13px;padding:20px 0;text-align:center";
    msg.textContent = "No companies with email addresses found. Scrape some agencies first.";
    list.appendChild(msg);
    return;
  }

  visible.forEach((c) => {
    const noEmail = !c.has_email;

    const row = document.createElement("div");
    row.className = noEmail ? "company-row is-disabled" : "company-row";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "company-checkbox";
    cb.value = c.id;
    cb.checked = !c.has_draft && !noEmail;
    cb.disabled = noEmail;  // Never allow selecting companies without a real email
    cb.addEventListener("change", syncGenerateButtonsState);

    const name = document.createElement("span");
    name.className = "company-name";
    name.textContent = c.name;

    const emailSpan = document.createElement("span");
    emailSpan.className = "company-email";
    if (noEmail) {
      emailSpan.textContent = "No email found — contact via website form";
    } else {
      emailSpan.textContent = c.email;
    }

    const badge = document.createElement("span");
    if (noEmail) {
      badge.className = "badge badge-red";
      badge.textContent = "No email";
    } else if (c.has_draft) {
      badge.className = "badge badge-green";
      badge.textContent = "Draft exists";
    } else {
      badge.className = "badge badge-gray";
      badge.textContent = c.type;
    }

    // Make the whole row a label only when email exists
    if (!noEmail) {
      row.style.cursor = "pointer";
      row.addEventListener("click", (e) => {
        if (e.target !== cb) {
          cb.checked = !cb.checked;
          syncGenerateButtonsState();
        }
      });
    }

    row.append(cb, name, emailSpan, badge);
    list.appendChild(row);
  });

  syncGenerateButtonsState();
}

async function startGeneration() {
  const selected = [...document.querySelectorAll(".company-checkbox:checked")].map((cb) =>
    parseInt(cb.value)
  );
  if (!selected.length) {
    toast("Select at least one company.", "error");
    return;
  }

  _setGenerateButtonsState(true);

  const senderCtx = {
    sender_name: document.getElementById("ai-sender-name")?.value || "",
    sender_role: document.getElementById("ai-sender-role")?.value || "",
    sender_company: document.getElementById("ai-sender-company")?.value || "",
    sender_email: document.getElementById("ai-sender-email")?.value || "",
    value_prop: document.getElementById("ai-value-prop")?.value || "",
  };

  const progCard = document.getElementById("ai-progress-card");
  if (progCard) progCard.style.display = "";

  try {
    const res = await API.post("/api/ai/generate/batch", {
      company_ids: selected,
      sender: senderCtx,
    });
    if (!res.ok) {
      toast(res.message, "error");
      _setGenerateButtonsState(false);
      return;
    }
    _pollAIJob(res.job_id);
  } catch (e) {
    toast("Generation failed: " + e.message, "error");
    _setGenerateButtonsState(false);
  }
}

function _setGenerateButtonsState(isLoading) {
  const hasSelection = document.querySelectorAll(".company-checkbox:checked").length > 0;
  _generateButtons.forEach((btn) => {
    btn.disabled = isLoading || !hasSelection;
    btn.textContent = isLoading ? "⏳ Generating…" : "🤖 Generate Emails";
  });
}

function syncGenerateButtonsState() {
  _setGenerateButtonsState(false);
}

function _pollAIJob(jobId) {
  if (_aiPollTimer) clearInterval(_aiPollTimer);
  _aiPollTimer = setInterval(async () => {
    try {
      const job = await API.get(`/api/ai/job/${jobId}`);
      const fill = document.getElementById("ai-prog-fill");
      const msg = document.getElementById("ai-prog-msg");
      if (fill) fill.style.width = job.progress + "%";
      if (msg) msg.textContent = job.message;

      if (job.status === "done") {
        clearInterval(_aiPollTimer);
        _setGenerateButtonsState(false);
        toast(job.message + " Go to Review Queue.", "success");
        loadCompanies();
      } else if (job.status === "error") {
        clearInterval(_aiPollTimer);
        _setGenerateButtonsState(false);
        toast("Generation error: " + job.message, "error");
      }
    } catch (_) {}
  }, 2000);
}

function _field(id, label, type, placeholder) {
  const group = document.createElement("div");
  group.className = "form-group";
  const lbl = document.createElement("label");
  lbl.textContent = label;
  lbl.setAttribute("for", id);
  const input = document.createElement("input");
  input.type = type;
  input.id = id;
  input.placeholder = placeholder;
  group.append(lbl, input);
  return group;
}

window.init_ai_engine = function () {
  buildAIEngineUI();
};
