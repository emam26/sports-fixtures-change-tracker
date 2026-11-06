const health = document.querySelector("#health");
const fixtureList = document.querySelector("#fixture-list");
const fixtureStatus = document.querySelector("#fixture-status");
const filters = document.querySelector("#filters");
const competitionSelect = document.querySelector("#competition");
const matchdaySelect = document.querySelector("#matchday");
const dialog = document.querySelector("#match-dialog");
const matchDetail = document.querySelector("#match-detail");
const emptyTemplate = document.querySelector("#empty-template");

const applicationState = {
  noteWritesEnabled: false,
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function setState(node, message, className = "") {
  node.textContent = message;
  node.classList.remove("error", "ok");
  if (className) node.classList.add(className);
}

function formatDate(value) {
  if (!value) return "Time not supplied";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Invalid source time";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

async function request(path, options = {}) {
  const headers = { Accept: "application/json", ...options.headers };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  if (response.status === 204) return null;
  return response.json();
}

async function checkHealth() {
  try {
    await request("/health");
    setState(health, "Database available", "ok");
  } catch (error) {
    setState(health, "Database unavailable", "error");
  }
}

async function loadServiceStatus() {
  try {
    const status = await request("/api/status");
    applicationState.noteWritesEnabled = status.note_writes_enabled;
  } catch (error) {
    applicationState.noteWritesEnabled = false;
  }
}

async function loadCompetitions() {
  try {
    const competitions = await request("/api/competitions");
    competitionSelect.replaceChildren(new Option("All loaded", ""));
    competitions.forEach((competition) => {
      const label = `${competition.name} ${competition.season}`;
      competitionSelect.append(new Option(label, competition.competition_season_id));
    });
    if (competitions.length === 1) {
      competitionSelect.value = String(competitions[0].competition_season_id);
    }
  } catch (error) {
    competitionSelect.replaceChildren(new Option("Unavailable", ""));
    competitionSelect.disabled = true;
    setState(fixtureStatus, "Competition information could not be loaded.", "error");
  }
}

async function loadMatchdays() {
  const params = new URLSearchParams();
  if (competitionSelect.value) {
    params.set("competition_season_id", competitionSelect.value);
  }
  const query = params.toString();
  const path = query ? `/api/matchdays?${query}` : "/api/matchdays";
  try {
    const matchdays = await request(path);
    const previous = matchdaySelect.value;
    matchdaySelect.replaceChildren(new Option("All loaded", ""));
    matchdays.forEach((matchday) => {
      const label = `Matchday ${matchday.matchday_number} (${matchday.match_count})`;
      matchdaySelect.append(new Option(label, matchday.matchday_number));
    });
    if ([...matchdaySelect.options].some((option) => option.value === previous)) {
      matchdaySelect.value = previous;
    }
  } catch (error) {
    matchdaySelect.replaceChildren(new Option("Unavailable", ""));
    setState(fixtureStatus, "Matchday information could not be loaded.", "error");
  }
}

function scoreText(match) {
  if (match.home_score === null || match.away_score === null) return "Not supplied";
  return `${match.home_score}\u2013${match.away_score}`;
}

function fixtureCard(match) {
  const card = element("article", "fixture-card");
  const meta = element("div", "fixture-meta");
  meta.append(
    element("span", "badge", match.is_finished ? "Finished" : "Upcoming"),
    element("span", "muted", `Matchday ${match.matchday_number ?? "Not supplied"}`),
  );
  const teams = element("div", "teams");
  const home = element("div", "scoreline");
  home.append(element("span", "", match.home_team), element("span", "score", scoreText(match)));
  teams.append(home, element("div", "", match.away_team));
  const button = element("button", "secondary", "View provenance");
  button.type = "button";
  button.addEventListener("click", () => showMatch(match.match_id));
  card.append(meta, teams, element("p", "muted", formatDate(match.kickoff_utc)), button);
  return card;
}

async function loadFixtures() {
  setState(fixtureStatus, "Loading fixtures...");
  fixtureList.replaceChildren();
  const params = new URLSearchParams({ limit: "200" });
  const finished = document.querySelector("#finished").value;
  const search = document.querySelector("#search").value.trim();
  if (competitionSelect.value) params.set("competition_season_id", competitionSelect.value);
  if (matchdaySelect.value) params.set("matchday", matchdaySelect.value);
  if (finished) params.set("finished", finished);
  if (search) params.set("search", search);
  try {
    const page = await request(`/api/matches?${params}`);
    setState(fixtureStatus, `${page.total} fixture${page.total === 1 ? "" : "s"}`);
    if (page.items.length === 0) {
      fixtureList.append(emptyTemplate.content.cloneNode(true));
      return;
    }
    page.items.forEach((match) => fixtureList.append(fixtureCard(match)));
  } catch (error) {
    setState(fixtureStatus, "Fixtures could not be loaded.", "error");
  }
}

function recordList(title, records, formatter) {
  const section = element("section", "record-list");
  section.append(element("h3", "", title));
  if (records.length === 0) {
    section.append(element("p", "muted", "No records."));
  } else {
    records.forEach((record) => section.append(formatter(record)));
  }
  return section;
}

function resultRow(result) {
  const score =
    result.home_score === null || result.away_score === null
      ? "Not supplied"
      : `${result.home_score}\u2013${result.away_score}`;
  return element("p", "", `${result.result_type}: ${score}`);
}

function goalRow(goal) {
  const score =
    goal.score_home === null || goal.score_away === null
      ? "Score not supplied"
      : `${goal.score_home}\u2013${goal.score_away}`;
  const minute = goal.minute === null ? "" : ` - ${goal.minute}'`;
  const scorer = goal.scorer_name ? ` - ${goal.scorer_name}` : "";
  return element("p", "", `${score}${minute}${scorer}`);
}

function changeRow(change) {
  const row = element("div", "change");
  row.append(
    element(
      "p",
      "",
      `${change.field_name}: ${change.old_value ?? "empty"} -> ${change.new_value ?? "empty"}`,
    ),
    element("p", "muted", formatDate(change.observed_at_utc)),
  );
  return row;
}

function noteToken() {
  return document.querySelector("#notes-token")?.value.trim() ?? "";
}

async function archiveNote(noteId, matchId, statusNode) {
  const token = noteToken();
  if (!token) {
    setState(statusNode, "Enter the local note-write token first.", "error");
    return;
  }
  try {
    await request(`/api/notes/${noteId}`, {
      method: "DELETE",
      headers: { "X-Notes-Token": token },
    });
    await showMatch(matchId, false);
  } catch (error) {
    setState(statusNode, "The note could not be archived.", "error");
  }
}

async function editNote(note, matchId, statusNode) {
  const token = noteToken();
  if (!token) {
    setState(statusNode, "Enter the local note-write token first.", "error");
    return;
  }
  const updatedText = window.prompt("Update local note", note.note_text);
  if (updatedText === null) return;
  if (!updatedText.trim()) {
    setState(statusNode, "A note cannot be blank.", "error");
    return;
  }
  try {
    await request(`/api/notes/${note.note_id}`, {
      method: "PUT",
      headers: { "X-Notes-Token": token },
      body: JSON.stringify({ note_text: updatedText.trim() }),
    });
    await showMatch(matchId, false);
  } catch (error) {
    setState(statusNode, "The note could not be updated.", "error");
  }
}

function noteRow(note, matchId, statusNode) {
  const row = element("div", "change");
  row.append(
    element("p", "", note.note_text),
    element("p", "muted", `${note.created_by ?? "Local user"} - ${formatDate(note.updated_at_utc)}`),
  );
  if (applicationState.noteWritesEnabled) {
    const actions = element("div", "note-actions");
    const edit = element("button", "secondary compact", "Edit");
    const archive = element("button", "secondary compact", "Archive");
    edit.type = "button";
    archive.type = "button";
    edit.addEventListener("click", () => editNote(note, matchId, statusNode));
    archive.addEventListener("click", () => archiveNote(note.note_id, matchId, statusNode));
    actions.append(edit, archive);
    row.append(actions);
  }
  return row;
}

function noteEditor(matchId, statusNode) {
  const section = element("section", "note-editor");
  section.append(element("h3", "", "Add local note"));
  if (!applicationState.noteWritesEnabled) {
    section.append(element("p", "muted", "Note writes are disabled by local configuration."));
    return section;
  }
  const form = element("form", "note-form");
  const tokenLabel = element("label", "", "Local write token");
  const tokenInput = element("input", "");
  tokenInput.id = "notes-token";
  tokenInput.type = "password";
  tokenInput.autocomplete = "off";
  tokenInput.required = true;
  tokenLabel.append(tokenInput);
  const textLabel = element("label", "", "Note");
  const textInput = element("textarea", "");
  textInput.name = "note_text";
  textInput.maxLength = 4000;
  textInput.required = true;
  textLabel.append(textInput);
  const authorLabel = element("label", "", "Created by");
  const authorInput = element("input", "");
  authorInput.name = "created_by";
  authorInput.maxLength = 200;
  authorInput.value = "local-user";
  authorLabel.append(authorInput);
  const submit = element("button", "primary", "Add note");
  submit.type = "submit";
  form.append(tokenLabel, textLabel, authorLabel, submit);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const token = tokenInput.value.trim();
    const noteText = textInput.value.trim();
    const createdBy = authorInput.value.trim();
    if (!token || !noteText || !createdBy) {
      setState(statusNode, "Token, note, and author are required.", "error");
      return;
    }
    try {
      await request(`/api/matches/${matchId}/notes`, {
        method: "POST",
        headers: { "X-Notes-Token": token },
        body: JSON.stringify({ note_text: noteText, created_by: createdBy }),
      });
      await showMatch(matchId, false);
    } catch (error) {
      setState(statusNode, "The note could not be created.", "error");
    }
  });
  section.append(form);
  return section;
}

async function showMatch(matchId, openDialog = true) {
  matchDetail.replaceChildren(element("p", "status", "Loading details..."));
  if (openDialog && !dialog.open) dialog.showModal();
  try {
    const [match, changes, notes] = await Promise.all([
      request(`/api/matches/${matchId}`),
      request(`/api/matches/${matchId}/changes`),
      request(`/api/matches/${matchId}/notes`),
    ]);
    const heading = element("div", "");
    const title = element("h2", "", `${match.home_team} vs ${match.away_team}`);
    title.id = "dialog-title";
    heading.append(
      element("p", "eyebrow", `Provider match ${match.provider_match_id}`),
      title,
      element("p", "muted", formatDate(match.kickoff_utc)),
    );
    const noteStatus = element("p", "status");
    noteStatus.setAttribute("role", "status");
    noteStatus.setAttribute("aria-live", "polite");
    const grid = element("div", "detail-grid");
    const data = element("div", "");
    data.append(
      recordList("Results", match.results, resultRow),
      recordList("Goals", match.goals, goalRow),
    );
    const provenance = element("div", "");
    provenance.append(
      recordList("Observed changes", changes, changeRow),
      recordList("Local notes", notes, (note) => noteRow(note, matchId, noteStatus)),
      noteEditor(matchId, noteStatus),
      noteStatus,
    );
    grid.append(data, provenance);
    matchDetail.replaceChildren(heading, grid);
  } catch (error) {
    matchDetail.replaceChildren(element("p", "error", "Match details could not be loaded."));
  }
}

function importRunRow(run) {
  const row = element("div", "run");
  const heading = element("div", "run-heading");
  heading.append(element("strong", "", `Run ${run.import_run_id}`), element("span", "badge", run.status));
  const replay = run.is_replay ? " - replay" : "";
  row.append(
    heading,
    element("p", "muted", `${formatDate(run.started_at_utc)}${replay}`),
    element(
      "p",
      "",
      `${run.matches_seen ?? 0} seen - ${run.matches_inserted ?? 0} inserted - ${run.matches_updated ?? 0} updated`,
    ),
  );
  if (run.error_message) row.append(element("p", "error", run.error_message));
  return row;
}

function checkpointRow(checkpoint) {
  const row = element("div", "run");
  row.append(
    element("strong", "", `Matchday ${checkpoint.matchday_number ?? "scope"}`),
    element("p", "muted", checkpoint.scope_key),
    element("p", "", `Processed ${formatDate(checkpoint.last_processed_at_utc)}`),
    element(
      "p",
      "muted",
      `Import run ${checkpoint.last_successful_import_run_id ?? "not recorded"}`,
    ),
  );
  return row;
}

function issueRow(issue) {
  const row = element("div", "issue");
  row.append(
    element("strong", "", `${issue.severity}: ${issue.issue_code}`),
    element("p", "", issue.message),
    element("p", "muted", formatDate(issue.created_at_utc)),
  );
  return row;
}

function replaceRecordList(container, records, formatter) {
  container.replaceChildren(...records.map(formatter));
  if (records.length === 0) container.append(emptyTemplate.content.cloneNode(true));
}

async function loadOperations() {
  const status = document.querySelector("#operations-status");
  const runs = document.querySelector("#import-runs");
  const checkpoints = document.querySelector("#sync-checkpoints");
  const issues = document.querySelector("#validation-issues");
  setState(status, "Loading operational history...");
  runs.replaceChildren();
  checkpoints.replaceChildren();
  issues.replaceChildren();
  try {
    const [runData, checkpointData, issueData] = await Promise.all([
      request("/api/import-runs?limit=20"),
      request("/api/sync-checkpoints?limit=20"),
      request("/api/validation-issues?limit=20"),
    ]);
    replaceRecordList(runs, runData, importRunRow);
    replaceRecordList(checkpoints, checkpointData, checkpointRow);
    replaceRecordList(issues, issueData, issueRow);
    setState(status, "Operational history loaded.");
  } catch (error) {
    setState(status, "Operational history could not be loaded.", "error");
  }
}

filters.addEventListener("submit", (event) => {
  event.preventDefault();
  loadFixtures();
});

competitionSelect.addEventListener("change", async () => {
  await loadMatchdays();
  await loadFixtures();
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("is-active"));
    document.querySelectorAll(".panel").forEach((panel) => {
      panel.classList.remove("is-active");
      panel.hidden = true;
    });
    tab.classList.add("is-active");
    const panel = document.querySelector(`#${tab.dataset.panel}`);
    panel.classList.add("is-active");
    panel.hidden = false;
    if (tab.dataset.panel === "operations") loadOperations();
  });
});

document.querySelector("#refresh-operations").addEventListener("click", loadOperations);

async function initialize() {
  await Promise.all([checkHealth(), loadServiceStatus(), loadCompetitions()]);
  await loadMatchdays();
  await loadFixtures();
}

initialize();
