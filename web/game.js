"use strict";
const $ = (id) => document.getElementById(id);
let state = { phase: "home" },
  roster = [],
  busy = false;
async function api(path, data, actionKey) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch("/api/" + path, {
      method: data === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json", "X-Cricinator": "1", ...(actionKey ? {"Idempotency-Key": actionKey} : {}) },
      signal: controller.signal,
      ...(data === undefined ? {} : { body: JSON.stringify(data) }),
    });
    const value = await response.json().catch(() => null);
    if (!response.ok || !value)
      throw new Error(value?.error || "The game is unavailable. Please try again shortly.");
    return value;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("The server took too long. Please try again.");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
async function act(path, data = {}) {
  if (busy) return;
  busy = true;
  setHost("thinking");
  $("game").setAttribute("aria-busy", "true");
  $("status").textContent = "";
  document
    .querySelectorAll("#game button,#start")
    .forEach((b) => (b.disabled = true));
  try {
    state = await api(path, path === "start" ? {...data, mode: $("mode").value, revision: state.revision} : {...data, revision: state.revision}, crypto.randomUUID());
    render();
  } catch (e) {
    try { state = await api("state"); render(); } catch (_) { /* Preserve the original action error. */ }
    $("status").textContent = e.message;
  } finally {
    busy = false;
    $("game").setAttribute("aria-busy", "false");
    setHost(state.phase);
    document
      .querySelectorAll("#game button,#start")
      .forEach((b) => (b.disabled = false));
    $("undo").disabled = !state.can_undo;
    if (!$("correction").hidden) $("save-correction").disabled = correctionMode !== (state.mode || $("mode").value);
  }
}
function setHost(phase) {
  window.cricinatorPhase = phase;
  window.dispatchEvent(new CustomEvent("cricinator-state", {detail: {phase}}));
}
function render() {
  document.body.dataset.phase = state.phase;
  setHost(state.phase);
  const home = state.phase === "home";
  $("home").hidden = !home;
  $("game").hidden = home;
  if (state.notice) $("status").textContent = state.notice;
  if (state.mode) $("mode").value = state.mode;
  if (home) return;
  const question = state.phase === "question";
  $("question-panel").hidden = !question;
  $("result-panel").hidden = question;
  $("round-label").textContent = question
    ? `QUESTION ${String(state.count + 1).padStart(2, "0")}`
    : `${state.count} QUESTIONS ANSWERED`;
  const confidence = Math.round((state.confidence || 0) * 100);
  $("engine-note").textContent = state.engine_path === "legacy_fallback"
    ? `Legacy fallback active · ${confidence}% confidence · ${state.fallback_reason}`
    : `AI engine active · ${confidence}% confidence`;
  $("progress").value = state.count || 0;
  $("undo").disabled = !state.can_undo;
  if (question) {
    $("question").textContent = state.question.text;
    $("question").focus();
    return;
  }
  const complete = state.phase === "complete",
    miss = state.phase === "miss";
  $("guess-actions").hidden = complete || miss;
  $("correction").hidden = !miss;
  if (miss) loadCorrection();
  $("play-again").hidden = !complete;
  $("profile").hidden = miss;
  $("initials").hidden = miss;
  $("result-kicker").textContent = complete
    ? "THAT’S A WRAP"
    : miss
      ? "YOU WIN THIS ROUND"
      : state.uncertain
        ? "MY BEST GUESS"
        : "I THINK I’VE GOT IT";
  $("guess-name").textContent = miss ? "A tricky innings." : state.player.name;
  $("guess-detail").textContent = miss
    ? ""
    : `${state.player.country} · ${state.player.role || "International cricketer"}`;
  $("result-message").textContent = complete
    ? "Feedback saved for review. Thanks for playing."
    : miss
      ? state.message
      : state.uncertain
        ? "The clues are mixed. Is this who you had in mind?"
        : "Is this your cricketer?";
  if (!miss) {
    $("initials").textContent = state.player.name
      .split(" ")
      .map((x) => x[0])
      .slice(0, 2)
      .join("");
    $("profile").href = state.player.source;
  }
  $("result-panel").classList.remove("reveal");
  void $("result-panel").offsetWidth;
  $("result-panel").classList.add("reveal");
  $("guess-name").focus();
}
let catalogMode = false, searchTimer, searchVersion = 0;
async function showCatalog() {
  const version = ++searchVersion;
  $("catalog-status").textContent = "Searching the world catalog…";
  try {
    const data = await api("catalog?q=" + encodeURIComponent($("search").value) + "&limit=100");
    if (version !== searchVersion || !catalogMode) return;
    $("roster-list").replaceChildren();
    for (const p of data.players) {
      const el = document.createElement("div"); el.className = "roster-entry";
      el.textContent = p.name;
      const detail = document.createElement("span");
      detail.textContent = [...(p.countries || []), ...(p.formats || []), p.playable ? "Enriched profile" : "World beta"].join(" · ");
      el.append(detail); $("roster-list").append(el);
    }
    $("catalog-status").textContent = `${data.total.toLocaleString()} matches · showing ${data.players.length}`;
  } catch (error) { if (version === searchVersion) $("catalog-status").textContent = error.message; }
}
function showRoster() {
  if (catalogMode) { showCatalog(); return; }
  ++searchVersion;
  $("catalog-status").textContent = "";
  const query = $("search").value.toLowerCase();
  $("roster-list").replaceChildren();
  const matching = roster.filter((p) =>
    (p.name + " " + p.country).toLowerCase().includes(query),
  );
  for (const p of matching) {
    const el = document.createElement("div");
    el.className = "roster-entry";
    el.textContent = p.name;
    const detail = document.createElement("span");
    detail.textContent = p.country + " · " + p.role;
    el.append(detail);
    $("roster-list").append(el);
  }
  if (!matching.length)
    $("roster-list").textContent = "No matching players in this roster.";
}
$("start").onclick = () => act("start");
$("restart").onclick = () => act("start");
$("play-again").onclick = () => act("start");
$("answers").onclick = (e) => {
  const b = e.target.closest("[data-answer]");
  if (b)
    act("answer", { question: state.question.id, answer: b.dataset.answer });
};
$("undo").onclick = () => act("undo");
$("confirm").onclick = () => act("feedback", { player: state.player.id });
$("reject").onclick = () => act("reject");
let correctionMode = null, correctionVersion = 0;
async function loadCorrection() {
  const mode = state.mode || $("mode").value;
  if (correctionMode === mode) return;
  const version = ++correctionVersion;
  $("save-correction").disabled = true;
  $("correct-player").disabled = true;
  $("correct-player").replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = ""; placeholder.textContent = "Loading players…";
  $("correct-player").append(placeholder);
  try {
    const data = mode === "classic" ? {players: roster} : await api("roster?mode=" + encodeURIComponent(mode));
    if (version !== correctionVersion) return;
    placeholder.textContent = "Select your player";
    for (const p of data.players) {
      const option = document.createElement("option");
      option.value = p.id;
      option.textContent = p.name + (p.country ? " · " + p.country : "");
      $("correct-player").append(option);
    }
    correctionMode = mode;
  } catch (error) {
    placeholder.textContent = "Could not load players. Reopen correction to retry.";
    $("status").textContent = error.message;
  } finally {
    if (version === correctionVersion) {
      $("correct-player").disabled = false;
      $("save-correction").disabled = correctionMode !== mode;
    }
  }
}
$("mode").onchange = () => { correctionMode = null; ++correctionVersion; $("correct-player").replaceChildren(); };
$("correct").onclick = () => {
  $("correction").hidden = false;
  $("guess-actions").hidden = true;
  loadCorrection();
  $("correct-player").focus();
};
$("save-correction").onclick = () => {
  const player = $("correct-player").value;
  if (player) act("feedback", { player });
  else $("status").textContent = "Choose a player first.";
};
$("roster-open").onclick = () => {
  $("roster-dialog").showModal();
  showRoster();
};
$("roster-close").onclick = () => $("roster-dialog").close();
$("search").oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(showRoster, 200); };
for (const [id, world] of [["playable-tab", false], ["catalog-tab", true]]) {
  $(id).onclick = () => { catalogMode = world;
    $("playable-tab").setAttribute("aria-pressed", String(!world));
    $("catalog-tab").setAttribute("aria-pressed", String(world)); showRoster(); };
}
api("coverage").then(data => {
  $("catalog-count").textContent = data.catalog_count.toLocaleString();
  $("coverage-note").textContent = `${data.playable_count.toLocaleString()} enriched profiles · ${data.catalog_count.toLocaleString()} international records. Records can overlap across formats; World beta includes incomplete profiles.`;
}).catch(() => { $("catalog-count").textContent = "Beta"; });
api("research").then(data => {
  $("classic-score").textContent = data.classic.clean_accuracy;
  $("classic-detail").textContent = `${data.classic.clean_first_guess} first guesses across ${data.classic.players} curated profiles; mean ${data.classic.mean_questions} questions.`;
  $("noisy-score").textContent = data.classic.noisy_accuracy;
  $("noisy-detail").textContent = `${data.classic.noisy_first_guess} with ${data.classic.noise_model}.`;
  $("world-records").textContent = data.world.records.toLocaleString();
  $("world-detail").textContent = `${data.world.questions} generated questions from ${data.world.parsed_source_pages} parsed source pages.`;
  $("limit-score").textContent = data.world.sample_accuracy;
  $("limit-detail").textContent = `${data.world.ambiguous_records.toLocaleString()} records share a fact signature, so World stays beta until more facts are verified.`;
  $("pipeline").replaceChildren(...data.pipeline.map((step, index) => {
    const item = document.createElement("li");
    item.textContent = `${String(index + 1).padStart(2, "0")} ${step}`;
    return item;
  }));
}).catch(() => {
  $("classic-detail").textContent = "Research metrics are unavailable on this server.";
});
document.addEventListener("keydown", (e) => {
  if (
    busy ||
    state.phase !== "question" ||
    $("roster-dialog").open ||
    ["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName) ||
    e.ctrlKey ||
    e.metaKey ||
    e.altKey
  )
    return;
  const keys = ["yes", "probably", "unknown", "probably_not", "no"];
  if (keys[Number(e.key) - 1]) {
    e.preventDefault();
    act("answer", {
      question: state.question.id,
      answer: keys[Number(e.key) - 1],
    });
  }
});
(async () => {
  try {
    const [data, saved] = await Promise.all([api("roster"), api("state")]);
    roster = data.players;
    $("player-count").textContent = roster.length;
    state = saved;
    render();
  } catch (e) {
    $("status").textContent =
      "Could not connect to the game. Refresh to retry.";
    $("start").disabled = true;
  }
})();
