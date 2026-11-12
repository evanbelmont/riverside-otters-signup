// Club Event Signup — browser code.
// Talks to the local server (server.py), which saves everything in SQLite.
// Nothing is kept in localStorage; lists always come from the database.

const SESSIONS = ["Beginner Lesson", "Advanced Practice"];

const form = document.getElementById("signup-form");
const nameInput = document.getElementById("attendee-name");
const sessionRadios = document.querySelectorAll('input[name="session"]');
const messageArea = document.getElementById("message-area");
const joinButton = document.getElementById("join-waitlist");
const waitlistHint = document.getElementById("waitlist-hint");

const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const clearButton = document.getElementById("clear-search");
const listMessage = document.getElementById("list-message");
const listStatus = document.getElementById("list-status");
const listCaption = document.getElementById("list-caption");
const regList = document.getElementById("registration-list");
const countsList = document.getElementById("session-counts");
const listHeading = document.getElementById("registrations-heading");

const waitlistMessage = document.getElementById("waitlist-message");
const waitlistGroups = document.getElementById("waitlist-groups");
const waitlistHeading = document.getElementById("waitlist-heading");

const NAME_ERROR = "Please enter an attendee name.";
const SESSION_ERROR = "Please choose a session.";
const SERVER_ERROR = "Could not reach the server. Make sure it is running, then try again.";

let currentSearch = "";
let latestListRequest = 0;
let sessionInfo = {}; // latest spots/waiting numbers, by session name

// ---------- Shared helpers ----------

// Each message goes on its own line inside the given message area.
// `promotions` are extra lines naming anyone moved off the waitlist.
function showMessages(area, lines, kind, promotions = []) {
  area.replaceChildren();
  for (const text of lines) area.appendChild(el("p", kind, text));
  for (const text of promotions) area.appendChild(el("p", "promotion", text));
}

// Show the server's answer for an action in the given area.
function showResult(area, result) {
  if (result.ok) {
    showMessages(area, [result.data.message], "success", result.data.promotions || []);
  } else {
    showMessages(area, result.data.errors || [SERVER_ERROR], "error");
  }
}

// Sends a request to the server. Always resolves to { ok, status, data }.
async function api(method, url, body) {
  try {
    const options = { method, headers: {} };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    const data = await response.json();
    return { ok: response.ok, status: response.status, data };
  } catch {
    return { ok: false, status: 0, data: { errors: [SERVER_ERROR] } };
  }
}

function otherSession(session) {
  return SESSIONS.find((s) => s !== session);
}

function spotsText(info) {
  if (info.full) return "Full";
  return `${info.remaining} ${info.remaining === 1 ? "spot" : "spots"} left`;
}

// Small helper to build elements: el("span", "class-name", "text")
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// ---------- Signup form ----------

function selectedSession() {
  const checked = document.querySelector('input[name="session"]:checked');
  return checked ? checked.value : null;
}

// Checks name + session. Shows errors and returns null if something is wrong.
function readValidForm() {
  const name = nameInput.value.trim();
  const session = selectedSession();
  const nameValid = name !== "";
  const sessionValid = session !== null;

  if (nameValid && sessionValid) return { name, session };

  // Invalid: never show success, and never erase what the user entered.
  const errors = [];
  if (!nameValid) errors.push(NAME_ERROR);
  if (!sessionValid) errors.push(SESSION_ERROR);
  showMessages(messageArea, errors, "error");
  if (!nameValid) {
    nameInput.focus();
  } else {
    sessionRadios[0].focus();
  }
  return null;
}

// Sign Up button, Enter in the name field, or Enter/Space on the button.
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = readValidForm();
  if (!input) return;

  messageArea.replaceChildren();
  const result = await api("POST", "/api/registrations", input);

  if (result.ok) {
    // Only show success after the database has saved the row.
    const saved = result.data.registration;
    showMessages(messageArea, [`Success! ${saved.name} is signed up for ${saved.session}.`], "success");
  } else {
    showMessages(messageArea, result.data.errors || [SERVER_ERROR], "error");
  }
  await loadRegistrations(); // refresh list, counts, spots, and waitlist offer
});

// Join Waitlist: same name + session rules as Sign Up.
joinButton.addEventListener("click", async () => {
  const input = readValidForm();
  if (!input) return;

  messageArea.replaceChildren();
  const result = await api("POST", "/api/waitlist", input);
  showResult(messageArea, result); // e.g. "Mia Lopez is #2 on the waitlist for Beginner Lesson."
  await loadRegistrations();
});

// Offer "Join Waitlist" only when the chosen session is full.
function updateWaitlistOffer() {
  const session = selectedSession();
  const info = session ? sessionInfo[session] : null;
  const full = Boolean(info && (info.full || info.waiting > 0));

  joinButton.hidden = !full;
  waitlistHint.hidden = !full;
  if (full) {
    const waiting = info.waiting === 1 ? "1 person is" : `${info.waiting} people are`;
    waitlistHint.textContent =
      `${session} is full (${waiting} waiting). ` +
      "Press Join Waitlist to be registered automatically when a spot opens.";
  }
}

// An old confirmation disappears as soon as the name or session changes.
// Error messages stay until a button is pressed again.
function clearConfirmationOnChange() {
  if (messageArea.querySelector(".success")) messageArea.replaceChildren();
}

nameInput.addEventListener("input", clearConfirmationOnChange);
sessionRadios.forEach((radio) => {
  radio.addEventListener("change", () => {
    clearConfirmationOnChange();
    updateWaitlistOffer();
  });
});

// ---------- Loading everything from the server ----------

async function loadRegistrations() {
  const requestId = ++latestListRequest;
  const url = "/api/registrations?search=" + encodeURIComponent(currentSearch);
  const result = await api("GET", url);

  // Ignore answers to older requests that arrive late.
  if (requestId !== latestListRequest) return;

  if (result.ok) {
    renderCounts(result.data.counts);
    renderList(result.data.registrations);
    renderWaitlist(result.data.waitlist);
    updateWaitlistOffer();
  } else {
    regList.replaceChildren();
    listCaption.hidden = true;
    listStatus.textContent = "Could not load registrations. Make sure the server is running.";
  }
}

function renderCounts(counts) {
  countsList.replaceChildren();
  sessionInfo = {};

  for (const info of counts.sessions) {
    sessionInfo[info.session] = info;

    const item = el("li", info.full ? "count is-full" : "count");
    item.append(
      el("span", "count-name", info.session),
      el("span", "count-detail", `${info.registered} of ${counts.capacity} registered`),
    );
    if (info.waiting > 0) {
      item.append(el("span", "count-detail", `${info.waiting} on waitlist`));
    }
    item.append(el("span", info.full ? "badge badge-full" : "badge badge-open", spotsText(info)));
    countsList.appendChild(item);

    // Also show spots next to the matching choice in the signup form.
    const formSpots = document.querySelector(`[data-spots-for="${info.session}"]`);
    if (formSpots) {
      formSpots.textContent = spotsText(info);
      formSpots.classList.toggle("badge-full", info.full);
      formSpots.classList.toggle("badge-open", !info.full);
      formSpots.classList.add("badge");
    }
  }

  const total = el("li", "count count-total");
  total.append(el("span", "count-name", "Total"), el("span", "count-detail", String(counts.total)));
  countsList.appendChild(total);
}

// ---------- Saved registrations list ----------

// The server already sorts names A–Z, so rows are shown in the order received.
function renderList(registrations) {
  regList.replaceChildren();

  if (registrations.length === 0) {
    listCaption.hidden = true;
    listStatus.textContent = currentSearch ? "No registrations found" : "No registrations yet.";
    return;
  }

  for (const reg of registrations) regList.appendChild(buildRow(reg));
  listCaption.hidden = false;

  const count = registrations.length;
  const plural = count === 1 ? "registration" : "registrations";
  listStatus.textContent = currentSearch
    ? `${count} ${plural} matching "${currentSearch}".`
    : `${count} ${plural}.`;
}

// One saved registration: name, session, and its three controls.
function buildRow(reg) {
  const item = el("li", "reg-item");
  item.dataset.id = reg.id;

  const info = el("div", "reg-info");
  info.append(el("span", "reg-name", reg.name), el("span", "reg-session", reg.session));

  const actions = el("div", "reg-actions");

  // Attended checkbox (the hidden text tells screen readers whose box it is)
  const attendedLabel = el("label", "attended");
  const checkbox = el("input");
  checkbox.type = "checkbox";
  checkbox.checked = reg.attended;
  checkbox.dataset.action = "attended";
  attendedLabel.append(checkbox, el("span", null, "Attended"), el("span", "sr-only", ` — ${reg.name}, ${reg.session}`));

  // Change Session button: moves this row to the other session
  const target = otherSession(reg.session);
  const changeButton = el("button", "secondary small");
  changeButton.type = "button";
  changeButton.dataset.action = "change";
  changeButton.dataset.target = target;
  changeButton.append("Change ", el("span", "sr-only", `${reg.name}'s session `), `to ${target}`);

  // Cancel button
  const cancelButton = el("button", "danger small");
  cancelButton.type = "button";
  cancelButton.dataset.action = "cancel";
  cancelButton.append("Cancel", el("span", "sr-only", ` ${reg.name}'s ${reg.session} signup`));

  actions.append(attendedLabel, changeButton, cancelButton);
  item.append(info, actions);
  item._registration = reg;
  return item;
}

function setBusy(item, busy) {
  item.querySelectorAll("button, input").forEach((control) => {
    control.disabled = busy;
  });
  item.classList.toggle("is-busy", busy);
}

// After the list is redrawn, put keyboard focus back where the user was.
function restoreFocus(id, action) {
  const control = regList.querySelector(`.reg-item[data-id="${id}"] [data-action="${action}"]`);
  (control || listHeading).focus();
}

// One listener handles the buttons on every row.
regList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const item = button.closest(".reg-item");
  const reg = item._registration;

  if (button.dataset.action === "change") {
    setBusy(item, true);
    const result = await api("PATCH", `/api/registrations/${reg.id}`, { session: button.dataset.target });
    showResult(listMessage, result); // includes anyone promoted into the freed spot
    await loadRegistrations();
    restoreFocus(reg.id, "change");
  }

  if (button.dataset.action === "cancel") {
    const sure = window.confirm(`Cancel ${reg.name}'s signup for ${reg.session}?\n\nThis removes it from the database.`);
    if (!sure) return;
    setBusy(item, true);
    const result = await api("DELETE", `/api/registrations/${reg.id}`);
    showResult(listMessage, result); // includes anyone promoted into the freed spot
    await loadRegistrations();
    listHeading.focus(); // the row is gone, so focus the section heading
  }
});

// Attended checkbox: save to the database right away.
regList.addEventListener("change", async (event) => {
  const checkbox = event.target.closest('input[data-action="attended"]');
  if (!checkbox) return;
  const item = checkbox.closest(".reg-item");
  const reg = item._registration;
  const wanted = checkbox.checked;

  setBusy(item, true);
  const result = await api("PATCH", `/api/registrations/${reg.id}`, { attended: wanted });
  setBusy(item, false);

  if (result.ok) {
    reg.attended = result.data.registration.attended;
  } else {
    checkbox.checked = !wanted; // not saved, so undo the tick
    if (result.status === 404) await loadRegistrations();
  }
  showResult(listMessage, result);
  checkbox.focus();
});

// ---------- Waitlist ----------

// One group per session, people in joining order with their position.
function renderWaitlist(entries) {
  waitlistGroups.replaceChildren();

  for (const session of SESSIONS) {
    const group = el("div", "waitlist-group");
    const people = entries.filter((entry) => entry.session === session);
    const headingId = `waitlist-${session.replace(/\s+/g, "-").toLowerCase()}`;

    const heading = el("h3", null, session);
    heading.id = headingId;
    heading.append(el("span", "waitlist-count", ` — ${people.length} waiting`));
    group.appendChild(heading);

    if (people.length === 0) {
      group.appendChild(el("p", "waitlist-empty", "No one is waiting."));
    } else {
      const list = el("ol", "waitlist-list");
      list.setAttribute("aria-labelledby", headingId);
      for (const entry of people) list.appendChild(buildWaitlistRow(entry));
      group.appendChild(list);
    }
    waitlistGroups.appendChild(group);
  }
}

function buildWaitlistRow(entry) {
  const item = el("li", "waitlist-item");
  item.dataset.id = entry.id;

  const info = el("div", "waitlist-info");
  info.append(
    el("span", "waitlist-position", `#${entry.position}`),
    el("span", "reg-name", entry.name),
    el("span", "reg-session", entry.session),
  );

  const leaveButton = el("button", "danger small");
  leaveButton.type = "button";
  leaveButton.dataset.action = "leave";
  leaveButton.append("Leave Waitlist", el("span", "sr-only", ` — ${entry.name}, ${entry.session}`));

  item.append(info, leaveButton);
  item._entry = entry;
  return item;
}

waitlistGroups.addEventListener("click", async (event) => {
  const button = event.target.closest('button[data-action="leave"]');
  if (!button) return;
  const item = button.closest(".waitlist-item");
  const entry = item._entry;

  const sure = window.confirm(`Remove ${entry.name} from the waitlist for ${entry.session}?`);
  if (!sure) return;
  setBusy(item, true);
  const result = await api("DELETE", `/api/waitlist/${entry.id}`);
  showResult(waitlistMessage, result);
  await loadRegistrations();
  waitlistHeading.focus(); // the row is gone, so focus the section heading
});

// ---------- Search ----------

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  currentSearch = searchInput.value.trim();
  loadRegistrations();
});

clearButton.addEventListener("click", () => {
  searchInput.value = "";
  currentSearch = "";
  loadRegistrations();
  searchInput.focus();
});

// ---------- Page open ----------

// Every time the page opens (or comes back via back/forward), start the form
// fresh and read registrations and the waitlist from the database.
window.addEventListener("pageshow", () => {
  form.reset();
  searchForm.reset();
  currentSearch = "";
  messageArea.replaceChildren();
  listMessage.replaceChildren();
  waitlistMessage.replaceChildren();
  updateWaitlistOffer();
  loadRegistrations();
});
