/* ════════════════════════════════════════════════════════
   app.js — routing, navigation, shared utilities
   ════════════════════════════════════════════════════════ */

// ─── Shared API helper with error boundaries ───────────────
const API = {
  async get(path, options = {}) {
    const { requireAuth = false, retryCount = 1 } = options;
    let lastError = null;

    for (let attempt = 0; attempt <= retryCount; attempt++) {
      try {
        const r = await fetch(path, {
          headers: { "Content-Type": "application/json" },
        });

        if (!r.ok) {
          const errorBody = await r.json().catch(() => ({}));
          const error = new Error(`GET ${path} → ${r.status}: ${errorBody.message || r.statusText}`);
          error.status = r.status;
          error.data = errorBody;
          throw error;
        }

        return await r.json();
      } catch (e) {
        lastError = e;
        // Don't retry on client errors (4xx)
        if (e.status && e.status >= 400 && e.status < 500) {
          break;
        }
        if (attempt < retryCount) {
          await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
        }
      }
    }

    throw lastError || new Error(`GET ${path} failed`);
  },

  async post(path, body, options = {}) {
    const { retryCount = 0 } = options;
    let lastError = null;

    for (let attempt = 0; attempt <= retryCount; attempt++) {
      try {
        const r = await fetch(path, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });

        const data = await r.json().catch(() => ({}));

        if (!r.ok) {
          const error = new Error(`POST ${path} → ${r.status}: ${data.message || r.statusText}`);
          error.status = r.status;
          error.data = data;
          throw error;
        }

        return data;
      } catch (e) {
        lastError = e;
        if (e.status && e.status >= 400 && e.status < 500) {
          break;
        }
        if (attempt < retryCount) {
          await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
        }
      }
    }

    throw lastError || new Error(`POST ${path} failed`);
  },

  async patch(path, body, options = {}) {
    const { retryCount = 0 } = options;
    let lastError = null;

    for (let attempt = 0; attempt <= retryCount; attempt++) {
      try {
        const r = await fetch(path, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: body !== undefined ? JSON.stringify(body) : undefined,
        });

        const data = await r.json().catch(() => ({}));

        if (!r.ok) {
          const error = new Error(`PATCH ${path} → ${r.status}: ${data.message || r.statusText}`);
          error.status = r.status;
          error.data = data;
          throw error;
        }

        return data;
      } catch (e) {
        lastError = e;
        if (e.status && e.status >= 400 && e.status < 500) {
          break;
        }
        if (attempt < retryCount) {
          await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
        }
      }
    }

    throw lastError || new Error(`PATCH ${path} failed`);
  },

  async del(path, options = {}) {
    const { retryCount = 0 } = options;
    let lastError = null;

    for (let attempt = 0; attempt <= retryCount; attempt++) {
      try {
        const r = await fetch(path, { method: "DELETE" });
        const data = await r.json().catch(() => ({}));

        if (!r.ok) {
          const error = new Error(`DELETE ${path} → ${r.status}: ${data.message || r.statusText}`);
          error.status = r.status;
          error.data = data;
          throw error;
        }

        return data;
      } catch (e) {
        lastError = e;
        if (e.status && e.status >= 400 && e.status < 500) {
          break;
        }
        if (attempt < retryCount) {
          await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
        }
      }
    }

    throw lastError || new Error(`DELETE ${path} failed`);
  },
};

// ─── Error boundary for async operations ──────────────────
async function withErrorBoundary(asyncFn, errorMessage = "Operation failed", options = {}) {
  const { showToast = true, onError = null } = options;
  try {
    return await asyncFn();
  } catch (e) {
    const msg = e.message || errorMessage;
    if (showToast) {
      toast(msg, "error");
    }
    if (onError) {
      onError(e);
    }
    // Log to console for debugging
    console.error(`[ErrorBoundary] ${errorMessage}:`, e);
    return null;
  }
}

// ─── Toast ────────────────────────────────────────────────
function toast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast ${type}`;

  const icon = document.createElement("span");
  icon.textContent = type === "success" ? "✓" : type === "error" ? "✕" : "ℹ";

  const text = document.createElement("span");
  text.textContent = message;

  el.append(icon, " ", text);
  container.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ─── SPA Navigation ───────────────────────────────────────
let _needsSetup = false;

function syncSetupLock() {
  const note = document.getElementById("sidebar-setup-note");
  if (note) note.hidden = !_needsSetup;
  document.querySelectorAll(".nav-item").forEach((item) => {
    if (!item.dataset.idleTitle) item.dataset.idleTitle = item.getAttribute("title") || "";
    item.classList.toggle("is-locked", _needsSetup);
    item.title = _needsSetup ? "Finish setup to open this page" : item.dataset.idleTitle;
  });
}

function navigate(page, fromClick) {
  if (_needsSetup && page !== "setup") {
    if (fromClick) toast("Finish setup on this page first. The menu opens after that.", "info");
    page = "setup";
  }
  if (!_needsSetup && page === "setup") page = "dashboard";
  syncSetupLock();
  history.replaceState(null, "", `#${page}`);

  document.querySelectorAll(".section").forEach((s) => s.classList.remove("active"));
  const target = document.getElementById(`page-${page}`);
  if (target) target.classList.add("active");

  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.page === page);
  });

  const initFn = window[`init_${page.replace(/-/g, "_")}`];
  if (typeof initFn === "function") initFn();
}

document.querySelectorAll(".nav-item").forEach((item) => {
  item.addEventListener("click", (e) => {
    e.preventDefault();
    navigate(item.dataset.page, true);
  });
});

// ─── Dashboard checklist (safe DOM construction) ──────────
function makeCheckRow(label, done) {
  const row = document.createElement("div");
  row.style.cssText =
    "display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--border)";

  const icon = document.createElement("span");
  icon.style.fontSize = "18px";
  icon.textContent = done ? "✅" : "⬜";

  const labelEl = document.createElement("span");
  labelEl.style.cssText = `color:${done ? "var(--text)" : "var(--text-muted)"};font-size:13.5px`;
  labelEl.textContent = label;

  row.append(icon, labelEl);

  if (!done) {
    const btn = document.createElement("button");
    btn.className = "btn btn-outline btn-sm";
    btn.style.marginLeft = "auto";
    btn.textContent = "Configure →";
    btn.addEventListener("click", () => navigate("settings"));
    row.appendChild(btn);
  }

  return row;
}

async function renderDashboard() {
  const settings = await withErrorBoundary(
    () => API.get("/api/settings"),
    "Failed to load settings",
    { showToast: false }
  ) || {};

  const systemStatus = await withErrorBoundary(
    () => API.get("/api/system/status"),
    "Failed to load system status",
    { showToast: false }
  ) || {};

  const checks = [
    { label: "Gmail SMTP configured", done: !!(settings.GMAIL_SMTP_USER && settings.GMAIL_SMTP_PASSWORD === "••••••••") },
    { label: "Custom mailbox configured", done: !!(settings.CUSTOM_SMTP_USER && settings.CUSTOM_SMTP_PASSWORD === "••••••••") },
    { label: "Claude API key set", done: settings.CLAUDE_API_KEY === "••••••••" },
    { label: "Google Maps API key set", done: settings.GOOGLE_MAPS_API_KEY === "••••••••" },
    { label: "Google Sheets ID configured", done: !!settings.GOOGLE_SHEETS_ID },
    { label: "Database connected", done: systemStatus?.database_connected === true },
  ];

  const checklist = document.getElementById("checklist");
  if (checklist) {
    checklist.replaceChildren(...checks.map((c) => makeCheckRow(c.label, c.done)));
  }
  renderLocalSystemControls(systemStatus);

  // Stats - load in parallel with individual error handling
  const statsPromises = {
    clients: withErrorBoundary(() => API.get("/api/scraper/clients?page=1&page_size=1"), "Failed to load clients", { showToast: false }),
    agencies: withErrorBoundary(() => API.get("/api/scraper/agencies?page=1&page_size=1"), "Failed to load agencies", { showToast: false }),
    review: withErrorBoundary(() => API.get("/api/review"), "Failed to load review queue", { showToast: false }),
    crm: withErrorBoundary(() => API.get("/api/crm"), "Failed to load CRM", { showToast: false }),
  };

  const stats = await Promise.all(Object.values(statsPromises));
  const [clients, agencies, review, crm] = stats;

  const statMappings = {
    "stat-clients": clients?.total ?? clients?.length ?? 0,
    "stat-agencies": agencies?.total ?? agencies?.length ?? 0,
    "stat-pending": review?.length || 0,
    "stat-sent": crm?.filter((r) => r.status === "sent")?.length || 0,
  };

  Object.entries(statMappings).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  });

  const badge = document.getElementById("review-badge");
  if (badge) {
    badge.textContent = review?.length || 0;
    badge.style.display = (review?.length || 0) > 0 ? "" : "none";
  }
}

function restartCommand(systemStatus) {
  if (systemStatus && systemStatus.restart_command) return systemStatus.restart_command;
  const windows = navigator.userAgent.includes("Windows");
  return windows ? "start.bat" : "./start.sh";
}

function renderLocalSystemControls(systemStatus) {
  const container = document.getElementById("local-system-controls");
  if (!container) return;
  const command = restartCommand(systemStatus);

  const wrap = document.createElement("div");

  const actions = document.createElement("div");
  actions.style.cssText = "display:flex;gap:10px;align-items:center;flex-wrap:wrap";

  const stopBtn = document.createElement("button");
  stopBtn.className = "btn btn-danger";
  stopBtn.textContent = "Stop system";
  stopBtn.addEventListener("click", () => stopLocalSystem(command));

  actions.appendChild(stopBtn);

  const note = document.createElement("div");
  note.style.cssText = "font-size:12.5px;color:var(--text-muted);margin-top:12px;line-height:1.7";
  note.textContent = "Restart is not exposed in-app because the current local process cannot safely restart itself without an external supervisor. To restart, stop the system here and run " + command + ".";

  wrap.append(actions, note);
  container.replaceChildren(wrap);
}

async function stopLocalSystem(command) {
  const confirmed = window.confirm("Stop Nearletter now? You will need to run " + command + " to bring it back.");
  if (!confirmed) return;

  await withErrorBoundary(
    async () => {
      const res = await API.post("/api/system/stop", {});
      toast(res.message || "System stop requested.", res.ok ? "success" : "error");
      return res;
    },
    "Failed to stop system"
  );
}

window.init_dashboard = renderDashboard;

// ─── Boot ─────────────────────────────────────────────────
window.addEventListener(
  "load",
  async () => {
    let status = { needs_setup: false };
    try {
      status = await API.get("/api/setup/status");
    } catch (_) {
      status = { needs_setup: false };
    }
    window.__setupStatus = status;
    _needsSetup = !!status.needs_setup;
    syncSetupLock();
    const sub = document.querySelector(".logo-sub");
    if (status.brand_name) {
      if (sub) sub.textContent = status.brand_name;
      document.title = "Nearletter — " + status.brand_name;
    } else if (status.needs_setup) {
      if (sub) sub.textContent = "Setup";
      document.title = "Nearletter";
    }
    const initialPage = _needsSetup ? "setup" : (location.hash.slice(1) || "dashboard");
    navigate(initialPage);
  },
  { once: true }
);
