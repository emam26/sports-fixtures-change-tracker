const ui = {
  appAlert: document.querySelector("#app-alert"),
  health: document.querySelector("#health"),
  competitionContext: document.querySelector("#competition-context"),
  overviewStatus: document.querySelector("#overview-status"),
  lastUpdated: document.querySelector("#last-updated"),
  metricTotal: document.querySelector("#metric-total"),
  metricFinished: document.querySelector("#metric-finished"),
  metricUpcoming: document.querySelector("#metric-upcoming"),
  metricGoals: document.querySelector("#metric-goals"),
  metricChanges: document.querySelector("#metric-changes"),
  metricChangesDetail: document.querySelector("#metric-changes-detail"),
  filters: document.querySelector("#filters"),
  competitionSelect: document.querySelector("#competition"),
  matchdaySelect: document.querySelector("#matchday"),
  finishedSelect: document.querySelector("#finished"),
  sortSelect: document.querySelector("#fixture-sort"),
  searchInput: document.querySelector("#search"),
  fixtureStatus: document.querySelector("#fixture-status"),
  fixtureList: document.querySelector("#fixture-list"),
  changesStatus: document.querySelector("#changes-status"),
  changeList: document.querySelector("#change-list"),
  changePagination: document.querySelector("#change-pagination"),
  changePageDescription: document.querySelector("#change-page-description"),
  previousChangePage: document.querySelector("#change-page-previous"),
  nextChangePage: document.querySelector("#change-page-next"),
  dialog: document.querySelector("#match-dialog"),
  matchDetail: document.querySelector("#match-detail"),
};

const state = {
  competitions: [],
  detailRequestId: 0,
  changeOffset: 0,
  changePageSize: 25,
  changeRequestId: 0,
  fixturePage: null,
  fixtureRequestId: 0,
  fixturesLoading: false,
  matchdayRequestId: 0,
  noteWritesEnabled: false,
  overviewRequestId: 0,
};

const integerFormatter = new Intl.NumberFormat();

class ApiRequestError extends Error {
  constructor(message, status = null) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

function element(tag, { className = "", text, attributes = {} } = {}) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  Object.entries(attributes).forEach(([name, value]) => {
    node.setAttribute(name, String(value));
  });
  return node;
}

function setText(node, text) {
  if (node) node.textContent = text;
}

function setStatus(node, message, tone = "") {
  if (!node) return;
  node.textContent = message;
  node.dataset.tone = tone;
}

function setBusy(node, isBusy) {
  if (node) node.setAttribute("aria-busy", String(isBusy));
}

function showAppAlert(message) {
  if (!ui.appAlert) return;
  ui.appAlert.hidden = false;
  ui.appAlert.textContent = message;
}

function clearAppAlert() {
  if (!ui.appAlert) return;
  ui.appAlert.hidden = true;
  ui.appAlert.textContent = "";
}

function formatCount(value) {
  return integerFormatter.format(Number(value ?? 0));
}

function formatDate(value, fallback = "Not recorded") {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Invalid source time";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function valueOrNotSupplied(value) {
  if (value === null || value === undefined || value === "") return "Not supplied";
  return String(value);
}

function scoreText(homeScore, awayScore) {
  if (homeScore === null || homeScore === undefined) return "Not supplied";
  if (awayScore === null || awayScore === undefined) return "Not supplied";
  return `${homeScore}-${awayScore}`;
}

function compactHash(value) {
  if (!value) return "Hash not recorded";
  return value.length > 16 ? `${value.slice(0, 12)}...${value.slice(-4)}` : value;
}

function selectedCompetitionId() {
  const value = ui.competitionSelect?.value;
  return value ? Number(value) : null;
}

function selectedCompetition() {
  const competitionId = selectedCompetitionId();
  return state.competitions.find((item) => item.competition_season_id === competitionId) ?? null;
}

function apiPath(path, parameters = {}) {
  const search = new URLSearchParams();
  Object.entries(parameters).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  });
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

async function request(path, options = {}) {
  const headers = { Accept: "application/json", ...options.headers };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch {
    throw new ApiRequestError("The local API could not be reached.");
  }

  if (response.status === 204) return null;

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    if (response.ok) {
      throw new ApiRequestError("The local API returned an unreadable response.", response.status);
    }
  }

  if (!response.ok) {
    throw new ApiRequestError(`The local API returned HTTP ${response.status}.`, response.status);
  }
  return payload;
}

function contentState(title, detail, tone = "empty") {
  const container = element("div", { className: `content-state ${tone}-state` });
  container.append(element("strong", { text: title }), element("span", { text: detail }));
  return container;
}

function renderListState(container, title, detail, tone = "empty") {
  if (!container) return;
  container.replaceChildren(contentState(title, detail, tone));
  setBusy(container, false);
}

function statusClass(status) {
  const normalized = String(status ?? "unknown").toLowerCase();
  if (normalized === "succeeded" || normalized === "imported") return "is-success";
  if (normalized === "failed") return "is-danger";
  if (normalized === "skipped" || normalized === "started") return "is-neutral";
  return "is-neutral";
}

function statusPill(text) {
  return element("span", { className: `status-pill ${statusClass(text)}`, text: String(text) });
}

function sourcePill(match) {
  return statusPill(match.is_finished ? "Finished" : "Upcoming");
}

function describeRequestFailure(subject, error) {
  const suffix = error instanceof ApiRequestError && error.status ? ` (HTTP ${error.status})` : "";
  return `${subject} could not be loaded${suffix}. Check the local API and database service.`;
}

async function loadHealth() {
  setStatus(ui.health, "Checking availability...", "loading");
  try {
    await request("/health");
    setStatus(ui.health, "Database available", "ok");
  } catch {
    setStatus(ui.health, "Database unavailable", "error");
    showAppAlert("The database health check failed. The dashboard will show any data it can load.");
  }
}

async function loadServiceStatus() {
  try {
    const service = await request("/api/status");
    state.noteWritesEnabled = Boolean(service.note_writes_enabled);
  } catch {
    state.noteWritesEnabled = false;
  }
}

function renderCompetitionContext() {
  const competition = selectedCompetition();
  if (competition) {
    setText(ui.competitionContext, `${competition.name} / ${competition.season}`);
    return;
  }
  setText(ui.competitionContext, "All loaded competition seasons");
}

async function loadCompetitions() {
  const previous = ui.competitionSelect?.value ?? "";
  if (ui.competitionSelect) ui.competitionSelect.disabled = true;
  try {
    const competitions = await request("/api/competitions");
    state.competitions = competitions;
    ui.competitionSelect.replaceChildren(new Option("All loaded competition seasons", ""));
    competitions.forEach((competition) => {
      const label = `${competition.name} / ${competition.season}`;
      ui.competitionSelect.append(new Option(label, String(competition.competition_season_id)));
    });
    const availableValues = new Set([...ui.competitionSelect.options].map((option) => option.value));
    if (previous && availableValues.has(previous)) {
      ui.competitionSelect.value = previous;
    } else if (competitions.length === 1) {
      ui.competitionSelect.value = String(competitions[0].competition_season_id);
    }
    ui.competitionSelect.disabled = false;
    renderCompetitionContext();
    return true;
  } catch (error) {
    state.competitions = [];
    ui.competitionSelect.replaceChildren(new Option("Competition data unavailable", ""));
    ui.competitionSelect.disabled = true;
    renderCompetitionContext();
    showAppAlert(describeRequestFailure("Competition data", error));
    return false;
  }
}

async function loadMatchdays() {
  const requestId = ++state.matchdayRequestId;
  const previous = ui.matchdaySelect?.value ?? "";
  ui.matchdaySelect.disabled = true;
  try {
    const matchdays = await request(
      apiPath("/api/matchdays", { competition_season_id: selectedCompetitionId() }),
    );
    if (requestId !== state.matchdayRequestId) return false;
    ui.matchdaySelect.replaceChildren(new Option("All loaded matchdays", ""));
    matchdays.forEach((matchday) => {
      const completed = `${formatCount(matchday.finished_count)} finished`;
      const label = `Matchday ${matchday.matchday_number} / ${formatCount(
        matchday.match_count,
      )} fixtures / ${completed}`;
      ui.matchdaySelect.append(new Option(label, String(matchday.matchday_number)));
    });
    if ([...ui.matchdaySelect.options].some((option) => option.value === previous)) {
      ui.matchdaySelect.value = previous;
    }
    ui.matchdaySelect.disabled = false;
    return true;
  } catch (error) {
    if (requestId !== state.matchdayRequestId) return false;
    ui.matchdaySelect.replaceChildren(new Option("Matchday data unavailable", ""));
    ui.matchdaySelect.disabled = true;
    setStatus(ui.fixtureStatus, describeRequestFailure("Matchday data", error), "error");
    return false;
  }
}

function renderSummary(summary) {
  setText(ui.metricTotal, formatCount(summary.total_fixtures));
  setText(ui.metricFinished, formatCount(summary.finished_fixtures));
  setText(ui.metricUpcoming, formatCount(summary.upcoming_fixtures));
  setText(ui.metricGoals, formatCount(summary.goals_recorded));
  setText(ui.metricChanges, formatCount(summary.detected_changes));
  if (summary.changed_fixtures === null || summary.changed_fixtures === undefined) {
    setText(ui.metricChangesDetail, "Affected fixtures unavailable");
  } else {
    const label = Number(summary.changed_fixtures) === 1 ? "fixture" : "fixtures";
    setText(ui.metricChangesDetail, `Across ${formatCount(summary.changed_fixtures)} ${label}`);
  }

  const lastUpdated = ui.lastUpdated;
  lastUpdated.replaceChildren();
  lastUpdated.append(
    element("span", { className: "last-updated-label", text: "Last updated" }),
  );
  if (summary.latest_successful_sync_at_utc) {
    lastUpdated.append(
      element("strong", { text: formatDate(summary.latest_successful_sync_at_utc) }),
      element("span", {
        text: "Based on the latest successful synchronization recorded by the local database.",
      }),
    );
  } else {
    lastUpdated.append(
      element("strong", { text: "Not recorded" }),
      element("span", { text: "No completed synchronization is recorded for this selection." }),
    );
  }
}

async function loadOverview() {
  const requestId = ++state.overviewRequestId;
  setStatus(ui.overviewStatus, "Loading aggregate metrics from the local API...", "loading");
  try {
    const summary = await request(
      apiPath("/api/dashboard-summary", { competition_season_id: selectedCompetitionId() }),
    );
    if (requestId !== state.overviewRequestId) return;
    renderSummary(summary);
    setStatus(ui.overviewStatus, "Overview updated from current database records.", "ok");
  } catch (error) {
    if (requestId !== state.overviewRequestId) return;
    [ui.metricTotal, ui.metricFinished, ui.metricUpcoming, ui.metricGoals, ui.metricChanges].forEach(
      (node) => setText(node, "—"),
    );
    setText(ui.metricChangesDetail, "Affected fixtures unavailable");
    ui.lastUpdated.replaceChildren(
      element("span", { className: "last-updated-label", text: "Last updated" }),
      element("strong", { text: "Unavailable" }),
      element("span", { text: "The latest synchronization timestamp could not be loaded." }),
    );
    const message = describeRequestFailure("Overview metrics", error);
    setStatus(ui.overviewStatus, message, "error");
    showAppAlert(message);
  }
}

function sortFixtures(matches) {
  const direction = ui.sortSelect?.value === "kickoff-desc" ? -1 : 1;
  return [...matches].sort((left, right) => {
    const leftTime = left.kickoff_utc ? Date.parse(left.kickoff_utc) : Number.NaN;
    const rightTime = right.kickoff_utc ? Date.parse(right.kickoff_utc) : Number.NaN;
    const leftMissing = Number.isNaN(leftTime);
    const rightMissing = Number.isNaN(rightTime);
    if (leftMissing !== rightMissing) return leftMissing ? 1 : -1;
    if (leftMissing) return (Number(left.match_id) - Number(right.match_id)) * direction;
    if (leftTime !== rightTime) return (leftTime - rightTime) * direction;
    return (Number(left.match_id) - Number(right.match_id)) * direction;
  });
}

function fixtureCard(match) {
  const card = element("article", { className: "fixture-card" });
  const topLine = element("div", { className: "fixture-card-topline" });
  topLine.append(
    sourcePill(match),
    element("span", { className: "metadata", text: `Matchday ${valueOrNotSupplied(match.matchday_number)}` }),
  );

  const teamBlock = element("div", { className: "fixture-teams" });
  const score = element("strong", {
    className: "fixture-score",
    text: scoreText(match.home_score, match.away_score),
  });
  teamBlock.append(
    element("span", { className: "team-name", text: valueOrNotSupplied(match.home_team) }),
    score,
    element("span", { className: "team-name", text: valueOrNotSupplied(match.away_team) }),
  );

  const footer = element("div", { className: "fixture-footer" });
  const stage = match.stage_name ? `${match.stage_name} / ` : "";
  footer.append(
    element("p", { className: "fixture-time", text: `${stage}${formatDate(match.kickoff_utc)}` }),
    element("p", {
      className: "metadata",
      text: `Source updated ${formatDate(match.last_source_update_utc)}`,
    }),
  );
  const button = element("button", { className: "button button-card", text: "View match details" });
  button.type = "button";
  button.addEventListener("click", () => showMatch(match.match_id));
  card.append(topLine, teamBlock, footer, button);
  return card;
}

function renderFixturePage(page) {
  const matches = sortFixtures(page.items);
  ui.fixtureList.replaceChildren();
  if (matches.length === 0) {
    renderListState(
      ui.fixtureList,
      "No fixtures match these filters",
      "Change the filters or import a preserved source snapshot first.",
    );
  } else {
    matches.forEach((match) => ui.fixtureList.append(fixtureCard(match)));
    setBusy(ui.fixtureList, false);
  }
  const totalText = `${formatCount(page.total)} fixture${page.total === 1 ? "" : "s"}`;
  setStatus(ui.fixtureStatus, `${totalText} found. Ordered by kickoff.`, "ok");
}

async function loadFixtures() {
  const requestId = ++state.fixtureRequestId;
  state.fixturePage = null;
  state.fixturesLoading = true;
  setBusy(ui.fixtureList, true);
  setStatus(ui.fixtureStatus, "Loading fixtures...", "loading");
  ui.fixtureList.replaceChildren(contentState("Loading fixtures", "Querying the local fixture API.", "loading"));
  const parameters = {
    competition_season_id: selectedCompetitionId(),
    matchday: ui.matchdaySelect?.value || null,
    finished: ui.finishedSelect?.value || null,
    search: ui.searchInput?.value.trim() || null,
    limit: 200,
  };
  try {
    const page = await request(apiPath("/api/matches", parameters));
    if (requestId !== state.fixtureRequestId) return;
    state.fixturePage = page;
    renderFixturePage(page);
  } catch (error) {
    if (requestId !== state.fixtureRequestId) return;
    const message = describeRequestFailure("Fixtures", error);
    renderListState(ui.fixtureList, "Fixtures are unavailable", message, "error");
    setStatus(ui.fixtureStatus, message, "error");
    showAppAlert(message);
  } finally {
    if (requestId === state.fixtureRequestId) state.fixturesLoading = false;
  }
}

function changeCard(change) {
  const card = element("article", { className: "change-card" });
  const heading = element("div", { className: "change-heading" });
  heading.append(
    element("div", {
      className: "change-match",
      text: `${valueOrNotSupplied(change.home_team)} vs ${valueOrNotSupplied(change.away_team)}`,
    }),
    statusPill(change.change_kind),
  );
  const values = element("div", { className: "change-values" });
  const before = element("div", { className: "change-value" });
  before.append(
    element("span", { text: "Before" }),
    element("strong", { text: valueOrNotSupplied(change.old_value) }),
  );
  const after = element("div", { className: "change-value" });
  after.append(
    element("span", { text: "After" }),
    element("strong", { text: valueOrNotSupplied(change.new_value) }),
  );
  values.append(
    before,
    element("span", {
      className: "change-arrow",
      text: "->",
      attributes: { "aria-hidden": "true" },
    }),
    after,
  );

  const provenance = element("div", { className: "change-provenance" });
  provenance.append(
    element("span", { text: `Field: ${change.field_name}` }),
    element("span", { text: `Observed: ${formatDate(change.observed_at_utc)}` }),
    element("span", {
      text: `Snapshot ${change.source_snapshot_id} / ${compactHash(change.snapshot_sha256)}`,
    }),
    element("span", { text: `Captured: ${formatDate(change.snapshot_retrieved_at_utc)}` }),
  );
  const button = element("button", { className: "button button-quiet", text: "Open fixture" });
  button.type = "button";
  button.addEventListener("click", () => showMatch(change.match_id));
  card.append(heading, values, provenance, button);
  return card;
}

function renderChangePagination(total, itemCount) {
  if (!ui.changePagination) return;
  const hasRecords = total > 0;
  ui.changePagination.hidden = !hasRecords;
  if (!hasRecords) return;

  const first = state.changeOffset + 1;
  const last = Math.min(state.changeOffset + itemCount, total);
  setText(
    ui.changePageDescription,
    `Showing ${formatCount(first)}-${formatCount(last)} of ${formatCount(total)} observed changes.`,
  );
  ui.previousChangePage.disabled = state.changeOffset === 0;
  ui.nextChangePage.disabled = state.changeOffset + itemCount >= total;
}

async function loadChanges({ reset = false } = {}) {
  if (reset) state.changeOffset = 0;
  const requestId = ++state.changeRequestId;
  setBusy(ui.changeList, true);
  setStatus(ui.changesStatus, "Loading observed changes...", "loading");
  ui.changeList.replaceChildren(contentState("Loading change history", "Querying snapshot comparisons.", "loading"));
  try {
    const page = await request(
      apiPath("/api/match-changes", {
        competition_season_id: selectedCompetitionId(),
        limit: state.changePageSize,
        offset: state.changeOffset,
      }),
    );
    if (requestId !== state.changeRequestId) return;
    if (page.total > 0 && page.items.length === 0 && state.changeOffset >= page.total) {
      state.changeOffset = Math.floor((page.total - 1) / state.changePageSize) * state.changePageSize;
      await loadChanges();
      return;
    }
    ui.changeList.replaceChildren();
    if (page.items.length === 0) {
      renderListState(
        ui.changeList,
        "No observed fixture changes",
        "No field-level transitions have been recorded for this competition selection.",
      );
    } else {
      page.items.forEach((change) => ui.changeList.append(changeCard(change)));
      setBusy(ui.changeList, false);
    }
    renderChangePagination(page.total, page.items.length);
    setStatus(
      ui.changesStatus,
      `${formatCount(page.total)} recorded change${page.total === 1 ? "" : "s"}.`,
      "ok",
    );
  } catch (error) {
    if (requestId !== state.changeRequestId) return;
    const message = describeRequestFailure("Change intelligence", error);
    renderListState(ui.changeList, "Change history is unavailable", message, "error");
    ui.changePagination.hidden = true;
    setStatus(ui.changesStatus, message, "error");
    showAppAlert(message);
  }
}

function resultRow(result) {
  const row = element("li", { className: "detail-row" });
  row.append(
    element("strong", { text: result.result_type }),
    element("span", { text: result.result_name || "Source result type" }),
    element("span", { className: "detail-score", text: scoreText(result.home_score, result.away_score) }),
  );
  return row;
}

function goalRow(goal) {
  const row = element("li", { className: "detail-row goal-row" });
  const minute = goal.minute === null || goal.minute === undefined ? "Minute not supplied" : `${goal.minute}'`;
  const flags = [
    goal.is_penalty ? "penalty" : null,
    goal.is_own_goal ? "own goal" : null,
    goal.is_overtime ? "overtime" : null,
  ].filter(Boolean);
  row.append(
    element("strong", { text: valueOrNotSupplied(goal.scorer_name) }),
    element("span", { text: `${minute}${flags.length ? ` / ${flags.join(", ")}` : ""}` }),
    element("span", { className: "detail-score", text: scoreText(goal.score_home, goal.score_away) }),
  );
  return row;
}

function detailList(title, items, formatter, emptyMessage) {
  const section = element("section", { className: "detail-section" });
  section.append(element("h3", { text: title }));
  if (!items || items.length === 0) {
    section.append(element("p", { className: "metadata", text: emptyMessage }));
    return section;
  }
  const list = element("ul", { className: "detail-list" });
  items.forEach((item) => list.append(formatter(item)));
  section.append(list);
  return section;
}

function detailChangeRow(change) {
  const row = element("li", { className: "timeline-row" });
  row.append(
    element("strong", { text: change.field_name }),
    element("span", { text: `${valueOrNotSupplied(change.old_value)} -> ${valueOrNotSupplied(change.new_value)}` }),
    element("span", { className: "metadata", text: formatDate(change.observed_at_utc) }),
  );
  return row;
}

function noteToken() {
  return document.querySelector("#notes-token")?.value.trim() ?? "";
}

function createNoteStatus() {
  return element("p", {
    className: "note-status",
    attributes: { role: "status", "aria-live": "polite" },
  });
}

async function archiveNote(noteId, matchId, statusNode) {
  const token = noteToken();
  if (!token) {
    setStatus(statusNode, "Enter the local note-write token before archiving a note.", "error");
    return;
  }
  try {
    await request(`/api/notes/${noteId}`, {
      method: "DELETE",
      headers: { "X-Notes-Token": token },
    });
    await showMatch(matchId, false);
  } catch (error) {
    setStatus(statusNode, describeRequestFailure("The note", error), "error");
  }
}

function startNoteEdit(note, matchId, statusNode, row) {
  if (row.querySelector(".note-edit-form")) return;
  const form = element("form", { className: "note-edit-form" });
  const label = element("label", { text: "Edit local note" });
  const textInput = element("textarea", {
    attributes: { maxlength: "4000", required: "" },
  });
  textInput.value = note.note_text;
  label.append(textInput);
  const actions = element("div", { className: "note-actions" });
  const save = element("button", { className: "button button-primary", text: "Save note" });
  const cancel = element("button", { className: "button button-quiet", text: "Cancel" });
  save.type = "submit";
  cancel.type = "button";
  cancel.addEventListener("click", () => form.remove());
  actions.append(save, cancel);
  form.append(label, actions);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const token = noteToken();
    const updatedText = textInput.value.trim();
    if (!token) {
      setStatus(statusNode, "Enter the local note-write token before editing a note.", "error");
      return;
    }
    if (!updatedText) {
      setStatus(statusNode, "A note cannot be blank.", "error");
      return;
    }
    try {
      await request(`/api/notes/${note.note_id}`, {
        method: "PUT",
        headers: { "X-Notes-Token": token },
        body: JSON.stringify({ note_text: updatedText }),
      });
      await showMatch(matchId, false);
    } catch (error) {
      setStatus(statusNode, describeRequestFailure("The note", error), "error");
    }
  });
  row.append(form);
  textInput.focus();
}

function noteRow(note, matchId, statusNode) {
  const row = element("li", { className: "note-row" });
  row.append(
    element("p", { text: note.note_text }),
    element("span", {
      className: "metadata",
      text: `${note.created_by || "Local user"} / ${formatDate(note.updated_at_utc)}`,
    }),
  );
  if (state.noteWritesEnabled) {
    const actions = element("div", { className: "note-actions" });
    const edit = element("button", { className: "button button-quiet", text: "Edit" });
    const archive = element("button", { className: "button button-quiet", text: "Archive" });
    edit.type = "button";
    archive.type = "button";
    edit.addEventListener("click", () => startNoteEdit(note, matchId, statusNode, row));
    archive.addEventListener("click", () => archiveNote(note.note_id, matchId, statusNode));
    actions.append(edit, archive);
    row.append(actions);
  }
  return row;
}

function noteEditor(matchId, statusNode) {
  const section = element("section", { className: "detail-section note-editor" });
  section.append(element("h3", { text: "Local match notes" }));
  if (!state.noteWritesEnabled) {
    section.append(
      element("p", {
        className: "metadata",
        text: "Note writes are disabled by local configuration. Existing notes remain visible.",
      }),
    );
    return section;
  }

  const form = element("form", { className: "note-form" });
  const tokenLabel = element("label", { text: "Local note-write token" });
  const tokenInput = element("input", {
    attributes: {
      id: "notes-token",
      type: "password",
      autocomplete: "off",
      required: "",
    },
  });
  tokenLabel.append(tokenInput);
  const noteLabel = element("label", { text: "Note" });
  const noteInput = element("textarea", {
    attributes: { name: "note_text", maxlength: "4000", required: "" },
  });
  noteLabel.append(noteInput);
  const authorLabel = element("label", { text: "Created by" });
  const authorInput = element("input", {
    attributes: { name: "created_by", maxlength: "200", required: "", value: "local-user" },
  });
  authorLabel.append(authorInput);
  const submit = element("button", { className: "button button-primary", text: "Add local note" });
  submit.type = "submit";
  form.append(tokenLabel, noteLabel, authorLabel, submit);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const token = tokenInput.value.trim();
    const noteText = noteInput.value.trim();
    const createdBy = authorInput.value.trim();
    if (!token || !noteText || !createdBy) {
      setStatus(statusNode, "Token, note, and author are required.", "error");
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
      setStatus(statusNode, describeRequestFailure("The note", error), "error");
    }
  });
  section.append(form);
  return section;
}

function buildMatchDetail(match, changes, notes, issues) {
  const fragment = document.createDocumentFragment();
  const header = element("header", { className: "dialog-heading" });
  const title = element("h2", {
    text: `${match.home_team} vs ${match.away_team}`,
    attributes: { id: "dialog-title" },
  });
  header.append(
    element("p", {
      className: "eyebrow",
      text: `Provider match ${match.provider_match_id} / Matchday ${valueOrNotSupplied(match.matchday_number)}`,
    }),
    title,
    element("p", { className: "dialog-score", text: scoreText(match.home_score, match.away_score) }),
    element("p", { className: "metadata", text: `${formatDate(match.kickoff_utc)} / ${match.stage_name || "Stage not supplied"}` }),
    element("p", { className: "metadata", text: `Venue: ${valueOrNotSupplied(match.venue)}` }),
  );
  fragment.append(header);

  const columns = element("div", { className: "detail-grid" });
  const sporting = element("div", { className: "detail-column" });
  sporting.append(
    detailList(
      "Typed results",
      match.results,
      resultRow,
      "No result records were supplied by the source for this fixture.",
    ),
    detailList(
      "Goal events",
      match.goals,
      goalRow,
      "No goal events were supplied by the source for this fixture.",
    ),
  );

  const provenance = element("div", { className: "detail-column" });
  if (issues.changes) {
    provenance.append(detailList("Observed changes", [], () => element("li"), issues.changes));
  } else {
    provenance.append(
      detailList(
        "Observed changes",
        changes,
        detailChangeRow,
        "No field-level changes have been recorded for this fixture.",
      ),
    );
  }
  const noteStatus = createNoteStatus();
  if (issues.notes) {
    provenance.append(detailList("Local notes", [], () => element("li"), issues.notes));
  } else {
    provenance.append(
      detailList("Local notes", notes, (note) => noteRow(note, match.match_id, noteStatus), "No local notes."),
    );
  }
  provenance.append(noteEditor(match.match_id, noteStatus), noteStatus);
  columns.append(sporting, provenance);
  fragment.append(columns);
  return fragment;
}

async function showMatch(matchId, openDialog = true) {
  const requestId = ++state.detailRequestId;
  ui.matchDetail.replaceChildren(contentState("Loading match details", "Retrieving fixture, provenance, and notes.", "loading"));
  if (openDialog && !ui.dialog.open) {
    if (typeof ui.dialog.showModal === "function") {
      ui.dialog.showModal();
    } else {
      ui.dialog.setAttribute("open", "");
    }
  }

  try {
    const match = await request(`/api/matches/${matchId}`);
    const [changeResult, noteResult] = await Promise.allSettled([
      request(`/api/matches/${matchId}/changes`),
      request(`/api/matches/${matchId}/notes`),
    ]);
    if (requestId !== state.detailRequestId) return;
    const changes = changeResult.status === "fulfilled" ? changeResult.value : [];
    const notes = noteResult.status === "fulfilled" ? noteResult.value : [];
    const issues = {
      changes:
        changeResult.status === "rejected"
          ? describeRequestFailure("Change history", changeResult.reason)
          : null,
      notes:
        noteResult.status === "rejected" ? describeRequestFailure("Local notes", noteResult.reason) : null,
    };
    ui.matchDetail.replaceChildren(buildMatchDetail(match, changes, notes, issues));
  } catch (error) {
    if (requestId !== state.detailRequestId) return;
    ui.matchDetail.replaceChildren(
      contentState("Match details are unavailable", describeRequestFailure("Match details", error), "error"),
    );
  }
}

async function refreshDashboard() {
  clearAppAlert();
  const competitionsLoaded = await loadCompetitions();
  if (competitionsLoaded) await loadMatchdays();
  await Promise.all([
    loadHealth(),
    loadServiceStatus(),
    loadOverview(),
    loadFixtures(),
    loadChanges({ reset: true }),
  ]);
}

function clearFilters() {
  ui.competitionSelect.value = "";
  ui.matchdaySelect.value = "";
  ui.finishedSelect.value = "";
  ui.sortSelect.value = "kickoff-asc";
  ui.searchInput.value = "";
}

function attachEventListeners() {
  ui.filters.addEventListener("submit", (event) => {
    event.preventDefault();
    loadFixtures();
  });
  ui.competitionSelect.addEventListener("change", async () => {
    renderCompetitionContext();
    const matchdaysLoaded = await loadMatchdays();
    if (!matchdaysLoaded) return;
    await Promise.all([loadOverview(), loadFixtures(), loadChanges({ reset: true })]);
  });
  ui.sortSelect.addEventListener("change", () => {
    if (state.fixturePage) {
      renderFixturePage(state.fixturePage);
    } else if (!state.fixturesLoading) {
      void loadFixtures();
    }
  });
  document.querySelector("#clear-filters").addEventListener("click", async () => {
    clearFilters();
    renderCompetitionContext();
    const matchdaysLoaded = await loadMatchdays();
    if (!matchdaysLoaded) return;
    await Promise.all([loadOverview(), loadFixtures(), loadChanges({ reset: true })]);
  });
  document.querySelector("#refresh-dashboard").addEventListener("click", refreshDashboard);
  document.querySelector("#refresh-changes").addEventListener("click", loadChanges);
  ui.previousChangePage.addEventListener("click", async () => {
    if (ui.previousChangePage.disabled) return;
    state.changeOffset = Math.max(0, state.changeOffset - state.changePageSize);
    await loadChanges();
  });
  ui.nextChangePage.addEventListener("click", async () => {
    if (ui.nextChangePage.disabled) return;
    state.changeOffset += state.changePageSize;
    await loadChanges();
  });
}

function dashboardMarkupIsComplete() {
  return Object.values(ui).every(Boolean);
}

async function initialize() {
  if (!dashboardMarkupIsComplete()) {
    const fallback = element("p", {
      className: "app-alert",
      text: "Dashboard markup is incomplete. Reload the page after confirming the deployed assets match the application version.",
      attributes: { role: "alert" },
    });
    document.body.prepend(fallback);
    return;
  }
  attachEventListeners();
  await refreshDashboard();
}

window.addEventListener("error", () => {
  showAppAlert("The dashboard encountered a client-side error. Reload the page and check the browser console if it persists.");
});
window.addEventListener("unhandledrejection", () => {
  showAppAlert("The dashboard could not complete an asynchronous request. Check the visible panel errors and local API service.");
});

initialize().catch(() => {
  showAppAlert("The dashboard could not start. Reload the page after confirming the local API is running.");
});
