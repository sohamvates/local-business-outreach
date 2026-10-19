/* First-run workspace assistant. Secrets go to .env. The profile stores the rest.
   Places are confirmed with Google before the person can leave that step. */

const SETUP_NICHES = [
  "Law Firms", "Dental Clinics", "Medical Centres", "Real Estate",
  "Accountants", "Restaurants", "Gyms", "Contractors",
];

const SETUP_STEPS = [
  "You",
  "Maps",
  "Places",
  "Audience",
  "Claude",
  "Mailbox",
  "Review",
];

const AUDIENCE_LABELS = {
  clients: "Local businesses",
  agencies: "Agencies",
  both: "Both",
};

const setupState = {
  step: 0,
  started: false,
  name: "",
  company: "",
  role: "",
  phone: "",
  website: "",
  signature: "",
  country: "",
  countryPick: null,
  statePick: null,
  cityPicks: [],
  cities: "",
  confirmed: null,
  audience: "clients",
  niches: ["Law Firms"],
  customNiche: "",
  extraNiches: [],
  claudeKey: "",
  mapsKey: "",
  mapsReady: false,
  claudeReady: false,
  smtpHost: "smtp.gmail.com",
  smtpPort: "587",
  smtpUser: "",
  smtpPassword: "",
  fromName: "",
  dailyLimit: "25",
  mailboxReady: false,
};

function buildSetupUI() {
  const container = document.getElementById("setup-content");
  if (!container) return;
  container.replaceChildren(renderSetupStep());
  if (!setupState.started) {
    setupState.started = true;
    API.post("/api/setup/progress", {}).catch(() => {});
  }
}

function renderSetupStep() {
  const shell = document.createElement("div");
  shell.className = "setup-shell";

  const rail = document.createElement("ol");
  rail.className = "setup-rail";
  SETUP_STEPS.forEach((label, index) => {
    const item = document.createElement("li");
    if (index === setupState.step) item.className = "current";
    else if (index < setupState.step) item.className = "done";
    item.textContent = label;
    rail.appendChild(item);
  });

  const progress = document.createElement("div");
  progress.className = "setup-progress";
  progress.textContent = "Step " + (setupState.step + 1) + " of " + SETUP_STEPS.length + " — " + SETUP_STEPS[setupState.step];

  const card = document.createElement("div");
  card.className = "card";
  card.append(rail, progress, setupStepBody(setupState.step));
  shell.appendChild(card);
  return shell;
}

function setupStepBody(step) {
  if (step === 0) return setupIdentityStep();
  if (step === 1) return setupMapsStep();
  if (step === 2) return setupPlacesStep();
  if (step === 3) return setupAudienceStep();
  if (step === 4) return setupClaudeStep();
  if (step === 5) return setupSendingStep();
  return setupReviewStep();
}

function setupField(id, label, type, value, onInput) {
  const group = document.createElement("div");
  group.className = "form-group";
  const lab = document.createElement("label");
  lab.setAttribute("for", id);
  lab.textContent = label;
  const input = document.createElement("input");
  input.id = id;
  input.type = type;
  input.value = value || "";
  if (type === "password") input.autocomplete = "new-password";
  input.addEventListener("input", () => onInput(input.value));
  group.append(lab, input);
  return group;
}

function setupErrorSlot() {
  const error = document.createElement("div");
  error.id = "setup-error";
  error.className = "alert alert-error";
  error.style.display = "none";
  return error;
}

function setupActions(showBack, nextLabel, onNext, nextDisabled) {
  const block = document.createElement("div");
  const row = document.createElement("div");
  row.className = "setup-actions";
  if (showBack) {
    const back = document.createElement("button");
    back.type = "button";
    back.className = "btn btn-ghost";
    back.textContent = "Back";
    back.addEventListener("click", () => {
      setupState.step -= 1;
      buildSetupUI();
    });
    row.appendChild(back);
  }
  const next = document.createElement("button");
  next.type = "button";
  next.id = "setup-next";
  next.className = "btn btn-primary";
  next.textContent = nextLabel;
  next.disabled = !!nextDisabled;
  next.addEventListener("click", onNext);
  row.appendChild(next);
  block.append(setupErrorSlot(), row);
  return block;
}

function readInput(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : "";
}

function showSetupError(message) {
  const error = document.getElementById("setup-error");
  if (!error) return;
  error.style.display = "";
  error.textContent = message;
}

function chosenChoices() {
  return setupState.cityPicks.map((item) => ({ city: item.name, state: item.state || "" }));
}

function placesFingerprint() {
  const country = setupState.countryPick ? setupState.countryPick.code : "";
  const cities = setupState.cityPicks.map((item) => item.name + "@" + (item.state || "")).join("|");
  return country + "|" + cities.toLowerCase();
}

function placesMatch() {
  return !!(setupState.confirmed && setupState.confirmed.fingerprint === placesFingerprint());
}

function signaturePreview() {
  let signature = setupState.signature.trim();
  if (!signature) {
    signature = [setupState.name, setupState.role, setupState.company, setupState.phone, setupState.website]
      .filter(Boolean)
      .join("\n");
  }
  const email = setupState.smtpUser.trim();
  if (email && !signature.toLowerCase().includes(email.toLowerCase())) {
    signature = signature.replace(/\s+$/, "") + "\n" + email;
  }
  return signature;
}

function chosenNiches() {
  return setupState.niches.concat(setupState.extraNiches);
}

function addExtraNiche() {
  const name = readInput("setup-custom-niche");
  if (!name) {
    showSetupError("Type the niche, then press Add niche.");
    return;
  }
  const already = chosenNiches().some((item) => item.toLowerCase() === name.toLowerCase());
  if (!already) setupState.extraNiches.push(name);
  setupState.customNiche = "";
  buildSetupUI();
}

function setupIdentityStep() {
  const wrap = document.createElement("div");
  wrap.className = "setup-fields";
  const intro = document.createElement("p");
  intro.className = "setup-lead";
  intro.textContent = "This is the person the emails come from. Only the name is required. Leave the signature empty and it is built from these fields. The sending email is added on the mailbox step.";
  const grid = document.createElement("div");
  grid.className = "form-grid";
  grid.append(
    setupField("setup-name", "Your name", "text", setupState.name, (value) => { setupState.name = value; }),
    setupField("setup-company", "Company", "text", setupState.company, (value) => { setupState.company = value; }),
    setupField("setup-role", "Role", "text", setupState.role, (value) => { setupState.role = value; }),
    setupField("setup-phone", "Phone", "text", setupState.phone, (value) => { setupState.phone = value; }),
    setupField("setup-website", "Website", "text", setupState.website, (value) => { setupState.website = value; }),
  );
  const sig = document.createElement("div");
  sig.className = "form-group";
  const sigLabel = document.createElement("label");
  sigLabel.setAttribute("for", "setup-signature");
  sigLabel.textContent = "Signature";
  const area = document.createElement("textarea");
  area.id = "setup-signature";
  area.rows = 5;
  area.value = setupState.signature;
  area.addEventListener("input", () => { setupState.signature = area.value; });
  sig.append(sigLabel, area);
  wrap.append(
    intro,
    grid,
    sig,
    setupActions(false, "Continue", () => {
      setupState.name = readInput("setup-name");
      setupState.company = readInput("setup-company");
      setupState.role = readInput("setup-role");
      setupState.phone = readInput("setup-phone");
      setupState.website = readInput("setup-website");
      setupState.signature = document.getElementById("setup-signature").value.trim();
      if (!setupState.name) {
        showSetupError("Add your name to continue.");
        return;
      }
      setupState.step = 1;
      buildSetupUI();
    }),
  );
  return wrap;
}

function setupMapsStep() {
  const wrap = document.createElement("div");
  const intro = document.createElement("p");
  intro.className = "setup-lead";
  intro.textContent = "Paste the key from Google Cloud. Places API has to be enabled on that key. The next step uses it to list states and cities. A rejected key stays here.";
  wrap.append(
    intro,
    setupField("setup-maps", "Google Maps API key", "password", setupState.mapsKey, (value) => {
      setupState.mapsKey = value;
      setupState.mapsReady = false;
    }),
    setupActions(true, "Test key and continue", async () => {
      setupState.mapsKey = readInput("setup-maps");
      if (!setupState.mapsKey) {
        showSetupError("Add the Google Maps API key.");
        return;
      }
      const button = document.getElementById("setup-next");
      if (button) button.disabled = true;
      try {
        await API.post("/api/setup/progress", {});
        await API.post("/api/settings", { GOOGLE_MAPS_API_KEY: setupState.mapsKey });
        const maps = await API.post("/api/settings/test/google-maps");
        if (!maps.ok) {
          setupState.mapsReady = false;
          showSetupError(maps.message || "Google Maps key was rejected.");
          return;
        }
        setupState.mapsReady = true;
        setupState.step = 2;
        buildSetupUI();
      } catch (error) {
        showSetupError(error.message || "Could not test the Maps key.");
      } finally {
        if (button && setupState.step === 1) button.disabled = false;
      }
    }),
  );
  return wrap;
}

function setupPlacesStep() {
  const wrap = document.createElement("div");
  const intro = document.createElement("p");
  intro.className = "setup-lead";
  intro.textContent = "Type and choose one country. Then choose one state. Then choose each city. A choice stays marked. Text you type but do not choose is ignored, so a wrong name is never guessed.";
  const picker = buildPlacePicker({
    country: setupState.countryPick,
    state: setupState.statePick,
    cities: setupState.cityPicks,
  }, (picks) => {
    setupState.countryPick = picks.country;
    setupState.statePick = picks.state;
    setupState.cityPicks = picks.cities;
    setupState.country = picks.country ? picks.country.name : "";
    invalidatePlaces();
  });

  const confirmed = document.createElement("ul");
  confirmed.id = "setup-confirmed";
  confirmed.className = "setup-confirmed";
  if (placesMatch()) {
    setupState.confirmed.cities.forEach((city) => {
      const item = document.createElement("li");
      item.textContent = city.formatted_address;
      confirmed.appendChild(item);
    });
  } else {
    confirmed.style.display = "none";
  }

  const check = document.createElement("button");
  check.type = "button";
  check.id = "setup-check-places";
  check.className = "btn btn-outline";
  check.textContent = "Confirm with Google";
  check.addEventListener("click", checkPlaces);

  wrap.append(
    intro,
    picker,
    check,
    confirmed,
    setupActions(true, "Continue", () => {
      if (!placesMatch()) {
        showSetupError("Choose the country, state, and at least one city, then confirm with Google.");
        return;
      }
      setupState.step = 3;
      buildSetupUI();
    }, !placesMatch()),
  );
  return wrap;
}

function buildPlacePicker(initial, onChange) {
  const picks = {
    country: initial.country || null,
    state: initial.state || null,
    cities: (initial.cities || []).slice(),
    stateSkipped: !!(initial.state && initial.state.skipped),
  };
  let suggestTimer = null;
  let suggestSeq = 0;
  const root = document.createElement("div");
  root.className = "setup-places";

  function emit() {
    onChange({
      country: picks.country,
      state: picks.state,
      cities: picks.cities.slice(),
    });
  }

  function hint(text) {
    const note = document.createElement("p");
    note.className = "setup-hint";
    note.textContent = text;
    return note;
  }

  function pickedRow(label, onChangeClick) {
    const row = document.createElement("div");
    row.className = "setup-picked";
    const name = document.createElement("strong");
    name.textContent = label;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-ghost btn-sm";
    button.textContent = "Change";
    button.addEventListener("click", onChangeClick);
    row.append(name, button);
    return row;
  }

  function suggestList(items, onPick, emptyText) {
    const list = document.createElement("ul");
    list.className = "setup-suggest-list";
    if (!items.length) {
      const item = document.createElement("li");
      item.className = "setup-suggest-empty";
      item.textContent = emptyText;
      list.appendChild(item);
      return list;
    }
    items.forEach((item) => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = item.description && item.description !== item.name
        ? item.name + " — " + item.description
        : item.name;
      button.addEventListener("mousedown", (event) => {
        event.preventDefault();
        onPick(item);
      });
      li.appendChild(button);
      list.appendChild(li);
    });
    return list;
  }

  function countryBlock() {
    const group = document.createElement("div");
    group.className = "form-group";
    const label = document.createElement("label");
    label.textContent = "Country";
    group.append(label, hint("One country. Start typing and choose it. It stays selected."));
    if (picks.country) {
      group.appendChild(pickedRow(picks.country.name, () => {
        picks.country = null;
        picks.state = null;
        picks.cities = [];
        picks.stateSkipped = false;
        emit();
        paint();
      }));
      return group;
    }
    const box = document.createElement("div");
    box.className = "setup-suggest";
    const input = document.createElement("input");
    input.id = "setup-country";
    input.type = "text";
    input.placeholder = "Type a country, for example Brazil";
    input.autocomplete = "off";
    input.addEventListener("input", () => {
      const matches = filterCountries(input.value).map((item) => ({
        name: item.name,
        code: item.code,
        description: item.alias && foldPlaceText(item.alias) !== foldPlaceText(item.name) ? item.alias : "",
      }));
      draw(matches, "No country matches. Keep typing the country name.");
    });
    box.appendChild(input);
    group.appendChild(box);

    function draw(matches, emptyText) {
      const old = box.querySelector(".setup-suggest-list");
      if (old) old.remove();
      if (!input.value.trim()) return;
      box.appendChild(suggestList(matches, (item) => {
        picks.country = { name: item.name, code: item.code };
        picks.state = null;
        picks.cities = [];
        picks.stateSkipped = false;
        emit();
        paint();
      }, emptyText));
    }
    return group;
  }

  function stateBlock() {
    const group = document.createElement("div");
    group.className = "form-group";
    const label = document.createElement("label");
    label.textContent = "State";
    group.append(label, hint("Choose the state, province, or region inside the country. The city list uses this choice."));
    if (!picks.country) {
      group.appendChild(hint("Choose the country first."));
      return group;
    }
    if (picks.state && !picks.state.skipped) {
      group.appendChild(pickedRow(picks.state.name, () => {
        picks.state = null;
        picks.stateSkipped = false;
        emit();
        paint();
      }));
      return group;
    }
    if (picks.stateSkipped) {
      group.appendChild(pickedRow("No state for this country", () => {
        picks.stateSkipped = false;
        picks.state = null;
        emit();
        paint();
      }));
      return group;
    }
    const box = document.createElement("div");
    box.className = "setup-suggest";
    const input = document.createElement("input");
    input.id = "setup-state";
    input.type = "text";
    input.placeholder = "Type a state in " + picks.country.name;
    input.autocomplete = "off";
    input.addEventListener("input", () => {
      const local = filterStates(picks.country.code, input.value);
      if (local) {
        const old = box.querySelector(".setup-suggest-list");
        if (old) old.remove();
        if (input.value.trim().length < 2) return;
        box.appendChild(suggestList(local, (item) => {
          picks.state = { name: item.name };
          picks.stateSkipped = false;
          emit();
          paint();
        }, "No state matches. Check the spelling."));
        return;
      }
      queueRemote("state", input.value, box, input, (item) => {
        picks.state = { name: item.name };
        picks.stateSkipped = false;
        emit();
        paint();
      }, "No state matches. If this country has no states, use the button below.");
    });
    const skip = document.createElement("button");
    skip.type = "button";
    skip.className = "btn btn-ghost btn-sm";
    skip.textContent = "This country has no states";
    skip.addEventListener("click", () => {
      picks.state = { name: "", skipped: true };
      picks.stateSkipped = true;
      emit();
      paint();
    });
    box.appendChild(input);
    group.append(box, skip);
    return group;
  }

  function cityBlock() {
    const group = document.createElement("div");
    group.className = "form-group";
    const label = document.createElement("label");
    label.textContent = "Cities";
    group.append(label, hint("Choose a city. It stays marked. You can add more than one. Remove a city if it is wrong."));
    const ready = picks.country && (picks.state || picks.stateSkipped);
    if (!ready) {
      group.appendChild(hint("Choose the state first."));
      return group;
    }
    const box = document.createElement("div");
    box.className = "setup-suggest";
    const input = document.createElement("input");
    input.id = "setup-city";
    input.type = "text";
    input.placeholder = picks.state ? "Type a city in " + picks.state.name : "Type a city in " + picks.country.name;
    input.autocomplete = "off";
    input.addEventListener("input", () => queueRemote("city", input.value, box, input, (item) => {
      const stateName = picks.state ? picks.state.name : "";
      const exists = picks.cities.some((city) => city.name === item.name && (city.state || "") === stateName);
      if (!exists) picks.cities.push({ name: item.name, state: stateName });
      emit();
      paint();
    }, "No city matches in this state."));
    box.appendChild(input);
    const chips = document.createElement("div");
    chips.className = "setup-city-chips";
    picks.cities.forEach((city, index) => {
      const chip = document.createElement("span");
      chip.className = "setup-city-chip";
      chip.textContent = city.state ? city.name + ", " + city.state : city.name;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Remove";
      remove.addEventListener("click", () => {
        picks.cities.splice(index, 1);
        emit();
        paint();
      });
      chip.appendChild(remove);
      chips.appendChild(chip);
    });
    group.append(box, chips);
    return group;
  }

  function queueRemote(kind, query, box, input, onPick, emptyText) {
    const old = box.querySelector(".setup-suggest-list");
    if (old) old.remove();
    clearTimeout(suggestTimer);
    const seq = ++suggestSeq;
    if (query.trim().length < 2) return;
    const pending = document.createElement("ul");
    pending.className = "setup-suggest-list";
    const item = document.createElement("li");
    item.className = "setup-suggest-empty";
    item.textContent = kind === "state" ? "Looking up states…" : "Looking up cities…";
    pending.appendChild(item);
    box.appendChild(pending);
    suggestTimer = setTimeout(async () => {
      try {
        const data = await API.post("/api/setup/suggest-places", {
          kind: kind,
          query: query.trim(),
          country_code: picks.country.code,
          state_name: picks.state ? picks.state.name : "",
        });
        if (seq !== suggestSeq || document.activeElement !== input) return;
        const current = box.querySelector(".setup-suggest-list");
        if (current) current.remove();
        if (!data.ok) {
          box.appendChild(suggestList([], () => {}, data.message || "Google could not suggest places."));
          return;
        }
        box.appendChild(suggestList(data.items || [], onPick, emptyText));
      } catch (error) {
        if (seq !== suggestSeq) return;
        const current = box.querySelector(".setup-suggest-list");
        if (current) current.remove();
        box.appendChild(suggestList([], () => {}, error.message || "Could not look up places."));
      }
    }, 300);
  }

  function paint() {
    root.replaceChildren(countryBlock(), stateBlock(), cityBlock());
  }

  paint();
  return root;
}

window.buildPlacePicker = buildPlacePicker;

function invalidatePlaces() {
  if (!setupState.confirmed) return;
  if (setupState.confirmed.fingerprint === placesFingerprint()) return;
  setupState.confirmed = null;
  const list = document.getElementById("setup-confirmed");
  if (list) {
    list.replaceChildren();
    list.style.display = "none";
  }
  const next = document.getElementById("setup-next");
  if (next) next.disabled = true;
}

async function checkPlaces() {
  if (!setupState.mapsReady) {
    showSetupError("Test the Google Maps key before checking places.");
    return;
  }
  if (!setupState.countryPick) {
    showSetupError("Choose a country from the list.");
    return;
  }
  if (!setupState.statePick) {
    showSetupError("Choose a state from the list.");
    return;
  }
  if (!setupState.cityPicks.length) {
    showSetupError("Choose at least one city from the list.");
    return;
  }
  const button = document.getElementById("setup-check-places");
  if (button) {
    button.disabled = true;
    button.textContent = "Confirming…";
  }
  try {
    const found = await API.post("/api/setup/resolve-places", {
      country: setupState.countryPick.name,
      choices: chosenChoices(),
    });
    if (!found.ok) {
      setupState.confirmed = null;
      showSetupError(found.message || "Google could not confirm these places.");
      const list = document.getElementById("setup-confirmed");
      if (list) list.style.display = "none";
      const next = document.getElementById("setup-next");
      if (next) next.disabled = true;
      return;
    }
    setupState.confirmed = {
      fingerprint: placesFingerprint(),
      country_name: found.country_name,
      country_code: found.country_code,
      cities: found.cities,
    };
    buildSetupUI();
  } catch (error) {
    showSetupError(error.message || "Could not check places.");
  } finally {
    if (button && !setupState.confirmed) {
      button.disabled = false;
      button.textContent = "Confirm with Google";
    }
  }
}

function setupAudienceStep() {
  const wrap = document.createElement("div");
  const intro = document.createElement("p");
  intro.className = "setup-lead";
  intro.textContent = "Local businesses are searched on the map in the cities you marked. Agencies are digital agencies in those same places. Both runs the two searches. Pick at least one kind of business.";
  const audience = document.createElement("div");
  audience.className = "setup-choice";
  const audienceLabel = document.createElement("div");
  audienceLabel.className = "setup-choice-title";
  audienceLabel.textContent = "Who do you want to contact?";
  audience.appendChild(audienceLabel);
  [
    ["clients", "Local businesses"],
    ["agencies", "Agencies"],
    ["both", "Both"],
  ].forEach(([value, label]) => {
    const lab = document.createElement("label");
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "setup-audience";
    radio.value = value;
    radio.checked = setupState.audience === value;
    radio.addEventListener("change", () => { setupState.audience = value; });
    lab.append(radio, document.createTextNode(label));
    audience.appendChild(lab);
  });

  const niches = document.createElement("div");
  niches.className = "clients-chip-grid";
  SETUP_NICHES.forEach((niche) => {
    const lab = document.createElement("label");
    lab.className = "clients-chip";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = niche;
    box.className = "setup-niche";
    box.checked = setupState.niches.includes(niche);
    box.addEventListener("change", () => {
      setupState.niches = [...document.querySelectorAll(".setup-niche:checked")].map((item) => item.value);
    });
    lab.append(box, document.createTextNode(niche));
    niches.appendChild(lab);
  });
  setupState.extraNiches.forEach((niche, index) => {
    const chip = document.createElement("span");
    chip.className = "setup-city-chip";
    chip.textContent = niche;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => {
      setupState.extraNiches.splice(index, 1);
      buildSetupUI();
    });
    chip.appendChild(remove);
    niches.appendChild(chip);
  });

  const custom = document.createElement("div");
  custom.className = "form-group";
  const customLabel = document.createElement("label");
  customLabel.setAttribute("for", "setup-custom-niche");
  customLabel.textContent = "Another niche";
  const customHint = document.createElement("p");
  customHint.className = "setup-hint";
  customHint.textContent = "Type a niche and press Add niche. It stays marked on this step. Continue does not add the text for you.";
  const customRow = document.createElement("div");
  customRow.className = "setup-city-add";
  const customInput = document.createElement("input");
  customInput.id = "setup-custom-niche";
  customInput.type = "text";
  customInput.placeholder = "Type a niche";
  customInput.value = setupState.customNiche;
  customInput.addEventListener("input", () => { setupState.customNiche = customInput.value; });
  customInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    addExtraNiche();
  });
  const add = document.createElement("button");
  add.type = "button";
  add.className = "btn btn-outline";
  add.textContent = "Add niche";
  add.addEventListener("click", addExtraNiche);
  customRow.append(customInput, add);
  custom.append(customLabel, customHint, customRow);

  wrap.append(
    intro,
    audience,
    niches,
    custom,
    setupActions(true, "Continue", () => {
      const selected = document.querySelector("input[name='setup-audience']:checked");
      setupState.audience = selected ? selected.value : "";
      setupState.niches = [...document.querySelectorAll(".setup-niche:checked")].map((box) => box.value);
      setupState.customNiche = readInput("setup-custom-niche");
      if (setupState.customNiche) {
        showSetupError("Press Add niche so “" + setupState.customNiche + "” stays marked. Continue does not add it.");
        return;
      }
      if (!setupState.audience || !chosenNiches().length) {
        showSetupError("Choose who you contact and at least one niche.");
        return;
      }
      setupState.step = 4;
      buildSetupUI();
    }),
  );
  return wrap;
}

function setupSuccess(message) {
  const note = document.createElement("div");
  note.className = "alert alert-success";
  note.textContent = message;
  return note;
}

function setupClaudeStep() {
  const wrap = document.createElement("div");
  const intro = document.createElement("p");
  intro.className = "setup-lead";
  intro.textContent = "Claude only writes the drafts. This is not the email account. The mailbox is the next step. A rejected key stays here.";
  const hint = document.createElement("p");
  hint.className = "setup-hint";
  hint.textContent = "Paste the key from console.anthropic.com. Test key checks it with Claude before you continue.";
  wrap.append(
    intro,
    setupField("setup-claude", "Claude API key", "password", setupState.claudeKey, (value) => {
      setupState.claudeKey = value;
      setupState.claudeReady = false;
    }),
    hint,
    setupActions(true, "Test key and continue", async () => {
      setupState.claudeKey = readInput("setup-claude");
      if (!setupState.claudeKey) {
        showSetupError("Add the Claude API key.");
        return;
      }
      const button = document.getElementById("setup-next");
      if (button) button.disabled = true;
      try {
        await API.post("/api/setup/progress", {});
        await API.post("/api/settings", { CLAUDE_API_KEY: setupState.claudeKey });
        const claude = await API.post("/api/settings/test/claude");
        if (!claude.ok) {
          setupState.claudeReady = false;
          showSetupError(claude.message || "Claude key was rejected.");
          return;
        }
        setupState.claudeReady = true;
        setupState.step = 5;
        buildSetupUI();
      } catch (error) {
        showSetupError(error.message || "Could not test the Claude key.");
      } finally {
        if (button && setupState.step === 4) button.disabled = false;
      }
    }),
  );
  return wrap;
}

function setupSendingStep() {
  const wrap = document.createElement("div");
  const intro = document.createElement("p");
  intro.className = "setup-lead";
  intro.textContent = "This is the address people reply to. For Gmail, use an app password, not the normal Google password. The daily limit is how many emails this computer may send in a day, from 1 to 200.";
  const grid = document.createElement("div");
  grid.className = "form-grid";
  grid.append(
    setupField("setup-smtp-host", "SMTP host", "text", setupState.smtpHost, (value) => {
      setupState.smtpHost = value;
      setupState.mailboxReady = false;
    }),
    setupField("setup-smtp-port", "Port", "text", setupState.smtpPort, (value) => {
      setupState.smtpPort = value;
    }),
    setupField("setup-smtp-user", "Email", "email", setupState.smtpUser, (value) => {
      setupState.smtpUser = value;
      setupState.mailboxReady = false;
    }),
    setupField("setup-smtp-password", "Password", "password", setupState.smtpPassword, (value) => {
      setupState.smtpPassword = value;
      setupState.mailboxReady = false;
    }),
    setupField("setup-from-name", "From name", "text", setupState.fromName || setupState.company || setupState.name, (value) => {
      setupState.fromName = value;
    }),
    setupField("setup-daily", "Daily send limit", "number", setupState.dailyLimit, (value) => {
      setupState.dailyLimit = value;
    }),
  );
  if (setupState.claudeReady) wrap.append(setupSuccess("Claude key accepted."));
  wrap.append(intro, grid, setupActions(true, "Test mailbox and continue", async () => {
    if (!setupState.claudeReady) {
      showSetupError("Go back and test the Claude key first.");
      return;
    }
    setupState.smtpHost = readInput("setup-smtp-host");
    setupState.smtpPort = readInput("setup-smtp-port") || "587";
    setupState.smtpUser = readInput("setup-smtp-user");
    setupState.smtpPassword = document.getElementById("setup-smtp-password").value;
    setupState.fromName = readInput("setup-from-name") || setupState.company || setupState.name;
    setupState.dailyLimit = readInput("setup-daily");
    const limit = Number(setupState.dailyLimit);
    if (!setupState.smtpHost || !setupState.smtpUser || !setupState.smtpPassword) {
      showSetupError("Add the mailbox host, email, and password.");
      return;
    }
    if (!Number.isInteger(limit) || limit < 1 || limit > 200) {
      showSetupError("Daily send limit must be a whole number from 1 to 200.");
      return;
    }
    const viaGmail = setupState.smtpHost.toLowerCase().includes("gmail");
    const prefix = viaGmail ? "GMAIL" : "CUSTOM";
    const button = document.getElementById("setup-next");
    if (button) button.disabled = true;
    try {
      await API.post("/api/setup/progress", {});
      await API.post("/api/settings", {
        [prefix + "_SMTP_HOST"]: setupState.smtpHost,
        [prefix + "_SMTP_PORT"]: setupState.smtpPort,
        [prefix + "_SMTP_USER"]: setupState.smtpUser,
        [prefix + "_SMTP_PASSWORD"]: setupState.smtpPassword,
        [prefix + "_FROM_NAME"]: setupState.fromName,
        DAILY_SEND_LIMIT: String(limit),
      });
      const test = await API.post("/api/settings/test/" + (viaGmail ? "gmail" : "custom") + "-smtp");
      if (!test.ok) {
        setupState.mailboxReady = false;
        showSetupError(test.message || "Mailbox connection failed.");
        return;
      }
      setupState.mailboxReady = true;
      setupState.step = 6;
      buildSetupUI();
    } catch (error) {
      showSetupError(error.message || "Could not test the mailbox.");
    } finally {
      if (button && setupState.step === 5) button.disabled = false;
    }
  }));
  return wrap;
}

function setupReviewStep() {
  const wrap = document.createElement("div");
  const intro = document.createElement("p");
  intro.className = "setup-lead";
  intro.textContent = "Finish checks the marked cities with Google once more and opens the workspace. You can change the country, state, and cities later in Settings. Passwords and API keys are not shown here.";
  const list = document.createElement("dl");
  list.className = "setup-summary";
  const places = placesMatch()
    ? setupState.confirmed.cities.map((city) => city.formatted_address)
    : setupState.cityPicks.map((city) => city.state ? city.name + ", " + city.state : city.name);
  const country = placesMatch() ? setupState.confirmed.country_name : (setupState.countryPick ? setupState.countryPick.name : "");
  const rows = [
    ["Name", setupState.name],
    ["Company", setupState.company || "—"],
    ["Country", country],
    ["Places", places.join("; ")],
    ["Contact", AUDIENCE_LABELS[setupState.audience] || setupState.audience],
    ["Niches", chosenNiches().join(", ")],
    ["Mailbox", setupState.smtpUser],
    ["Daily limit", setupState.dailyLimit],
    ["Signature", signaturePreview()],
  ];
  rows.forEach(([label, value]) => {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    list.append(dt, dd);
  });
  wrap.append(intro, list, setupActions(true, "Finish setup", async () => {
    if (!placesMatch()) {
      showSetupError("Go back and check the places again.");
      return;
    }
    const button = document.getElementById("setup-next");
    if (button) {
      button.disabled = true;
      button.textContent = "Confirming places…";
    }
    try {
      const result = await API.post("/api/setup", {
        name: setupState.name.trim(),
        company: setupState.company.trim(),
        role: setupState.role.trim(),
        phone: setupState.phone.trim(),
        website: setupState.website.trim(),
        signature: setupState.signature.trim(),
        country: setupState.countryPick ? setupState.countryPick.name : "",
        cities: setupState.cityPicks.map((city) => city.name),
        choices: chosenChoices(),
        audience: setupState.audience,
        niches: chosenNiches(),
        smtp_host: setupState.smtpHost.trim(),
        smtp_port: setupState.smtpPort.trim() || "587",
        smtp_user: setupState.smtpUser.trim(),
        smtp_password: setupState.smtpPassword,
        from_name: setupState.fromName.trim() || setupState.company.trim() || setupState.name.trim(),
        daily_limit: Number(setupState.dailyLimit),
        claude_api_key: setupState.claudeKey.trim(),
        google_maps_api_key: setupState.mapsKey.trim(),
      });
      if (!result.ok) {
        showSetupError(result.message || "Setup could not finish.");
        if (button) {
          button.disabled = false;
          button.textContent = "Finish setup";
        }
        return;
      }
      window.location.hash = "dashboard";
      window.location.reload();
    } catch (error) {
      showSetupError(error.message || "Setup could not finish.");
      if (button) {
        button.disabled = false;
        button.textContent = "Finish setup";
      }
    }
  }));
  return wrap;
}

window.init_setup = buildSetupUI;
