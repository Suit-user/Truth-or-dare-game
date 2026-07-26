// Truth or Dare -- front-end controller.
// Renders entirely from the JSON the server returns; every action call
// (category, complete, skip, double_skip, players, etc.) gets back a
// fresh state snapshot and we just re-render from it. No client-side
// game rules live here -- the server (game_logic.py) is the single
// source of truth, which matters since this is one shared game state
// for the whole room.

const APP = document.getElementById("app");
const LOAD_INPUT = document.getElementById("load-file-input");

let currentState = null;   // last state snapshot from the server
let viewingStats = false;  // client-only overlay flag, independent of server screen
let toastTimer = null;

// ---------------------------------------------------------------------
// Networking helpers
// ---------------------------------------------------------------------
async function getJSON(url) {
  const res = await fetch(url);
  return res.json();
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

async function deleteJSON(url) {
  const res = await fetch(url, { method: "DELETE" });
  return res.json();
}

function applyState(state) {
  currentState = state;
  if (state.error) {
    showToast(state.error);
  }
  render();
}

function showToast(message) {
  clearTimeout(toastTimer);
  let toast = document.querySelector(".toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toastTimer = setTimeout(() => toast.remove(), 2600);
}

// ---------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------
async function addPlayer() {
  const input = document.getElementById("name-input");
  const name = input.value;
  const state = await postJSON("/api/players", { name });
  applyState(state);
  if (!state.error) {
    const newInput = document.getElementById("name-input");
    if (newInput) { newInput.value = ""; newInput.focus(); }
  }
}

async function removePlayer(index) {
  applyState(await deleteJSON(`/api/players/${index}`));
}

async function shufflePlayers() {
  applyState(await postJSON("/api/shuffle"));
}

async function startGame() {
  applyState(await postJSON("/api/start"));
}

async function selectCategory(category) {
  applyState(await postJSON("/api/category", { category }));
}

async function completeCurrent() {
  applyState(await postJSON("/api/complete"));
}

async function skipCurrent() {
  const checkbox = document.getElementById("impossible-checkbox");
  if (checkbox && checkbox.checked) return; // Skip disabled while Impossible is checked
  applyState(await postJSON("/api/skip"));
}

async function doubleSkipCurrent() {
  applyState(await postJSON("/api/double_skip"));
}

async function resetGame(confirmFirst) {
  if (confirmFirst && !confirm("Start a brand new game? Current progress will be lost.")) {
    return;
  }
  viewingStats = false;
  applyState(await postJSON("/api/reset"));
}

function saveGame() {
  window.location.href = "/api/save";
}

function triggerLoad() {
  LOAD_INPUT.click();
}

LOAD_INPUT.addEventListener("change", async () => {
  const file = LOAD_INPUT.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/api/load", { method: "POST", body: formData });
  const state = await res.json();
  viewingStats = false;
  applyState(state);
  LOAD_INPUT.value = "";
});

function toggleDarkMode() {
  document.body.classList.toggle("light-mode");
  localStorage.setItem(
    "tod-theme",
    document.body.classList.contains("light-mode") ? "light" : "dark"
  );
}

function openStats() { viewingStats = true; render(); }
function closeStats() { viewingStats = false; render(); }

// ---------------------------------------------------------------------
// Keyboard shortcuts
// ---------------------------------------------------------------------
document.addEventListener("keydown", (event) => {
  if (!currentState || currentState.screen !== "game" || viewingStats) return;
  const tag = (event.target.tagName || "").toLowerCase();
  if (tag === "input") return; // don't hijack typing in the name field

  if (event.key === "Enter" && currentState.current_prompt) {
    completeCurrent();
  } else if ((event.key === "s" || event.key === "S") && currentState.current_prompt) {
    skipCurrent();
  } else if ((event.key === "d" || event.key === "D") && currentState.current_prompt) {
    doubleSkipCurrent();
  } else if (["1", "2", "3", "4"].includes(event.key) && !currentState.current_prompt) {
    const categories = ["Normal Truth", "Spicy Truth", "Normal Dare", "Spicy Dare"];
    selectCategory(categories[parseInt(event.key, 10) - 1]);
  }
});

// ---------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------
function render() {
  if (!currentState) return;

  if (viewingStats) {
    APP.innerHTML = renderStats(currentState);
    return;
  }

  switch (currentState.screen) {
    case "setup":
      APP.innerHTML = renderSetup(currentState);
      break;
    case "game":
      APP.innerHTML = renderGame(currentState);
      break;
    case "game_over":
      APP.innerHTML = renderGameOver(currentState);
      break;
    default:
      APP.innerHTML = `<div class="screen"><p>${currentState.error || "Something went wrong."}</p></div>`;
  }

  wireEvents();
}

function renderSetup(state) {
  const players = state.players
    .map(
      (p, i) => `
      <div class="player-row">
        <span>${i + 1}. ${escapeHTML(p.name)}</span>
        <button class="danger remove-btn" data-remove="${i}">Remove</button>
      </div>`
    )
    .join("");

  return `
    <div class="screen">
      <h1 class="title">Truth or Dare</h1>
      <p class="subtitle">Add at least two players to begin</p>

      <div class="entry-row">
        <input id="name-input" type="text" placeholder="Player name" autofocus>
        <button class="primary" id="add-player-btn">Add Player</button>
      </div>

      <div class="player-list">
        ${players || '<p class="subtitle">No players yet</p>'}
      </div>

      <div class="setup-actions">
        <button id="shuffle-btn">Shuffle Players</button>
        <button id="load-btn">Load Game</button>
      </div>

      <button class="primary start-btn" id="start-btn" ${state.can_start ? "" : "disabled"}>
        Start Game
      </button>
    </div>
  `;
}

function renderGame(state) {
  const bonus =
    state.forced_queue_length > 0
      ? `<span class="bonus-tag">Bonus prompts left: ${state.forced_queue_length}</span>`
      : "";

  const topBar = `
    <div class="top-bar">
      <button id="stats-btn">Stats</button>
      <button id="save-btn">Save Game</button>
      <button id="load-btn">Load Game</button>
      <button id="dark-btn">Dark Mode</button>
      <button class="danger" id="reset-btn">Reset Game</button>
    </div>`;

  const header = `
    <div class="player-name">Current Player:<br>${escapeHTML(state.current_player_name || "")}</div>
    <div class="skips-line">Skips Remaining: ${currentPlayerSkips(state)} ${bonus ? " | " + bonus : ""}</div>
  `;

  let body;
  if (!state.current_prompt) {
    body = `
      <div class="category-grid">
        ${["Normal Truth", "Spicy Truth", "Normal Dare", "Spicy Dare"]
          .map(
            (cat, i) => `
          <button class="category-btn" data-category="${cat}" ${state.category_is_empty[cat] ? "disabled" : ""}>
            ${cat}<small>press ${i + 1}</small>
          </button>`
          )
          .join("")}
      </div>
    `;
  } else {
    body = `
      <div class="prompt-box">
        <div>
          <span class="cat-label">${escapeHTML(state.current_category)}</span>
          ${escapeHTML(state.current_prompt)}
        </div>
      </div>

      <div class="impossible-row">
        <input type="checkbox" id="impossible-checkbox">
        <label for="impossible-checkbox">Impossible</label>
      </div>

      <div class="action-row">
        <button class="success" id="complete-btn">Completed (Enter)</button>
        <button class="warning" id="skip-btn" ${currentPlayerSkips(state) <= 0 ? "disabled" : ""}>Skip (S)</button>
        <button class="danger" id="double-skip-btn">Double Skip (D)</button>
      </div>
    `;
  }

  const statusBar = `
    <div class="status-bar">
      Remaining prompts: ${totalRemaining(state)} &nbsp;|&nbsp;
      Current player: ${escapeHTML(state.current_player_name || "")} &nbsp;|&nbsp;
      Skips left: ${currentPlayerSkips(state)} &nbsp;|&nbsp;
      Completed: ${state.completed_total}
    </div>
  `;

  return `<div class="screen">${topBar}${header}${body}</div>${statusBar}`;
}

function renderStats(state) {
  const counts = Object.entries(state.counts_by_category)
    .map(([cat, count]) => `<p>Remaining ${escapeHTML(cat)}: ${count}</p>`)
    .join("");

  const playerRows = state.players
    .map(
      (p) => `
      <div class="player-stat-row">
        <strong>${escapeHTML(p.name)}</strong> &mdash;
        Completed: ${p.completed_count} &nbsp;
        Skips Used: ${p.skips_used} &nbsp;
        Double Skips: ${p.double_skips_used} &nbsp;
        Skips Remaining: ${p.skips_remaining}
      </div>`
    )
    .join("");

  const backLabel = state.started && !state.game_over ? "Back to Game" : "Back";

  return `
    <div class="screen">
      <h1 class="title">Statistics</h1>
      <div class="stats-card">
        <h3>Total Completed: ${state.completed_total}</h3>
        ${counts}
      </div>
      <div class="stats-card">
        <h3>Per-Player Stats</h3>
        ${playerRows || "<p>No players yet.</p>"}
      </div>
      <button class="primary" id="stats-back-btn">${backLabel}</button>
    </div>
  `;
}

function renderGameOver(state) {
  return `
    <div class="screen">
      <div class="game-over-title">Game Over!</div>
      <p class="subtitle">All truths and dares have been completed.</p>
      <div class="setup-actions">
        <button class="primary" id="stats-btn">View Statistics</button>
        <button class="success" id="play-again-btn">Play Again</button>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------
// Event wiring (re-run after every render since we rebuild the DOM)
// ---------------------------------------------------------------------
function wireEvents() {
  const byId = (id) => document.getElementById(id);

  if (byId("add-player-btn")) byId("add-player-btn").onclick = addPlayer;
  if (byId("name-input")) {
    byId("name-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") addPlayer();
    });
  }
  document.querySelectorAll("[data-remove]").forEach((btn) => {
    btn.onclick = () => removePlayer(parseInt(btn.dataset.remove, 10));
  });
  if (byId("shuffle-btn")) byId("shuffle-btn").onclick = shufflePlayers;
  if (byId("start-btn")) byId("start-btn").onclick = startGame;
  if (byId("load-btn")) byId("load-btn").onclick = triggerLoad;

  document.querySelectorAll("[data-category]").forEach((btn) => {
    btn.onclick = () => selectCategory(btn.dataset.category);
  });

  if (byId("complete-btn")) byId("complete-btn").onclick = completeCurrent;
  if (byId("skip-btn")) byId("skip-btn").onclick = skipCurrent;
  if (byId("double-skip-btn")) byId("double-skip-btn").onclick = doubleSkipCurrent;
  if (byId("impossible-checkbox")) {
    byId("impossible-checkbox").onchange = (e) => {
      const skipBtn = byId("skip-btn");
      if (skipBtn) skipBtn.disabled = e.target.checked || currentPlayerSkips(currentState) <= 0;
    };
  }

  if (byId("stats-btn")) byId("stats-btn").onclick = openStats;
  if (byId("stats-back-btn")) byId("stats-back-btn").onclick = closeStats;
  if (byId("save-btn")) byId("save-btn").onclick = saveGame;
  if (byId("dark-btn")) byId("dark-btn").onclick = toggleDarkMode;
  if (byId("reset-btn")) byId("reset-btn").onclick = () => resetGame(true);
  if (byId("play-again-btn")) byId("play-again-btn").onclick = () => resetGame(false);
}

// ---------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------
function currentPlayerSkips(state) {
  const player = state.players[state.current_player_index];
  return player ? player.skips_remaining : 0;
}

function totalRemaining(state) {
  return Object.values(state.counts_by_category).reduce((a, b) => a + b, 0);
}

function escapeHTML(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

// ---------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------
(function init() {
  if (localStorage.getItem("tod-theme") === "light") {
    document.body.classList.add("light-mode");
  }
  getJSON("/api/state").then(applyState);
})();
