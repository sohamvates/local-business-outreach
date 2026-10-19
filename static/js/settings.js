/* ════════════════════════════════════════════════════════
   settings.js — Settings page logic
   ════════════════════════════════════════════════════════ */

// ─── Build the settings form using safe DOM methods ───────
function buildSettingsUI() {
  const container = document.getElementById("settings-content");
  const places = el("div", { className: "card", id: "settings-places" });
  places.textContent = "Loading places…";
  container.replaceChildren(
    places,
    makeSmtpCard("gmail", "Gmail SMTP", "smtp.gmail.com", "587", "Use an App Password, not your main Google password."),
    makeSmtpCard("custom", "Custom SMTP", "", "587", "Optional second mailbox. Leave it empty if you only send through Gmail."),
    makeApiCard("claude", "Claude API Key", "CLAUDE_API_KEY", "sk-ant-…", "Required for AI-generated outreach emails.", "test/claude"),
    makeApiCard("maps", "Google Maps API Key", "GOOGLE_MAPS_API_KEY", "AIza…", "Required to search businesses with the Places API.", "test/google-maps"),
    makeSheetsCard(),
    makeScraperCard(),
    makeSaveBar(),
  );
  fillPlacesCard(places);
}

async function fillPlacesCard(card) {
  card.replaceChildren();
  let status = { has_profile: false, cities: [] };
  try {
    status = await API.get("/api/setup/status");
  } catch (_) {}
  const title = el("div", { className: "card-title" });
  title.textContent = "Country, state, and cities";
  const sub = el("div", { className: "card-subtitle" });
  if (!status.has_profile) {
    sub.textContent = "Country, state, and cities are chosen in the first-run setup. This computer already had a mailbox, so its current search places stay as they are.";
    card.append(title, sub);
    return;
  }
  sub.textContent = "Choose one country, then a state, then each city. A choice stays marked. Save asks Google to confirm the cities again.";
  const known = status.country_code ? countryByCode(status.country_code) : null;
  const initialCities = (status.cities || []).filter((city) => city.name).map((city) => ({
    name: city.name,
    state: city.state || "",
  }));
  const picker = buildPlacePicker({
    country: known || (status.country ? { name: status.country, code: status.country_code || "" } : null),
    cities: initialCities,
  }, (picks) => {
    card._picks = picks;
  });
  card._picks = {
    country: known || (status.country ? { name: status.country, code: status.country_code || "" } : null),
    cities: initialCities,
  };
  const save = el("button", { className: "btn btn-primary btn-sm" });
  save.type = "button";
  save.textContent = "Save places";
  save.addEventListener("click", async () => {
    const picks = card._picks || {};
    if (!picks.country || !(picks.cities || []).length) {
      toast("Choose a country and at least one city.", "error");
      return;
    }
    save.disabled = true;
    try {
      const result = await API.post("/api/setup/places", {
        country: picks.country.name,
        choices: picks.cities.map((city) => ({ city: city.name, state: city.state || "" })),
      });
      toast(result.message || (result.ok ? "Places saved." : "Could not save places."), result.ok ? "success" : "error");
    } catch (error) {
      toast(error.message || "Could not save places.", "error");
    } finally {
      save.disabled = false;
    }
  });
  card.append(title, sub, picker, save);
}

// ─── Card builders (all safe DOM) ────────────────────────
function makeSmtpCard(prefix, title, defaultHost, defaultPort, hint) {
  const card = el("div", { className: "card" });

  const cardTitle = el("div", { className: "card-title" });
  cardTitle.append(prefix === "gmail" ? "✉️" : "📧", " ", title);

  const cardSub = el("div", { className: "card-subtitle" });
  cardSub.textContent = hint;

  const grid = el("div", { className: "form-grid" });

  grid.append(
    formGroup(`${prefix}_host`, "SMTP Host", "text", defaultHost, `${prefix.toUpperCase()}_SMTP_HOST`),
    formGroup(`${prefix}_port`, "Port", "text", defaultPort, `${prefix.toUpperCase()}_SMTP_PORT`),
    formGroup(`${prefix}_user`, "Username / Email", "email", "", `${prefix.toUpperCase()}_SMTP_USER`),
    formGroup(`${prefix}_password`, "Password / App Password", "password", "", `${prefix.toUpperCase()}_SMTP_PASSWORD`),
    formGroup(`${prefix}_from_name`, "From Display Name", "text",
      "Your name",
      `${prefix.toUpperCase()}_FROM_NAME`),
  );

  const testRow = el("div", { className: "test-row" });
  const testBtn = el("button", { className: "btn btn-ghost btn-sm" });
  testBtn.textContent = "🔌 Test connection";
  testBtn.addEventListener("click", () => testSmtp(prefix, testBtn));

  const testResult = el("span", { className: "test-result", id: `test-result-${prefix}` });

  testRow.append(testBtn, testResult);
  card.append(cardTitle, cardSub, grid, testRow);
  return card;
}

function makeApiCard(id, title, envKey, placeholder, hint, testEndpoint) {
  const card = el("div", { className: "card" });

  const cardTitle = el("div", { className: "card-title" });
  cardTitle.textContent = title;

  const cardSub = el("div", { className: "card-subtitle" });
  cardSub.textContent = hint;

  const group = formGroup(id + "_key", title, "password", placeholder, envKey);
  group.style.maxWidth = "520px";

  const testRow = el("div", { className: "test-row" });
  const testBtn = el("button", { className: "btn btn-ghost btn-sm" });
  testBtn.textContent = "🔌 Test key";
  testBtn.addEventListener("click", () => testApiKey(testEndpoint, testBtn, id + "_key_test"));

  const testResult = el("span", { className: "test-result", id: `${id}_key_test` });
  testRow.append(testBtn, testResult);

  card.append(cardTitle, cardSub, group, testRow);
  return card;
}

function makeSheetsCard() {
  const card = el("div", { className: "card" });

  const cardTitle = el("div", { className: "card-title" });
  cardTitle.textContent = "📊 Google Sheets ID";

  const cardSub = el("div", { className: "card-subtitle" });
  cardSub.textContent =
    "The ID from your Google Sheet URL: docs.google.com/spreadsheets/d/[THIS_ID]/edit";

  const group = formGroup("sheets_id", "Spreadsheet ID", "text", "", "GOOGLE_SHEETS_ID");
  group.style.maxWidth = "520px";

  card.append(cardTitle, cardSub, group);
  return card;
}

function makeScraperCard() {
  const card = el("div", { className: "card" });

  const cardTitle = el("div", { className: "card-title" });
  cardTitle.textContent = "🔍 Scraper Limits";

  const cardSub = el("div", { className: "card-subtitle" });
  cardSub.textContent = "Controls how many results are saved per Google Maps search job.";

  const group = formGroup("clients_max", "Max clients per search", "number", "20", "CLIENTS_MAX_RESULTS");
  group.style.maxWidth = "200px";

  const hint = el("div");
  hint.style.cssText = "font-size:12px;color:var(--text-muted);margin-top:4px";
  hint.textContent = "Each place fetched calls the Places Details API — keep low to stay within your quota.";
  group.appendChild(hint);

  card.append(cardTitle, cardSub, group);
  return card;
}

function makeSaveBar() {
  const card = el("div", { className: "card" });
  card.style.cssText = "background:var(--primary-light);border-color:var(--primary)";

  const row = el("div", { className: "action-row" });
  row.style.cssText = "margin:0;padding:0;border:none";

  const saveBtn = el("button", { className: "btn btn-primary", id: "save-btn" });
  saveBtn.textContent = "💾 Save all settings";
  saveBtn.addEventListener("click", saveSettings);

  const status = el("span", { id: "save-status", style: "font-size:13px" });

  row.append(saveBtn, status);
  card.appendChild(row);
  return card;
}

// ─── Populate form from API ───────────────────────────────
async function loadSettings() {
  try {
    const data = await API.get("/api/settings");
    Object.entries(data).forEach(([key, value]) => {
      const input = document.querySelector(`[data-env="${key}"]`);
      if (input) input.value = value;
    });
  } catch (e) {
    toast("Could not load settings: " + e.message, "error");
  }
}

// ─── Save settings ────────────────────────────────────────
async function saveSettings() {
  const btn = document.getElementById("save-btn");
  const status = document.getElementById("save-status");
  if (btn) btn.disabled = true;
  if (btn) btn.textContent = "Saving…";
  if (status) status.textContent = "";

  const payload = {};
  document.querySelectorAll("[data-env]").forEach((input) => {
    payload[input.dataset.env] = input.value;
  });

  try {
    const res = await API.post("/api/settings", payload);
    if (res.ok) {
      if (status) status.style.color = "var(--success)";
      if (status) status.textContent = "✓ Settings saved successfully";
      toast("Settings saved.", "success");
    } else {
      if (status) status.style.color = "var(--error)";
      if (status) status.textContent = "✕ " + (res.message || "Save failed");
    }
  } catch (e) {
    if (status) status.style.color = "var(--error)";
    if (status) status.textContent = "✕ " + e.message;
    toast("Save failed: " + e.message, "error");
  } finally {
    if (btn) btn.disabled = false;
    if (btn) btn.textContent = "💾 Save all settings";
  }
}

// ─── Connection testers ───────────────────────────────────
async function testSmtp(prefix, btn) {
  const resultEl = document.getElementById(`test-result-${prefix}`);
  btn.disabled = true;
  btn.textContent = "Testing…";
  resultEl.textContent = "";
  resultEl.className = "test-result";

  // Save current form values first so the server reads fresh values
  await saveSettings();

  try {
    const res = await API.post(`/api/settings/test/${prefix}-smtp`);
    resultEl.classList.add(res.ok ? "ok" : "err");
    resultEl.textContent = (res.ok ? "✓ " : "✕ ") + res.message;
  } catch (e) {
    resultEl.classList.add("err");
    resultEl.textContent = "✕ " + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "🔌 Test connection";
  }
}

async function testApiKey(endpoint, btn, resultId) {
  const resultEl = document.getElementById(resultId);
  btn.disabled = true;
  btn.textContent = "Testing…";
  resultEl.textContent = "";
  resultEl.className = "test-result";

  await saveSettings();

  try {
    const res = await API.post(`/api/settings/${endpoint}`);
    resultEl.classList.add(res.ok ? "ok" : "err");
    resultEl.textContent = (res.ok ? "✓ " : "✕ ") + res.message;
  } catch (e) {
    resultEl.classList.add("err");
    resultEl.textContent = "✕ " + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "🔌 Test key";
  }
}

// ─── DOM helpers ─────────────────────────────────────────
function el(tag, props = {}) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  return node;
}

function formGroup(id, labelText, inputType, placeholder, envKey) {
  const group = el("div", { className: "form-group" });

  const lbl = el("label");
  lbl.setAttribute("for", id);
  lbl.textContent = labelText;

  const input = el("input");
  input.type = inputType;
  input.id = id;
  input.placeholder = placeholder;
  input.dataset.env = envKey;
  input.autocomplete = inputType === "password" ? "off" : "on";

  group.append(lbl, input);
  return group;
}

// ─── Page init hook ───────────────────────────────────────
window.init_settings = async function () {
  buildSettingsUI();
  await loadSettings();
};
