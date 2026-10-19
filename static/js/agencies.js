/* ════════════════════════════════════════════════════════
   agencies.js — Agencies scraper page
   ════════════════════════════════════════════════════════ */

const KEYWORDS = ["React", "Next.js", "Vue", "WordPress", "Shopify", "Angular", "AI", "Webflow"];
let agencyLocationChoices = ["Queensland", "Gold Coast", "NSW", "Melbourne"];
const DEFAULT_MAX_AGENCIES = 25;

let _pollTimer = null;
const AGENCIES_PAGE_SIZE = 8;
let _agenciesPage = 1;
let _agenciesLoading = false;

async function buildAgenciesUI() {
  let agencyTitle = "";
  try {
    const [locations, status] = await Promise.all([
      API.get("/api/scraper/meta/agency-locations"),
      API.get("/api/setup/status"),
    ]);
    if (Array.isArray(locations) && locations.length) agencyLocationChoices = locations;
    agencyTitle = status.agency_search_title || "";
    if (agencyTitle) {
      const header = document.querySelector("#page-agencies .page-header p");
      if (header) header.textContent = agencyTitle + ".";
    }
  } catch (_) {}

  const container = document.getElementById("agencies-content");

  // ── Controls card ──────────────────────────────────────
  const ctrl = document.createElement("div");
  ctrl.className = "card";

  const title = document.createElement("div");
  title.className = "card-title";
  title.textContent = agencyTitle || "Scrape Australian Digital Agencies";

  const sub = document.createElement("div");
  sub.className = "card-subtitle";
  sub.textContent =
    "Searches DuckDuckGo, Clutch.co, and TechBehemoths. Capped at 25 new agencies per scrape.";

  const kwLabel = document.createElement("label");
  kwLabel.textContent = "Filter by tech stack:";
  kwLabel.style.cssText = "font-size:12.5px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:8px";

  const kwGrid = document.createElement("div");
  kwGrid.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px";

  const buildChip = (value, prefix, defaultChecked) => {
    const lbl = document.createElement("label");
    lbl.style.cssText =
      "display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border:1.5px solid var(--border);" +
      "border-radius:20px;cursor:pointer;font-size:13px;font-weight:500;user-select:none";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = value;
    cb.checked = defaultChecked;
    cb.id = `${prefix}-${value}`;

    const applyStyle = () => {
      lbl.style.borderColor = cb.checked ? "var(--primary)" : "var(--border)";
      lbl.style.background = cb.checked ? "var(--primary-light)" : "";
      lbl.style.color = cb.checked ? "var(--primary-dark)" : "";
    };
    cb.addEventListener("change", applyStyle);
    applyStyle();

    const span = document.createElement("span");
    span.textContent = value;
    lbl.append(cb, span);
    return lbl;
  };

  KEYWORDS.forEach((kw) => {
    const checked = ["React", "Next.js", "AI", "WordPress"].includes(kw);
    kwGrid.appendChild(buildChip(kw, "kw", checked));
  });

  // ── Location filter ───────────────────────────────────
  const locLabel = document.createElement("label");
  locLabel.textContent = "Filter by location:";
  locLabel.style.cssText = "font-size:12.5px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:8px";

  const locGrid = document.createElement("div");
  locGrid.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px";

  agencyLocationChoices.forEach((loc) => {
    locGrid.appendChild(buildChip(loc, "loc", true));  // all selected by default
  });

  // ── Max-results control ───────────────────────────────
  const maxLabel = document.createElement("label");
  maxLabel.textContent = "Max agencies per scrape:";
  maxLabel.style.cssText = "font-size:12.5px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:8px";

  const maxRow = document.createElement("div");
  maxRow.style.cssText = "display:flex;align-items:center;gap:10px;margin-bottom:18px";

  const maxInput = document.createElement("input");
  maxInput.type = "number";
  maxInput.id = "max-agencies";
  maxInput.min = "1";
  maxInput.max = "100";
  maxInput.value = String(DEFAULT_MAX_AGENCIES);
  maxInput.style.cssText =
    "width:90px;padding:6px 10px;border:1.5px solid var(--border);border-radius:8px;font-size:13px";

  const maxHint = document.createElement("span");
  maxHint.textContent = "(default 25, max 100)";
  maxHint.style.cssText = "font-size:12px;color:var(--text-muted)";

  maxRow.append(maxInput, maxHint);

  const row = document.createElement("div");
  row.style.cssText = "display:flex;align-items:center;gap:12px";

  const scrapeBtn = document.createElement("button");
  scrapeBtn.className = "btn btn-primary";
  scrapeBtn.id = "scrape-btn";
  scrapeBtn.textContent = "🕷 Start Scrape";
  scrapeBtn.addEventListener("click", startScrape);

  const progressWrap = document.createElement("div");
  progressWrap.id = "scrape-progress";
  progressWrap.style.display = "none";
  progressWrap.style.cssText = "flex:1;display:none";

  const bar = document.createElement("div");
  bar.style.cssText =
    "height:6px;background:var(--border);border-radius:4px;overflow:hidden;margin-bottom:4px";
  const fill = document.createElement("div");
  fill.id = "progress-fill";
  fill.style.cssText = "height:100%;background:var(--primary);width:0%;transition:width .3s";
  bar.appendChild(fill);

  const msg = document.createElement("div");
  msg.id = "progress-msg";
  msg.style.cssText = "font-size:12px;color:var(--text-muted)";

  progressWrap.append(bar, msg);
  row.append(scrapeBtn, progressWrap);
  ctrl.append(title, sub, kwLabel, kwGrid, locLabel, locGrid, maxLabel, maxRow, row);

  // ── Results card ───────────────────────────────────────
  const results = document.createElement("div");
  results.className = "card";
  results.id = "agencies-results";

  container.replaceChildren(ctrl, results);
  loadAgencies();
}

function selectedKeywords() {
  return KEYWORDS.filter((kw) => {
    const cb = document.getElementById(`kw-${kw}`);
    return cb && cb.checked;
  });
}

function selectedLocations() {
  return agencyLocationChoices.filter((loc) => {
    const cb = document.getElementById(`loc-${loc}`);
    return cb && cb.checked;
  });
}

function selectedMaxResults() {
  const el = document.getElementById("max-agencies");
  const n = parseInt(el?.value, 10);
  if (!Number.isFinite(n) || n < 1) return DEFAULT_MAX_AGENCIES;
  return Math.min(100, n);
}

async function startScrape() {
  const kws = selectedKeywords();
  if (!kws.length) {
    toast("Select at least one keyword filter.", "error");
    return;
  }
  const locs = selectedLocations();
  if (!locs.length) {
    toast("Select at least one location.", "error");
    return;
  }
  const maxResults = selectedMaxResults();

  const btn = document.getElementById("scrape-btn");
  btn.disabled = true;
  btn.textContent = "⏳ Scraping…";

  showProgress(0, "Starting…");

  try {
    const res = await API.post("/api/scraper/agencies/scrape", {
      keywords: kws,
      locations: locs,
      max_results: maxResults,
    });
    if (!res.ok) {
      toast(res.message, "error");
      btn.disabled = false;
      btn.textContent = "🕷 Start Scrape";
      return;
    }
    pollJob(res.job_id, btn);
  } catch (e) {
    toast("Scrape failed: " + e.message, "error");
    btn.disabled = false;
    btn.textContent = "🕷 Start Scrape";
  }
}

function showProgress(pct, msg) {
  const wrap = document.getElementById("scrape-progress");
  if (wrap) wrap.style.display = "flex";
  const fill = document.getElementById("progress-fill");
  if (fill) fill.style.width = pct + "%";
  const msgEl = document.getElementById("progress-msg");
  if (msgEl) msgEl.textContent = msg;
}

function pollJob(jobId, btn) {
  if (_pollTimer) clearInterval(_pollTimer);
  _pollTimer = setInterval(async () => {
    try {
      const job = await API.get(`/api/scraper/agencies/job/${jobId}`);
      showProgress(job.progress, job.message);
      if (job.status === "done") {
        clearInterval(_pollTimer);
        btn.disabled = false;
        btn.textContent = "🕷 Start Scrape";
        toast(job.message, "success");
        loadAgencies(1);
      } else if (job.status === "error") {
        clearInterval(_pollTimer);
        btn.disabled = false;
        btn.textContent = "🕷 Start Scrape";
        toast("Scrape error: " + job.message, "error");
      }
    } catch (_) {}
  }, 1500);
}

async function loadAgencies(page, scroll) {
  const container = document.getElementById("agencies-results");
  if (!container || _agenciesLoading) return;
  if (typeof page === "number") _agenciesPage = page;
  _agenciesLoading = true;

  const existing = container.querySelector(".data-list");
  if (existing) {
    existing.replaceChildren();
    const loading = document.createElement("div");
    loading.className = "list-loading";
    loading.textContent = "Loading agencies…";
    existing.appendChild(loading);
  } else {
    container.replaceChildren();
    const loading = document.createElement("div");
    loading.className = "list-loading";
    loading.textContent = "Loading agencies…";
    container.appendChild(loading);
  }

  try {
    const data = await API.get(
      "/api/scraper/agencies?page=" + _agenciesPage + "&page_size=" + AGENCIES_PAGE_SIZE
    );
    const items = Array.isArray(data) ? data : (data.items || []);
    const total = Array.isArray(data) ? items.length : data.total;
    const pages = Array.isArray(data) ? 1 : data.pages;
    if (!Array.isArray(data) && data.page) _agenciesPage = data.page;
    renderAgenciesTable(items, total, pages, container);
    if (scroll) container.scrollIntoView({ block: "start" });
  } catch (e) {
    container.textContent = "Failed to load agencies: " + e.message;
  } finally {
    _agenciesLoading = false;
  }
}

function _agencyPager(total, count, pages) {
  const bar = document.createElement("div");
  bar.className = "list-pager";
  const start = (_agenciesPage - 1) * AGENCIES_PAGE_SIZE;
  const note = document.createElement("div");
  note.className = "list-pager-note";
  note.textContent = total
    ? `Showing ${start + 1}–${start + count} of ${total}`
    : "Showing 0 of 0";

  const actions = document.createElement("div");
  actions.className = "list-pager-actions";
  const prev = document.createElement("button");
  prev.type = "button";
  prev.className = "btn btn-ghost btn-sm";
  prev.textContent = "Previous";
  prev.disabled = _agenciesPage <= 1;
  prev.addEventListener("click", () => loadAgencies(_agenciesPage - 1, true));
  const position = document.createElement("span");
  position.className = "list-pager-note";
  position.textContent = `Page ${_agenciesPage} of ${pages}`;
  const next = document.createElement("button");
  next.type = "button";
  next.className = "btn btn-ghost btn-sm";
  next.textContent = "Next";
  next.disabled = _agenciesPage >= pages;
  next.addEventListener("click", () => loadAgencies(_agenciesPage + 1, true));
  actions.append(prev, position, next);
  bar.append(note, actions);
  return bar;
}

function renderAgenciesTable(agencies, total, pages, container) {
  container.replaceChildren();

  const header = document.createElement("div");
  header.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px";

  const title = document.createElement("div");
  title.className = "card-title";
  title.textContent = `${total} Agencies Found`;

  const genBtn = document.createElement("button");
  genBtn.className = "btn btn-primary btn-sm";
  genBtn.textContent = "🤖 Generate emails";
  genBtn.addEventListener("click", () => {
    navigate("ai-engine");
    toast("Use AI Engine to generate emails for agencies that have an address.", "info");
  });

  header.append(title, genBtn);
  container.appendChild(header);

  if (!total) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.style.padding = "40px";
    const icon = document.createElement("div");
    icon.className = "empty-icon";
    icon.textContent = "🏢";
    const h3 = document.createElement("h3");
    h3.textContent = "No agencies scraped yet";
    const p = document.createElement("p");
    p.textContent = "Click 'Start Scrape' above to discover Australian digital agencies.";
    empty.append(icon, h3, p);
    container.appendChild(empty);
    return;
  }

  container.appendChild(_agencyPager(total, agencies.length, pages));
  const list = document.createElement("div");
  list.className = "data-list";
  agencies.forEach((a) => {
    const card = document.createElement("article");
    card.className = "data-card";

    const title = document.createElement("div");
    title.className = "data-card-title";
    title.textContent = a.name;

    const siteLine = document.createElement("div");
    siteLine.className = "data-card-line";
    const siteLabel = document.createElement("span");
    siteLabel.className = "data-card-label";
    siteLabel.textContent = "Website";
    siteLine.appendChild(siteLabel);
    if (a.website) {
      const link = document.createElement("a");
      link.href = a.website;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = a.website.replace(/^https?:\/\/(www\.)?/, "").split("/")[0];
      link.style.cssText = "color:var(--primary);text-decoration:none";
      siteLine.appendChild(link);
    } else {
      siteLine.appendChild(document.createTextNode("—"));
    }

    const emailLine = document.createElement("div");
    emailLine.className = "data-card-line";
    const emailLabel = document.createElement("span");
    emailLabel.className = "data-card-label";
    emailLabel.textContent = "Email";
    emailLine.append(emailLabel, document.createTextNode(a.email || "—"));

    const badges = document.createElement("div");
    badges.className = "data-card-badges";
    (a.stack || []).forEach((s) => {
      const stackBadge = document.createElement("span");
      stackBadge.className = "badge badge-blue";
      stackBadge.textContent = s;
      badges.appendChild(stackBadge);
    });
    const sourceBadge = document.createElement("span");
    sourceBadge.className = "badge badge-gray";
    sourceBadge.textContent = a.source || "scraper";
    badges.appendChild(sourceBadge);

    const actions = document.createElement("div");
    actions.className = "data-card-actions";
    const delBtn = document.createElement("button");
    delBtn.className = "btn btn-ghost btn-sm";
    delBtn.textContent = "Remove";
    delBtn.addEventListener("click", async () => {
      delBtn.disabled = true;
      await API.del(`/api/scraper/agencies/${a.id}`);
      loadAgencies(_agenciesPage);
    });
    actions.appendChild(delBtn);

    card.append(title, siteLine, emailLine, badges, actions);
    list.appendChild(card);
  });
  container.append(list, _agencyPager(total, agencies.length, pages));
}

window.init_agencies = function () {
  buildAgenciesUI();
};
