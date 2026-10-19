/* ════════════════════════════════════════════════════════
   clients.js — Potential Clients (Google Maps scraper) page
   ════════════════════════════════════════════════════════ */

const ALL_CATEGORIES = [
  "Law Firms", "Dental Clinics", "Medical Centres", "Real Estate",
  "Accountants", "Restaurants", "Gyms", "Tradies",
];
const ALL_SUBURBS = ["Brighton", "South Yarra", "St Kilda", "CBD", "Richmond"];
let categoryChoices = ALL_CATEGORIES.slice();
let locationChoices = ALL_SUBURBS.slice();
let clientSearchTitle = "";

// Persisted across navigations so we can resume polling if the user leaves mid-scrape
let _clientsJobId = sessionStorage.getItem("clients_job_id") || null;
let _clientsPollTimer = null;
const CLIENTS_PAGE_SIZE = 8;
let _clientsPage = 1;
let _clientsLoading = false;

// ─── Page init ────────────────────────────────────────────
async function buildClientsUI() {
  try {
    const [cats, subs, status] = await Promise.all([
      API.get("/api/scraper/meta/categories"),
      API.get("/api/scraper/meta/suburbs"),
      API.get("/api/setup/status"),
    ]);
    if (Array.isArray(cats) && cats.length) categoryChoices = cats;
    if (Array.isArray(subs) && subs.length) locationChoices = subs;
    clientSearchTitle = status.client_search_title || "";
    if (clientSearchTitle) {
      const header = document.querySelector("#page-clients .page-header p");
      if (header) header.textContent = clientSearchTitle + ".";
    }
  } catch (_) {}

  const container = document.getElementById("clients-content");
  container.replaceChildren(
    _makeSearchCard(),
    _makeResultsCard(),
  );
  await loadClients();

  if (_clientsJobId) {
    _resumeJobIfRunning(_clientsJobId);
  }
}

async function _resumeJobIfRunning(jobId) {
  try {
    const job = await API.get(`/api/scraper/clients/job/${jobId}`);
    if (job.status === "running" || job.status === "queued") {
      const progressWrap = document.getElementById("clients-progress-wrap");
      if (progressWrap) progressWrap.style.display = "";
      const btn = document.getElementById("clients-search-btn");
      if (btn) { btn.disabled = true; btn.textContent = "Searching…"; }
      _setProgress(job.progress || 0, job.message || "Resuming…");
      _pollClientsJob();
    } else {
      sessionStorage.removeItem("clients_job_id");
      _clientsJobId = null;
    }
  } catch (_) {
    sessionStorage.removeItem("clients_job_id");
    _clientsJobId = null;
  }
}

// ─── Search card ──────────────────────────────────────────
function _makeSearchCard() {
  const card = document.createElement("div");
  card.className = "card clients-search-card";

  const title = document.createElement("div");
  title.className = "card-title";
  title.textContent = clientSearchTitle || "Search businesses";

  const sub = document.createElement("div");
  sub.className = "card-subtitle";
  sub.textContent = "Select business categories and suburbs, then click Search to find potential clients via Google Maps.";

  const layout = document.createElement("div");
  layout.className = "clients-search-layout";

  const catBlock = document.createElement("div");
  catBlock.className = "clients-search-block";
  const catLabel = document.createElement("div");
  catLabel.className = "clients-search-label";
  catLabel.textContent = "Categories";
  const catHint = document.createElement("div");
  catHint.className = "clients-search-hint";
  catHint.textContent = "Choose the types of businesses you want to search.";
  const catGrid = document.createElement("div");
  catGrid.className = "clients-chip-grid";
  catGrid.id = "cat-grid";

  categoryChoices.forEach((cat) => {
    const label = document.createElement("label");
    label.className = "clients-chip";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = cat;
    cb.className = "cat-checkbox";
    cb.checked = true;

    label.append(cb, document.createTextNode(cat));
    catGrid.appendChild(label);
  });
  catBlock.append(catLabel, catHint, catGrid);

  const subBlock = document.createElement("div");
  subBlock.className = "clients-search-block";
  const subLabel = document.createElement("div");
  subLabel.className = "clients-search-label";
  subLabel.textContent = "Suburbs / Location";
  const subHint = document.createElement("div");
  subHint.className = "clients-search-hint";
  subHint.textContent = "Each suburb searches a 2 km area using the current Google Maps setup.";
  const subGrid = document.createElement("div");
  subGrid.className = "clients-chip-grid";
  subGrid.id = "sub-grid";

  locationChoices.forEach((s) => {
    const label = document.createElement("label");
    label.className = "clients-chip";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = s;
    cb.className = "sub-checkbox";
    cb.checked = true;

    label.append(cb, document.createTextNode(s));
    subGrid.appendChild(label);
  });
  subBlock.append(subLabel, subHint, subGrid);

  const sideCol = document.createElement("div");
  sideCol.className = "clients-search-side";

  const limitBlock = document.createElement("div");
  limitBlock.className = "clients-search-block";
  const limitLabel = document.createElement("div");
  limitLabel.className = "clients-search-label";
  limitLabel.textContent = "Result Limit";
  const limitHint = document.createElement("div");
  limitHint.className = "clients-search-hint";
  limitHint.textContent = "The exact save limit comes from Settings. The search response shows the live value when the job starts.";
  const limitInfo = document.createElement("div");
  limitInfo.className = "clients-limit-note";
  limitInfo.textContent = "Configured in Settings -> Max clients per search";
  limitBlock.append(limitLabel, limitHint, limitInfo);

  const actionsBlock = document.createElement("div");
  actionsBlock.className = "clients-search-block";
  const actionLabel = document.createElement("div");
  actionLabel.className = "clients-search-label";
  actionLabel.textContent = "Search Controls";
  const actionHint = document.createElement("div");
  actionHint.className = "clients-search-hint";
  actionHint.textContent = "Start a Google Maps search, or quickly select/clear all filters before running it.";

  const actRow = document.createElement("div");
  actRow.className = "clients-action-row";

  const searchBtn = document.createElement("button");
  searchBtn.className = "btn btn-primary";
  searchBtn.id = "clients-search-btn";
  searchBtn.textContent = "Search Google Maps";
  searchBtn.addEventListener("click", startClientSearch);

  const selectAllBtn = document.createElement("button");
  selectAllBtn.className = "btn btn-ghost btn-sm";
  selectAllBtn.textContent = "Select all";
  selectAllBtn.addEventListener("click", () => {
    document.querySelectorAll(".cat-checkbox, .sub-checkbox").forEach((cb) => { cb.checked = true; });
  });

  const clearBtn = document.createElement("button");
  clearBtn.className = "btn btn-ghost btn-sm";
  clearBtn.textContent = "Clear all";
  clearBtn.addEventListener("click", () => {
    document.querySelectorAll(".cat-checkbox, .sub-checkbox").forEach((cb) => { cb.checked = false; });
  });

  actRow.append(searchBtn, selectAllBtn, clearBtn);

  const progressWrap = document.createElement("div");
  progressWrap.id = "clients-progress-wrap";
  progressWrap.className = "clients-progress-wrap";
  progressWrap.style.display = "none";

  const progressBar = document.createElement("div");
  progressBar.className = "clients-progress-bar";

  const progressFill = document.createElement("div");
  progressFill.id = "clients-progress-fill";
  progressFill.className = "clients-progress-fill";
  progressBar.appendChild(progressFill);

  const progressMsg = document.createElement("div");
  progressMsg.id = "clients-progress-msg";
  progressMsg.className = "clients-progress-msg";

  progressWrap.append(progressBar, progressMsg);
  actionsBlock.append(actionLabel, actionHint, actRow, progressWrap);

  sideCol.append(limitBlock, actionsBlock);
  layout.append(catBlock, subBlock, sideCol);

  card.append(title, sub, layout);
  return card;
}

// ─── Results card ─────────────────────────────────────────
function _makeResultsCard() {
  const card = document.createElement("div");
  card.className = "card";

  const header = document.createElement("div");
  header.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px";

  const title = document.createElement("div");
  title.className = "card-title";
  title.id = "clients-list-title";
  title.textContent = "Potential Clients";

  const refreshBtn = document.createElement("button");
  refreshBtn.className = "btn btn-ghost btn-sm";
  refreshBtn.textContent = "⟳ Refresh";
  refreshBtn.addEventListener("click", loadClients);

  header.append(title, refreshBtn);

  const nextStep = document.createElement("div");
  nextStep.id = "clients-next-step";
  nextStep.className = "alert alert-success";
  nextStep.style.display = "none";
  nextStep.textContent = "Next step: generate emails only for clients with a real email.";

  const listBody = document.createElement("div");
  listBody.id = "clients-list";

  card.append(header, nextStep, listBody);
  return card;
}

// ─── Start search job ─────────────────────────────────────
async function startClientSearch() {
  const categories = [...document.querySelectorAll(".cat-checkbox:checked")].map((cb) => cb.value);
  const suburbs = [...document.querySelectorAll(".sub-checkbox:checked")].map((cb) => cb.value);

  if (!categories.length || !suburbs.length) {
    toast("Select at least one category and one suburb.", "error");
    return;
  }

  const btn = document.getElementById("clients-search-btn");
  btn.disabled = true;
  btn.textContent = "Searching…";

  const progressWrap = document.getElementById("clients-progress-wrap");
  progressWrap.style.display = "";
  _setProgress(0, "Starting search…");

  try {
    const res = await API.post("/api/scraper/clients/search", { categories, suburbs });
    if (!res.ok) {
      toast(res.message || "Failed to start search.", "error");
      btn.disabled = false;
      btn.textContent = "Search Google Maps";
      return;
    }
    _clientsJobId = res.job_id;
    sessionStorage.setItem("clients_job_id", _clientsJobId);
    if (res.max_results) {
      _setProgress(0, `Starting — will save up to ${res.max_results} clients (configurable in Settings).`);
    }
    _pollClientsJob();
  } catch (e) {
    toast("Error: " + e.message, "error");
    btn.disabled = false;
    btn.textContent = "Search Google Maps";
  }
}

function _setProgress(pct, msg) {
  const fill = document.getElementById("clients-progress-fill");
  const msgEl = document.getElementById("clients-progress-msg");
  if (fill) fill.style.width = pct + "%";
  if (msgEl) msgEl.textContent = msg;
}

function _pollClientsJob() {
  if (_clientsPollTimer) clearInterval(_clientsPollTimer);
  _clientsPollTimer = setInterval(async () => {
    if (!_clientsJobId) { clearInterval(_clientsPollTimer); return; }
    try {
      const job = await API.get(`/api/scraper/clients/job/${_clientsJobId}`);
      _setProgress(job.progress || 0, job.message || "");

      if (job.status === "done" || job.status === "error") {
        clearInterval(_clientsPollTimer);
        _clientsPollTimer = null;
        _clientsJobId = null;
        sessionStorage.removeItem("clients_job_id");

        const btn = document.getElementById("clients-search-btn");
        if (btn) { btn.disabled = false; btn.textContent = "Search Google Maps"; }

        if (job.status === "done") {
          toast(job.message, "success");
          _clientsPage = 1;
          await loadClients();
        } else {
          toast("Search error: " + job.message, "error");
        }
      }
    } catch (e) {
      clearInterval(_clientsPollTimer);
    }
  }, 2000);
}

// ─── Load and render results ──────────────────────────────
function _listLoading(message) {
  const loading = document.createElement("div");
  loading.className = "list-loading";
  loading.textContent = message;
  return loading;
}

async function loadClients(page, scroll) {
  const list = document.getElementById("clients-list");
  const titleEl = document.getElementById("clients-list-title");
  if (!list || _clientsLoading) return;
  if (typeof page === "number") _clientsPage = page;
  _clientsLoading = true;
  list.replaceChildren(_listLoading("Loading clients…"));

  try {
    const data = await API.get(
      "/api/scraper/clients?page=" + _clientsPage + "&page_size=" + CLIENTS_PAGE_SIZE
    );
    const items = Array.isArray(data) ? data : (data.items || []);
    const total = Array.isArray(data) ? items.length : data.total;
    const pages = Array.isArray(data) ? 1 : data.pages;
    if (!Array.isArray(data) && data.page) _clientsPage = data.page;
    if (titleEl) titleEl.textContent = `Potential Clients (${total})`;
    renderClients(items, total, pages, list);
    if (scroll) {
      const title = document.getElementById("clients-list-title");
      if (title) title.scrollIntoView({ block: "start" });
    }
  } catch (e) {
    list.textContent = "Failed to load: " + e.message;
  } finally {
    _clientsLoading = false;
  }
}

function renderClients(clients, total, pages, container) {
  container.replaceChildren();
  const nextStep = document.getElementById("clients-next-step");
  if (nextStep) nextStep.style.display = total ? "" : "none";

  if (!total) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.style.padding = "40px";
    const icon = document.createElement("div");
    icon.className = "empty-icon";
    icon.textContent = "🏢";
    const h3 = document.createElement("h3");
    h3.textContent = "No clients found yet";
    const p = document.createElement("p");
    p.textContent = "No clients found yet. Start a search above.";
    empty.append(icon, h3, p);
    container.appendChild(empty);
    return;
  }

  const start = (_clientsPage - 1) * CLIENTS_PAGE_SIZE;
  container.append(
    _clientPager(total, start, clients.length, pages),
    _buildClientCards(clients),
    _clientPager(total, start, clients.length, pages),
  );
}

function _clientPager(total, start, count, pages) {
  const bar = document.createElement("div");
  bar.className = "list-pager";

  const note = document.createElement("div");
  note.className = "list-pager-note";
  const from = total ? start + 1 : 0;
  const to = start + count;
  note.textContent = `Showing ${from}–${to} of ${total}`;

  const actions = document.createElement("div");
  actions.className = "list-pager-actions";

  const prev = document.createElement("button");
  prev.type = "button";
  prev.className = "btn btn-ghost btn-sm";
  prev.textContent = "Previous";
  prev.disabled = _clientsPage <= 1;
  prev.addEventListener("click", () => loadClients(_clientsPage - 1, true));

  const position = document.createElement("span");
  position.className = "list-pager-note";
  position.textContent = `Page ${_clientsPage} of ${pages}`;

  const next = document.createElement("button");
  next.type = "button";
  next.className = "btn btn-ghost btn-sm";
  next.textContent = "Next";
  next.disabled = _clientsPage >= pages;
  next.addEventListener("click", () => loadClients(_clientsPage + 1, true));

  actions.append(prev, position, next);
  bar.append(note, actions);
  return bar;
}

function _buildClientCards(clients) {
  const grid = document.createElement("div");
  grid.className = "clients-card-grid";

  clients.forEach((c) => {
    const card = document.createElement("div");
    card.className = "clients-client-card";

    const top = document.createElement("div");
    top.className = "clients-card-top";

    const name = document.createElement("div");
    name.className = "clients-card-title";
    name.textContent = c.name;

    const badge = document.createElement("span");
    badge.className = `badge ${c.email ? "badge-green" : "badge-red"}`;
    badge.textContent = c.email ? "Email found" : "No email found";

    top.append(name, badge);

    const meta = document.createElement("div");
    meta.className = "clients-card-meta";
    meta.textContent = [c.category || "—", c.source || "google_maps"].filter(Boolean).join(" • ");

    const details = document.createElement("div");
    details.className = "clients-card-details";

    const websiteValue = c.website || "No website";
    const emailValue = c.email || "No email found";
    const phoneValue = c.phone || "No phone";
    const addressValue = c.address || "No address";

    [
      ["Website", websiteValue, c.website],
      ["Email", emailValue, false],
      ["Phone", phoneValue, false],
      ["Address", addressValue, false],
    ].forEach(([labelText, valueText, isLink]) => {
      const row = document.createElement("div");
      row.className = "clients-card-row";
      const label = document.createElement("span");
      label.className = "clients-card-label";
      label.textContent = labelText;
      const value = isLink ? document.createElement("a") : document.createElement("span");
      value.className = "clients-card-value";
      if (isLink) {
        value.href = valueText;
        value.target = "_blank";
        value.rel = "noopener noreferrer";
        value.textContent = valueText;
      } else {
        value.textContent = valueText;
      }
      row.append(label, value);
      details.appendChild(row);
    });

    const footer = document.createElement("div");
    footer.className = "clients-card-footer";

    const scoreBlock = document.createElement("div");
    scoreBlock.className = "clients-card-score";
    const scoreVal = c.digital_score ?? 0;
    const scoreColor = scoreVal >= 5 ? "var(--success)" : scoreVal >= 3 ? "var(--warning)" : "var(--error)";
    const scoreMain = document.createElement("div");
    scoreMain.style.cssText = `font-weight:700;color:${scoreColor};font-size:14px`;
    scoreMain.textContent = `${scoreVal}/6`;
    const scoreMeta = document.createElement("div");
    scoreMeta.className = "clients-card-score-meta";
    scoreMeta.textContent = c.rating ? `Rating ★ ${c.rating}` : "No rating";
    scoreBlock.append(scoreMain, scoreMeta);

    const actions = document.createElement("div");
    actions.className = "clients-card-actions";

    if (c.website) {
      const openBtn = document.createElement("a");
      openBtn.href = c.website;
      openBtn.target = "_blank";
      openBtn.rel = "noopener noreferrer";
      openBtn.className = "btn btn-ghost btn-sm";
      openBtn.textContent = "Open website";
      actions.appendChild(openBtn);
    }

    const delBtn = document.createElement("button");
    delBtn.className = "btn btn-danger btn-sm";
    delBtn.textContent = "Delete";
    delBtn.title = "Delete";
    delBtn.addEventListener("click", () => deleteClient(c.id));
    actions.appendChild(delBtn);

    footer.append(scoreBlock, actions);
    card.append(top, meta, details, footer);
    grid.appendChild(card);
  });

  return grid;
}

async function deleteClient(id) {
  try {
    await API.del(`/api/scraper/clients/${id}`);
    await loadClients();
    toast("Client removed.", "info");
  } catch (e) {
    toast("Delete failed: " + e.message, "error");
  }
}

window.init_clients = buildClientsUI;
