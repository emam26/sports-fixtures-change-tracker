const health = document.querySelector("#health");
const fixtureList = document.querySelector("#fixture-list");
const fixtureStatus = document.querySelector("#fixture-status");
const filters = document.querySelector("#filters");
const dialog = document.querySelector("#match-dialog");
const matchDetail = document.querySelector("#match-detail");
const emptyTemplate = document.querySelector("#empty-template");

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function formatDate(value) {
  if (!value) return "Time not supplied";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

async function request(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}

async function checkHealth() {
  try {
    await request("/health");
    health.textContent = "Database available";
    health.classList.add("ok");
  } catch (error) {
    health.textContent = "Database unavailable";
    health.classList.add("error");
  }
}

function scoreText(match) {
  if (match.home_score === null || match.away_score === null) return "—";
  return `${match.home_score}–${match.away_score}`;
}

function fixtureCard(match) {
  const card = element("article", "fixture-card");
  const meta = element("div", "fixture-meta");
  meta.append(
    element("span", "badge", match.is_finished ? "Finished" : "Upcoming"),
    element("span", "muted", `Matchday ${match.matchday_number ?? "—"}`),
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
  fixtureStatus.textContent = "Loading fixtures…";
  fixtureList.replaceChildren();
  const params = new URLSearchParams({ limit: "200" });
  const matchday = document.querySelector("#matchday").value;
  const finished = document.querySelector("#finished").value;
  const search = document.querySelector("#search").value.trim();
  if (matchday) params.set("matchday", matchday);
  if (finished) params.set("finished", finished);
  if (search) params.set("search", search);
  try {
    const page = await request(`/api/matches?${params}`);
    fixtureStatus.textContent = `${page.total} fixture${page.total === 1 ? "" : "s"}`;
    if (page.items.length === 0) {
      fixtureList.append(emptyTemplate.content.cloneNode(true));
      return;
    }
    page.items.forEach((match) => fixtureList.append(fixtureCard(match)));
  } catch (error) {
    fixtureStatus.textContent = "Fixtures could not be loaded.";
    fixtureStatus.classList.add("error");
  }
}

function recordList(title, records, formatter) {
  const section = element("section", "");
  section.append(element("h3", "", title));
  if (records.length === 0) {
    section.append(element("p", "muted", "No records."));
  } else {
    records.forEach((record) => section.append(formatter(record)));
  }
  return section;
}

function resultRow(result) {
  const row = element("p", "");
  row.textContent = `${result.result_type}: ${result.home_score}–${result.away_score}`;
  return row;
}

function goalRow(goal) {
  const scorer = goal.scorer_name ? ` · ${goal.scorer_name}` : "";
  return element(
    "p",
    "",
    `${goal.score_home}–${goal.score_away}${goal.minute ? ` · ${goal.minute}′` : ""}${scorer}`,
  );
}

function changeRow(change) {
  const row = element("div", "change");
  row.append(
    element("p", "", `${change.field_name}: ${change.old_value ?? "∅"} → ${change.new_value ?? "∅"}`),
    element("p", "muted", formatDate(change.observed_at_utc)),
  );
  return row;
}

function noteRow(note) {
  const row = element("div", "change");
  row.append(
    element("p", "", note.note_text),
    element("p", "muted", `${note.created_by} · ${formatDate(note.updated_at_utc)}`),
  );
  return row;
}

async function showMatch(matchId) {
  matchDetail.replaceChildren(element("p", "status", "Loading details…"));
  dialog.showModal();
  try {
    const [match, changes, notes] = await Promise.all([
      request(`/api/matches/${matchId}`),
      request(`/api/matches/${matchId}/changes`),
      request(`/api/matches/${matchId}/notes`),
    ]);
    const heading = element("div", "");
    const title = element("h2", "", `${match.home_team} · ${match.away_team}`);
    title.id = "dialog-title";
    heading.append(
      element("p", "eyebrow", `Provider match ${match.provider_match_id}`),
      title,
      element("p", "muted", formatDate(match.kickoff_utc)),
    );
    const grid = element("div", "detail-grid");
    const data = element("div", "");
    data.append(
      recordList("Results", match.results, resultRow),
      recordList("Goals", match.goals, goalRow),
    );
    const provenance = element("div", "");
    provenance.append(
      recordList("Observed changes", changes, changeRow),
      recordList("Local notes", notes, noteRow),
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
  row.append(
    heading,
    element("p", "muted", formatDate(run.started_at_utc)),
    element("p", "", `${run.matches_seen ?? 0} matches seen · ${run.matches_updated ?? 0} updated`),
  );
  if (run.error_message) row.append(element("p", "error", run.error_message));
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

async function loadOperations() {
  const runs = document.querySelector("#import-runs");
  const issues = document.querySelector("#validation-issues");
  runs.textContent = "Loading…";
  issues.textContent = "Loading…";
  try {
    const [runData, issueData] = await Promise.all([
      request("/api/import-runs?limit=20"),
      request("/api/validation-issues?limit=20"),
    ]);
    runs.replaceChildren(...runData.map(importRunRow));
    issues.replaceChildren(...issueData.map(issueRow));
    if (runData.length === 0) runs.append(emptyTemplate.content.cloneNode(true));
    if (issueData.length === 0) issues.append(emptyTemplate.content.cloneNode(true));
  } catch (error) {
    runs.textContent = "Operational history could not be loaded.";
    issues.textContent = "Validation issues could not be loaded.";
  }
}

filters.addEventListener("submit", (event) => {
  event.preventDefault();
  loadFixtures();
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

checkHealth();
loadFixtures();
