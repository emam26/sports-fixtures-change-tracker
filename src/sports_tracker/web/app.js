const ui = {
  appAlert: document.querySelector("#app-alert"),
  competitionContext: document.querySelector("#competition-context"),
  overviewStatus: document.querySelector("#overview-status"),
  lastUpdated: document.querySelector("#last-updated"),
  metricTotal: document.querySelector("#metric-total"),
  metricFinished: document.querySelector("#metric-finished"),
  metricUpcoming: document.querySelector("#metric-upcoming"),
  metricGoals: document.querySelector("#metric-goals"),
  metricChanges: document.querySelector("#metric-changes"),
  metricChangesDetail: document.querySelector("#metric-changes-detail"),
  upcomingStatus: document.querySelector("#upcoming-status"),
  upcomingList: document.querySelector("#upcoming-list"),
  insightsStatus: document.querySelector("#insights-status"),
  insightsSource: document.querySelector("#insights-source"),
  insightGoals: document.querySelector("#insight-goals"),
  insightAverageGoals: document.querySelector("#insight-average-goals"),
  insightResultSplit: document.querySelector("#insight-result-split"),
  insightGoalEvents: document.querySelector("#insight-goal-events"),
  insightGoalTrendSummary: document.querySelector("#insight-goal-trend-summary"),
  insightGoalTrend: document.querySelector("#insight-goal-trend"),
  insightGoalTrendTable: document.querySelector("#insight-goal-trend-table"),
  insightResultBars: document.querySelector("#insight-result-bars"),
  insightResultNote: document.querySelector("#insight-result-note"),
  insightMostGoals: document.querySelector("#insight-most-goals"),
  insightFewestConceded: document.querySelector("#insight-fewest-conceded"),
  insightTeamSearch: document.querySelector("#insight-team-search"),
  insightTeamSort: document.querySelector("#insight-team-sort"),
  insightTeamChart: document.querySelector("#insight-team-chart"),
  insightTeamBody: document.querySelector("#insight-team-body"),
  insightTeamDetail: document.querySelector("#insight-team-detail"),
  insightHighestScoring: document.querySelector("#insight-highest-scoring"),
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
  activeSectionId: "overview",
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
  upcomingRequestId: 0,
  insightsRequestId: 0,
  insightsTeamRequestId: 0,
  insightSummary: null,
  insightTeams: [],
  insightMatchdays: [],
  freshnessRevision: null,
  freshnessInitialized: false,
  freshnessCheckText: "Update check waiting.",
  freshnessPollTimer: null,
  freshnessRequestInFlight: false,
  freshnessRetryDelayMs: 60000,
  dashboardRefreshInFlight: false,
};

const integerFormatter = new Intl.NumberFormat();
const FRESHNESS_POLL_INTERVAL_MS = 60000;
const FRESHNESS_MAX_RETRY_DELAY_MS = 300000;

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

const DASHBOARD_SECTION_ORDER = [
  "overview",
  "match-explorer",
  "insights",
  "change-intelligence",
];

function orderDashboardSections() {
  const layout = document.querySelector(".dashboard-layout");
  if (!layout) return;
  DASHBOARD_SECTION_ORDER.forEach((sectionId) => {
    const section = document.getElementById(sectionId);
    if (section) layout.append(section);
  });
}

function setActiveSection(sectionId, links, sections) {
  if (!sections.some((section) => section.id === sectionId)) return;
  state.activeSectionId = sectionId;
  links.forEach((link) => {
    const isCurrent = link.getAttribute("href") === `#${sectionId}`;
    if (isCurrent) link.setAttribute("aria-current", "location");
    else link.removeAttribute("aria-current");
  });
}

function setupSectionNavigation() {
  const links = [...document.querySelectorAll('.section-nav a[href^="#"]')];
  const sections = DASHBOARD_SECTION_ORDER
    .map((sectionId) => document.getElementById(sectionId))
    .filter(Boolean);
  if (!links.length || !sections.length) return;

  const requestedSection = window.location.hash.slice(1);
  const initialSection = sections.some((section) => section.id === requestedSection)
    ? requestedSection
    : sections[0].id;
  setActiveSection(initialSection, links, sections);
  window.addEventListener("hashchange", () => {
    setActiveSection(window.location.hash.slice(1), links, sections);
  });

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => left.boundingClientRect.top - right.boundingClientRect.top)[0];
        if (visible) setActiveSection(visible.target.id, links, sections);
      },
      { rootMargin: "-18% 0px -68% 0px", threshold: 0 },
    );
    sections.forEach((section) => observer.observe(section));
  }
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
  return `${homeScore} \u2013 ${awayScore}`;
}

function resultTypeLabel(resultType) {
  const normalized = String(resultType ?? "").toLowerCase();
  if (normalized === "after90minutes") return "Final score";
  if (normalized === "halftime") return "Half-time score";
  return "Result";
}

const MATCH_FIELD_LABELS = {
  away_team_id: "Away team",
  competition_stage: "Competition stage",
  home_team_id: "Home team",
  kickoff_utc: "Kickoff time",
  location: "Venue",
  matchday_number: "Matchday",
  source_group_id: "Group reference",
  source_group_name: "Group name",
  source_group_order_id: "Group order",
  source_last_update_raw: "Source update value",
  source_last_update_utc: "Source update time",
  source_match_is_finished: "Match status",
  source_time_zone_id: "Source time zone",
};

const RESULT_FIELD_LABELS = {
  points_team1: "Home score",
  points_team2: "Away score",
  result_description: "Result description",
  result_name: "Result label",
  result_order_id: "Result order",
  result_type_id: "Result type reference",
  result_type_kind: "Score stage",
};

const GOAL_FIELD_LABELS = {
  comment: "Source comment",
  goal_getter_name: "Scorer",
  goal_getter_provider_id: "Scorer reference",
  is_overtime: "Overtime",
  is_own_goal: "Own goal",
  is_penalty: "Penalty",
  match_minute: "Match minute",
  score_team1: "Home score",
  score_team2: "Away score",
  scoring_team_id: "Scoring team reference",
};

const CHANGE_FIELD_LABELS = {
  goal: GOAL_FIELD_LABELS,
  match: MATCH_FIELD_LABELS,
  result: RESULT_FIELD_LABELS,
};

function parseChangeField(fieldName) {
  const parts = String(fieldName ?? "").split(".");
  if ((parts[0] === "goal" || parts[0] === "result") && parts.length >= 3) {
    return {
      recordId: parts[1],
      scope: parts[0],
      key: parts.slice(2).join("."),
    };
  }
  return { recordId: null, scope: "match", key: String(fieldName ?? "") };
}

function normalizeChangeKind(changeKind) {
  const normalized = String(changeKind ?? "Updated").toLowerCase();
  if (normalized === "inserted" || normalized === "updated" || normalized === "removed") {
    return normalized;
  }
  return "updated";
}

function changeKindLabel(changeKind) {
  const labels = {
    inserted: "Inserted",
    removed: "Removed",
    updated: "Updated",
  };
  return labels[normalizeChangeKind(changeKind)];
}

function changeKindPill(changeKind) {
  const normalized = normalizeChangeKind(changeKind);
  return element("span", {
    className: `status-pill change-kind-${normalized}`,
    text: changeKindLabel(normalized),
  });
}

function isTrue(value) {
  return String(value).toLowerCase() === "true";
}

function isFalse(value) {
  return String(value).toLowerCase() === "false";
}

function looksLikeTimezoneAwareTimestamp(value) {
  return /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/i.test(String(value));
}

function formatChangeValue(value, descriptor) {
  if (value === null || value === undefined || value === "") return "Not supplied";
  const text = String(value);
  if (descriptor.key === "source_match_is_finished") {
    if (isTrue(text)) return "Finished";
    if (isFalse(text)) return "Not finished";
  }
  if (descriptor.key === "result_type_kind") return resultTypeLabel(text);
  if (isTrue(text)) return "Yes";
  if (isFalse(text)) return "No";
  if (descriptor.key === "match_minute" && /^\d+$/.test(text)) return `${text}'`;
  if (
    (descriptor.key === "kickoff_utc" || descriptor.key === "source_last_update_utc") &&
    looksLikeTimezoneAwareTimestamp(text)
  ) {
    return formatDate(text);
  }
  return text;
}

function changeFieldLabel(descriptor) {
  return CHANGE_FIELD_LABELS[descriptor.scope]?.[descriptor.key] ?? "Additional detail";
}

function groupChangeEvents(changes) {
  const groups = new Map();
  changes.forEach((change) => {
    const descriptor = parseChangeField(change.field_name);
    const key = [
      descriptor.scope,
      descriptor.recordId ?? "fixture",
      normalizeChangeKind(change.change_kind),
      change.observed_at_utc,
      change.source_snapshot_id,
      change.import_run_id,
    ].join("|");
    const existing = groups.get(key);
    if (existing) {
      existing.changes.push({ change, descriptor });
      return;
    }
    groups.set(key, {
      changes: [{ change, descriptor }],
      kind: normalizeChangeKind(change.change_kind),
      scope: descriptor.scope,
    });
  });
  return [...groups.values()];
}

function groupHasField(group, fields) {
  return group.changes.some(({ descriptor }) => fields.includes(descriptor.key));
}

function groupResultTypeLooksFinal(group) {
  return group.changes.some(({ change, descriptor }) => {
    if (descriptor.key !== "result_type_kind") return false;
    return [change.old_value, change.new_value].some((value) =>
      /after90minutes/i.test(String(value ?? "")),
    );
  });
}

function changeEventSummary(group) {
  const scoresChanged = groupHasField(group, ["points_team1", "points_team2"]);
  if (group.scope === "match") {
    const statusChange = group.changes.find(
      ({ descriptor }) => descriptor.key === "source_match_is_finished",
    );
    if (statusChange) {
      if (group.kind === "inserted") return "Match status recorded";
      if (group.kind === "removed") return "Match status removed";
      if (isFalse(statusChange.change.old_value) && isTrue(statusChange.change.new_value)) {
        return "Match completed";
      }
      if (isTrue(statusChange.change.old_value) && isFalse(statusChange.change.new_value)) {
        return "Match marked unfinished";
      }
      return "Match status changed";
    }
    if (groupHasField(group, ["kickoff_utc"])) {
      return group.kind === "inserted"
        ? "Kickoff time recorded"
        : group.kind === "removed"
          ? "Kickoff time removed"
          : "Kickoff time changed";
    }
    if (groupHasField(group, ["location"])) {
      return group.kind === "inserted"
        ? "Venue recorded"
        : group.kind === "removed"
          ? "Venue removed"
          : "Venue changed";
    }
    return `Fixture information ${changeKindLabel(group.kind).toLowerCase()}`;
  }
  if (group.scope === "result") {
    if (groupResultTypeLooksFinal(group) && scoresChanged) {
      if (group.kind === "inserted") return "Final score recorded";
      if (group.kind === "removed") return "Final score removed";
      return "Final score updated";
    }
    if (scoresChanged) {
      if (group.kind === "inserted") return "Result score recorded";
      if (group.kind === "removed") return "Result score removed";
      return "Result score updated";
    }
    if (group.kind === "inserted") return "Result information added";
    if (group.kind === "removed") return "Result information removed";
    return "Result information updated";
  }
  if (group.scope === "goal") {
    if (group.kind === "inserted") return "Goal event added";
    if (group.kind === "removed") return "Goal event removed";
    return "Goal event updated";
  }
  return `Match information ${changeKindLabel(group.kind).toLowerCase()}`;
}

function changeScopeLabel(scope) {
  if (scope === "goal") return "goal detail";
  if (scope === "result") return "result detail";
  return "fixture detail";
}

function changeEventDescription(group) {
  const count = group.changes.length;
  const scope = changeScopeLabel(group.scope);
  const action = changeKindLabel(group.kind).toLowerCase();
  return `${formatCount(count)} ${scope}${count === 1 ? "" : "s"} ${action}.`;
}

function changeEventProvenance(group) {
  const { change } = group.changes[0];
  const provenance = element("div", { className: "change-event-provenance" });
  const snapshot = change.snapshot_sha256
    ? `Snapshot ${change.source_snapshot_id} / ${compactHash(change.snapshot_sha256)}`
    : `Snapshot ${change.source_snapshot_id}`;
  provenance.append(
    element("span", {
      text: `Observed in source snapshot: ${formatDate(change.observed_at_utc)}`,
    }),
    element("span", { text: snapshot }),
    element("span", { text: `Import run ${change.import_run_id}` }),
  );
  if (change.snapshot_retrieved_at_utc) {
    provenance.append(
      element("span", {
        text: `Captured: ${formatDate(change.snapshot_retrieved_at_utc)}`,
      }),
    );
  }
  if (change.source_last_update_utc) {
    provenance.append(
      element("span", {
        text: `Provider update: ${formatDate(change.source_last_update_utc)}`,
      }),
    );
  }
  return provenance;
}

function changeFieldValues(change, descriptor, changeKind) {
  const values = element("div", { className: "change-field-values" });
  if (changeKind === "inserted") {
    values.append(
      element("span", { className: "change-value-label", text: "Recorded" }),
      element("strong", { text: formatChangeValue(change.new_value, descriptor) }),
    );
    return values;
  }
  if (changeKind === "removed") {
    values.append(
      element("span", { className: "change-value-label", text: "Previous value" }),
      element("strong", { text: formatChangeValue(change.old_value, descriptor) }),
    );
    return values;
  }
  values.classList.add("is-comparison");
  const before = element("div", { className: "change-field-value" });
  before.append(
    element("span", { className: "change-value-label", text: "Previous" }),
    element("strong", { text: formatChangeValue(change.old_value, descriptor) }),
  );
  const after = element("div", { className: "change-field-value" });
  after.append(
    element("span", { className: "change-value-label", text: "Current" }),
    element("strong", { text: formatChangeValue(change.new_value, descriptor) }),
  );
  values.append(
    before,
    element("span", {
      className: "change-arrow",
      text: "→",
      attributes: { "aria-hidden": "true" },
    }),
    after,
  );
  return values;
}

function changeFieldDetails(group) {
  const details = element("details", { className: "change-field-details" });
  const count = group.changes.length;
  details.append(
    element("summary", {
      text: `Show ${formatCount(count)} change ${count === 1 ? "detail" : "details"}`,
    }),
  );
  const list = element("ul", { className: "change-field-list" });
  group.changes.forEach(({ change, descriptor }) => {
    const row = element("li", { className: "change-field-row" });
    row.append(
      element("strong", {
        className: "change-field-label",
        text: changeFieldLabel(descriptor),
      }),
      changeFieldValues(change, descriptor, group.kind),
    );
    list.append(row);
  });
  details.append(list);
  return details;
}

function changeEvent(group, match = null) {
  const event = element("article", { className: "change-event" });
  const header = element("div", { className: "change-event-header" });
  const title = element("div", { className: "change-event-title" });
  if (match) {
    title.append(
      element("p", {
        className: "change-match",
        text: `${valueOrNotSupplied(match.home_team)} vs ${valueOrNotSupplied(match.away_team)}`,
      }),
    );
  }
  title.append(element("h4", { text: changeEventSummary(group) }));
  header.append(title, changeKindPill(group.kind));
  event.append(
    header,
    element("p", { className: "change-event-description", text: changeEventDescription(group) }),
    changeEventProvenance(group),
    changeFieldDetails(group),
  );
  return event;
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
    throw new ApiRequestError("The local dashboard service could not be reached.");
  }

  if (response.status === 204) return null;

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    if (response.ok) {
      throw new ApiRequestError("The local dashboard service returned an unreadable response.", response.status);
    }
  }

  if (!response.ok) {
    throw new ApiRequestError(`The local dashboard service returned HTTP ${response.status}.`, response.status);
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
  if (normalized === "succeeded" || normalized === "imported" || normalized === "completed") {
    return "is-success";
  }
  if (normalized === "failed") return "is-danger";
  if (normalized === "skipped" || normalized === "started") return "is-neutral";
  return "is-neutral";
}

function statusPill(text) {
  return element("span", { className: `status-pill ${statusClass(text)}`, text: String(text) });
}

function sourcePill(match) {
  return statusPill(match.is_finished ? "Completed" : "Upcoming");
}

function describeRequestFailure(subject, error) {
  const suffix = error instanceof ApiRequestError && error.status ? ` (HTTP ${error.status})` : "";
  return `${subject} could not be loaded${suffix}. Check the local dashboard service and try again.`;
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

  renderLastUpdated(summary.latest_successful_sync_at_utc);
}

function renderLastUpdated(timestamp, fallback = null) {
  if (!ui.lastUpdated) return;
  ui.lastUpdated.replaceChildren(
    element("span", { className: "last-updated-label", text: "Last updated" }),
    element("strong", { text: timestamp ? formatDate(timestamp) : fallback || "Not recorded" }),
    element("small", { className: "freshness-check", text: state.freshnessCheckText }),
  );
}

function renderFreshnessCheck(text) {
  state.freshnessCheckText = text;
  const node = ui.lastUpdated?.querySelector(".freshness-check");
  if (node) node.textContent = text;
}

function updateLastUpdatedTimestamp(timestamp) {
  const node = ui.lastUpdated?.querySelector("strong");
  if (node) node.textContent = timestamp ? formatDate(timestamp) : "Not recorded";
}

async function loadOverview() {
  const requestId = ++state.overviewRequestId;
  setStatus(ui.overviewStatus, "Loading the competition summary...", "loading");
  try {
    const summary = await request(
      apiPath("/api/dashboard-summary", { competition_season_id: selectedCompetitionId() }),
    );
    if (requestId !== state.overviewRequestId) return;
    renderSummary(summary);
    setStatus(ui.overviewStatus, "", "ok");
  } catch (error) {
    if (requestId !== state.overviewRequestId) return;
    [ui.metricTotal, ui.metricFinished, ui.metricUpcoming, ui.metricGoals, ui.metricChanges].forEach(
      (node) => setText(node, "—"),
    );
    setText(ui.metricChangesDetail, "Affected fixtures unavailable");
    renderLastUpdated(null, "Unavailable");
    renderFreshnessCheck("Update check paused until the local dashboard service responds.");
    const message = describeRequestFailure("Overview metrics", error);
    setStatus(ui.overviewStatus, message, "error");
    showAppAlert(message);
  }
}

function formatAverage(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(2);
}

function renderInsightSummary(summary) {
  setText(
    ui.insightsSource,
    `Local fixture data / Last updated: ${formatDate(summary.latest_successful_sync_at_utc, "Not recorded")}`,
  );
  setText(ui.insightGoals, formatCount(summary.full_time_goals));
  setText(
    ui.insightAverageGoals,
    formatAverage(summary.average_full_time_goals_per_completed_match),
  );
  setText(
    ui.insightResultSplit,
    `${formatCount(summary.home_wins)} / ${formatCount(summary.draws)} / ${formatCount(summary.away_wins)}`,
  );
  setText(ui.insightGoalEvents, formatCount(summary.observed_goal_events));
  const validCount = formatCount(summary.completed_matches_with_valid_final_score);
  setText(ui.insightResultNote, `${validCount} completed matches with valid final scores.`);
  const leaderText = (leaders, suffix) => {
    if (!leaders?.length) return "No valid completed matches";
    return leaders
      .slice(0, 2)
      .map(
        (leader) =>
          `${leader.team_name} (${formatCount(leader.value)} ${suffix}, ${formatCount(leader.matches_played)} matches)`,
      )
      .join(" · ");
  };
  setText(ui.insightMostGoals, leaderText(summary.most_goals_teams, "goals"));
  setText(ui.insightFewestConceded, leaderText(summary.fewest_conceded_teams, "conceded"));

  ui.insightHighestScoring.replaceChildren();
  if (!summary.highest_scoring_matches?.length) {
    renderListState(
      ui.insightHighestScoring,
      "No completed scorelines yet",
      "Highest-scoring matches will appear after valid final results are available.",
    );
  } else {
    summary.highest_scoring_matches.forEach((match) => {
      const item = element("article", { className: "highest-scoring-item" });
      const identity = element("div", { className: "highest-scoring-identity" });
      identity.append(
        element("strong", { text: `${match.home_team} vs ${match.away_team}` }),
        element("span", {
          className: "metadata",
          text: `Matchday ${valueOrNotSupplied(match.matchday_number)} / ${formatDate(match.kickoff_utc, "Kickoff not recorded")}`,
        }),
      );
      const score = element("strong", {
        className: "highest-scoring-score",
        text: `${match.home_score}-${match.away_score}`,
      });
      const button = element("button", {
        className: "button button-quiet",
        text: "View match",
        attributes: { type: "button" },
      });
      button.addEventListener("click", () => showMatch(match.match_id));
      item.append(identity, score, button);
      ui.insightHighestScoring.append(item);
    });
  }
}

function renderInsightGoalTrend(matchdays) {
  ui.insightGoalTrend.replaceChildren();
  ui.insightGoalTrendTable.replaceChildren();
  const available = matchdays.filter((item) => item.completed_matches_with_valid_final_score > 0);
  if (!available.length) {
    renderListState(
      ui.insightGoalTrend,
      "No goal trend yet",
      "A trend requires at least one completed fixture with a valid final score.",
    );
    setText(ui.insightGoalTrendSummary, "No valid completed matchdays");
    return;
  }
  const maxGoals = Math.max(...available.map((item) => Number(item.full_time_goals)), 1);
  const totalGoals = available.reduce((total, item) => total + Number(item.full_time_goals), 0);
  setText(ui.insightGoalTrendSummary, `${formatCount(totalGoals)} goals across ${formatCount(available.length)} matchdays`);
  available.forEach((item) => {
    const matchdayLabel =
      item.matchday_number === null ? "Unassigned matchday" : `Matchday ${item.matchday_number}`;
    const bar = element("button", {
      className: "chart-column",
      attributes: {
        type: "button",
        "aria-label": `${matchdayLabel}: ${formatCount(item.full_time_goals)} full-time goals`,
      },
    });
    if (item.matchday_number !== null) {
      bar.addEventListener("click", () => {
        ui.matchdaySelect.value = String(item.matchday_number);
        void loadFixtures();
        document.querySelector("#match-explorer")?.scrollIntoView({ behavior: "smooth" });
      });
    } else {
      bar.disabled = true;
    }
    const value = Number(item.full_time_goals);
    const fill = element("div", { className: "chart-bar-fill" });
    fill.style.setProperty("--bar-size", `${Math.max((value / maxGoals) * 100, 4)}%`);
    bar.append(
      element("div", { className: "chart-bar-track", attributes: { "aria-hidden": "true" } }),
      element("span", { className: "chart-column-value", text: formatCount(value) }),
      element("span", {
        className: "chart-column-label",
        text: item.matchday_number === null ? "Unassigned" : `MD ${item.matchday_number}`,
      }),
    );
    bar.querySelector(".chart-bar-track").append(fill);
    ui.insightGoalTrend.append(bar);
    const row = element("div", { className: "chart-data-row" });
    row.append(
      element("span", {
        text: item.matchday_number === null ? "Unassigned matchday" : `Matchday ${item.matchday_number}`,
      }),
      element("strong", { text: `${formatCount(value)} goals` }),
      element("span", {
        className: "metadata",
        text: `${formatCount(item.completed_matches_with_valid_final_score)} completed`,
      }),
    );
    ui.insightGoalTrendTable.append(row);
  });
}

function renderInsightResultBars(summary) {
  ui.insightResultBars.replaceChildren();
  const values = [
    { label: "Home wins", value: Number(summary.home_wins), className: "result-home" },
    { label: "Draws", value: Number(summary.draws), className: "result-draw" },
    { label: "Away wins", value: Number(summary.away_wins), className: "result-away" },
  ];
  const maximum = Math.max(...values.map((item) => item.value), 1);
  values.forEach((item) => {
    const row = element("div", { className: "result-bar-row" });
    const track = element("div", { className: "result-bar-track" });
    const fill = element("span", { className: `result-bar-fill ${item.className}` });
    fill.style.setProperty("--bar-size", `${Math.max((item.value / maximum) * 100, item.value ? 7 : 0)}%`);
    track.append(fill);
    row.append(
      element("span", { className: "result-bar-label", text: item.label }),
      track,
      element("strong", { text: formatCount(item.value) }),
    );
    ui.insightResultBars.append(row);
  });
}

function sortedInsightTeams() {
  const query = ui.insightTeamSearch.value.trim().toLocaleLowerCase();
  const sort = ui.insightTeamSort.value;
  return state.insightTeams
    .filter((team) => team.team_name.toLocaleLowerCase().includes(query))
    .sort((left, right) => {
      if (sort === "goals") return right.goals_for - left.goals_for || left.team_name.localeCompare(right.team_name);
      if (sort === "defence") return left.goals_against - right.goals_against || right.points - left.points;
      if (sort === "name") return left.team_name.localeCompare(right.team_name);
      return right.points - left.points || right.goal_difference - left.goal_difference || left.team_name.localeCompare(right.team_name);
    });
}

function renderInsightTeamChart(teams) {
  ui.insightTeamChart.replaceChildren();
  if (!teams.length) {
    renderListState(ui.insightTeamChart, "No teams match", "Try a different team search.");
    return;
  }
  const displayed = teams.slice(0, 8);
  const maximum = Math.max(...displayed.map((team) => Number(team.points)), 1);
  displayed.forEach((team) => {
    const row = element("div", { className: "team-chart-row" });
    const fill = element("span", { className: "team-chart-fill" });
    fill.style.setProperty("--bar-size", `${Math.max((team.points / maximum) * 100, team.points ? 7 : 0)}%`);
    row.append(
      element("span", { className: "team-chart-label", text: team.team_name }),
      element("span", { className: "team-chart-track", attributes: { "aria-hidden": "true" } }),
      element("strong", { text: `${formatCount(team.points)} pts` }),
    );
    row.querySelector(".team-chart-track").append(fill);
    ui.insightTeamChart.append(row);
  });
}

function renderInsightTeams() {
  const teams = sortedInsightTeams();
  renderInsightTeamChart(teams);
  ui.insightTeamBody.replaceChildren();
  if (!teams.length) {
    const row = element("tr");
    const cell = element("td", {
      text: "No team records match this search.",
      attributes: { colspan: "8" },
    });
    row.append(cell);
    ui.insightTeamBody.append(row);
    return;
  }
  teams.forEach((team) => {
    const row = element("tr");
    const button = element("button", {
      className: "table-link",
      text: team.team_name,
      attributes: { type: "button" },
    });
    button.addEventListener("click", () => loadInsightTeam(team.provider_team_id));
    const cells = [
      button,
      String(team.played),
      `${team.won}-${team.drawn}-${team.lost}`,
      `${team.goals_for}-${team.goals_against}`,
      String(team.goal_difference),
      String(team.points),
      String(team.clean_sheets),
    ];
    cells.forEach((content, index) => {
      const cell = element("td");
      if (index === 0) cell.append(content);
      else cell.textContent = content;
      row.append(cell);
    });
    const detailCell = element("td");
    detailCell.append(
      element("span", { className: "metadata", text: "Open" }),
    );
    row.append(detailCell);
    ui.insightTeamBody.append(row);
  });
}

function renderInsightTeamDetail(team) {
  ui.insightTeamDetail.replaceChildren();
  const heading = element("div", { className: "team-detail-heading" });
  heading.append(
    element("h4", { text: team.team_name }),
    element("span", { className: "metadata", text: `Recent form: ${team.recent_form.length ? team.recent_form.join(" · ") : "Not available"}` }),
  );
  ui.insightTeamDetail.append(heading);
  if (!team.recent_matches.length) {
    ui.insightTeamDetail.append(
      contentState("No recent completed results", "This team has no valid completed scorelines in the selected data."),
    );
    return;
  }
  const list = element("div", { className: "team-recent-list" });
  team.recent_matches.forEach((match) => {
    const item = element("div", { className: "team-recent-item" });
    item.append(
      statusPill(match.outcome),
      element("span", { text: `${match.home_team} ${match.team_score}-${match.opponent_score} ${match.away_team}` }),
      element("span", { className: "metadata", text: formatDate(match.kickoff_utc, "Kickoff not recorded") }),
    );
    list.append(item);
  });
  ui.insightTeamDetail.append(list);
}

async function loadInsightTeam(teamId) {
  const requestId = ++state.insightsTeamRequestId;
  ui.insightTeamDetail.replaceChildren(
    contentState("Loading team detail", "Retrieving recent completed results.", "loading"),
  );
  try {
    const team = await request(
      apiPath(`/api/insights/teams/${teamId}`, { competition_season_id: selectedCompetitionId() }),
    );
    if (requestId !== state.insightsTeamRequestId) return;
    renderInsightTeamDetail(team);
  } catch (error) {
    if (requestId !== state.insightsTeamRequestId) return;
    renderListState(
      ui.insightTeamDetail,
      "Team detail is unavailable",
      describeRequestFailure("Team detail", error),
      "error",
    );
  }
}

function renderInsightSummaryUnavailable(error) {
  [
    ui.insightGoals,
    ui.insightAverageGoals,
    ui.insightResultSplit,
    ui.insightGoalEvents,
    ui.insightResultNote,
    ui.insightMostGoals,
    ui.insightFewestConceded,
  ].forEach((node) => setText(node, "—"));
  setText(ui.insightsSource, "Fixture data unavailable / Last updated: unavailable");
  ui.insightResultBars.replaceChildren();
  renderListState(
    ui.insightHighestScoring,
    "Insights summary unavailable",
    describeRequestFailure("Insights summary", error),
    "error",
  );
}

function renderInsightGoalTrendUnavailable(error) {
  ui.insightGoalTrendTable.replaceChildren();
  setText(ui.insightGoalTrendSummary, "Unavailable");
  renderListState(
    ui.insightGoalTrend,
    "Matchday trend unavailable",
    describeRequestFailure("Matchday trend", error),
    "error",
  );
}

function renderInsightTeamsUnavailable(error) {
  renderListState(
    ui.insightTeamChart,
    "Team insights unavailable",
    describeRequestFailure("Team insights", error),
    "error",
  );
  ui.insightTeamBody.replaceChildren();
  const row = element("tr");
  row.append(
    element("td", {
      text: "Team insights are unavailable.",
      attributes: { colspan: "8" },
    }),
  );
  ui.insightTeamBody.append(row);
}

async function loadInsights() {
  const requestId = ++state.insightsRequestId;
  setStatus(ui.insightsStatus, "Loading analytical summaries...", "loading");
  const parameters = { competition_season_id: selectedCompetitionId() };
  const results = await Promise.allSettled([
    request(apiPath("/api/insights/summary", parameters)),
    request(apiPath("/api/insights/teams", parameters)),
    request(apiPath("/api/insights/matchdays", parameters)),
  ]);
  if (requestId !== state.insightsRequestId) return;

  const [summaryResult, teamsResult, matchdaysResult] = results;
  const summaryAvailable = summaryResult.status === "fulfilled";
  const teamsAvailable = teamsResult.status === "fulfilled";
  const matchdaysAvailable = matchdaysResult.status === "fulfilled";
  state.insightSummary = summaryAvailable ? summaryResult.value : null;
  state.insightTeams = teamsAvailable ? teamsResult.value : [];
  state.insightMatchdays = matchdaysAvailable ? matchdaysResult.value : [];

  if (summaryAvailable) {
    renderInsightSummary(state.insightSummary);
    renderInsightResultBars(state.insightSummary);
  } else {
    renderInsightSummaryUnavailable(summaryResult.reason);
  }
  if (matchdaysAvailable) renderInsightGoalTrend(state.insightMatchdays);
  else renderInsightGoalTrendUnavailable(matchdaysResult.reason);
  if (teamsAvailable) renderInsightTeams();
  else renderInsightTeamsUnavailable(teamsResult.reason);
  if (!summaryAvailable || !teamsAvailable || !matchdaysAvailable) {
    renderListState(
      ui.insightTeamDetail,
      "Team detail is unavailable",
      "The selected team analytics could not be loaded.",
      "error",
    );
    const failures = results.filter((result) => result.status === "rejected");
    const message =
      failures.length === results.length
        ? describeRequestFailure("Insights", failures[0].reason)
        : "Some Insights data could not be loaded. Check the local dashboard service and try again.";
    setStatus(ui.insightsStatus, message, "error");
    showAppAlert(message);
    return;
  }
  setStatus(ui.insightsStatus, "Insights updated from validated completed results.", "ok");
}

function fixtureKickoffText(match) {
  const stage = match.stage_name ? `${match.stage_name} / ` : "";
  if (!match.kickoff_utc) {
    const status = match.is_finished ? "Kickoff not recorded" : "Kickoff to be confirmed";
    return `${stage}${status}`;
  }
  return `${stage}${formatDate(match.kickoff_utc)}`;
}

function renderUpcomingFixtures(page) {
  const matches = page.items;
  ui.upcomingList.replaceChildren();
  if (matches.length === 0) {
    renderListState(
      ui.upcomingList,
      "No upcoming fixture records",
      "No unfinished fixtures have been imported for this competition selection.",
    );
    setStatus(ui.upcomingStatus, "No unfinished fixture records are currently loaded.", "ok");
    return;
  }

  matches.forEach((match) => {
    const item = element("article", { className: "upcoming-fixture" });
    const identity = element("div", { className: "upcoming-fixture-identity" });
    identity.append(
      element("strong", { text: `${match.home_team} vs ${match.away_team}` }),
      element("span", {
        className: "metadata",
        text: `Matchday ${valueOrNotSupplied(match.matchday_number)}`,
      }),
    );
    const details = element("div", { className: "upcoming-fixture-details" });
    details.append(
      sourcePill(match),
      element("span", { text: fixtureKickoffText(match) }),
      element("span", { className: "metadata", text: "Score: Not supplied" }),
    );
    const button = element("button", {
      className: "button button-quiet",
      text: "View match",
    });
    button.type = "button";
    button.addEventListener("click", () => showMatch(match.match_id));
    item.append(identity, details, button);
    ui.upcomingList.append(item);
  });
  const missingKickoffs = matches.filter((match) => !match.kickoff_utc).length;
  const displayCount = `${formatCount(matches.length)} of ${formatCount(page.total)}`;
  const suffix = missingKickoffs
    ? " Fixtures without a confirmed kickoff appear after scheduled fixtures."
    : "";
  setBusy(ui.upcomingList, false);
  setStatus(
    ui.upcomingStatus,
    `${displayCount} upcoming fixture records shown from nearest kickoff first.${suffix}`,
    "ok",
  );
}

async function loadUpcomingFixtures() {
  const requestId = ++state.upcomingRequestId;
  setBusy(ui.upcomingList, true);
  setStatus(ui.upcomingStatus, "Loading unfinished fixtures...", "loading");
  ui.upcomingList.replaceChildren(
    contentState("Loading upcoming fixtures", "Querying unfinished fixture records.", "loading"),
  );
  try {
    const page = await request(
      apiPath("/api/matches", {
        competition_season_id: selectedCompetitionId(),
        finished: false,
        limit: 6,
        sort: "explorer",
      }),
    );
    if (requestId !== state.upcomingRequestId) return;
    renderUpcomingFixtures(page);
  } catch (error) {
    if (requestId !== state.upcomingRequestId) return;
    const message = describeRequestFailure("Upcoming fixtures", error);
    renderListState(ui.upcomingList, "Upcoming fixtures are unavailable", message, "error");
    setStatus(ui.upcomingStatus, message, "error");
    showAppAlert(message);
  }
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
  footer.append(
    element("p", { className: "fixture-time", text: fixtureKickoffText(match) }),
  );
  const button = element("button", { className: "button button-card", text: "View match details" });
  button.type = "button";
  button.addEventListener("click", () => showMatch(match.match_id));
  card.append(topLine, teamBlock, footer, button);
  return card;
}

function renderFixturePage(page) {
  const matches = page.items;
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
  setStatus(ui.fixtureStatus, `${totalText} found. ${fixtureOrderLabel()}.`, "ok");
}

function fixtureOrderLabel() {
  const selectedSort = ui.sortSelect?.value || "explorer";
  if (selectedSort === "kickoff-asc") return "Earliest known kickoff first";
  if (selectedSort === "kickoff-desc") return "Latest known kickoff first";
  if (ui.finishedSelect?.value === "true") return "Newest completed kickoff first";
  if (ui.finishedSelect?.value === "false") return "Nearest upcoming kickoff first";
  return "Completed matches first, then upcoming fixtures";
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
    sort: ui.sortSelect?.value || "explorer",
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

function changeCard(group) {
  const sourceChange = group.changes[0].change;
  const card = changeEvent(group, sourceChange);
  const button = element("button", {
    className: "button button-quiet",
    text: "Open fixture",
  });
  button.type = "button";
  button.addEventListener("click", () => showMatch(sourceChange.match_id));
  card.append(button);
  return card;
}

function renderChangePagination(total, itemCount, groupCount) {
  if (!ui.changePagination) return;
  const hasRecords = total > 0;
  ui.changePagination.hidden = !hasRecords;
  if (!hasRecords) return;

  const first = state.changeOffset + 1;
  const last = Math.min(state.changeOffset + itemCount, total);
  const groupLabel = groupCount === 1 ? "grouped event" : "grouped events";
  const description = [
    `Showing ${formatCount(first)}-${formatCount(last)} of ${formatCount(total)} recorded changes`,
    `(${formatCount(groupCount)} ${groupLabel} on this page).`,
  ].join(" ");
  setText(
    ui.changePageDescription,
    description,
  );
  ui.previousChangePage.disabled = state.changeOffset === 0;
  ui.nextChangePage.disabled = state.changeOffset + itemCount >= total;
}

async function loadChanges({ reset = false } = {}) {
  if (reset) state.changeOffset = 0;
  const requestId = ++state.changeRequestId;
  setBusy(ui.changeList, true);
  setStatus(ui.changesStatus, "Loading observed changes...", "loading");
  ui.changeList.replaceChildren(contentState("Loading change history", "Loading recorded fixture updates.", "loading"));
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
    const groups = groupChangeEvents(page.items);
    ui.changeList.replaceChildren();
    if (page.items.length === 0) {
      renderListState(
        ui.changeList,
        "No observed fixture changes",
        "No fixture updates have been recorded for this competition selection.",
      );
    } else {
      groups.forEach((group) => ui.changeList.append(changeCard(group)));
      setBusy(ui.changeList, false);
    }
    renderChangePagination(page.total, page.items.length, groups.length);
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
  const row = element("li", { className: "detail-row result-row" });
  row.append(element("strong", { text: resultTypeLabel(result.result_type) }));
  row.append(
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

function detailChangeSection(changes) {
  const section = element("section", { className: "detail-section change-detail-section" });
  section.append(element("h3", { text: "Observed changes" }));
  if (!changes || changes.length === 0) {
    section.append(
      element("p", {
        className: "metadata",
        text: "No fixture updates have been recorded for this fixture.",
      }),
    );
    return section;
  }
  const groups = groupChangeEvents(changes);
  const summary = [
    `${formatCount(changes.length)} stored change${changes.length === 1 ? "" : "s"}`,
    `grouped into ${formatCount(groups.length)} event${groups.length === 1 ? "" : "s"}.`,
  ].join(" ");
  section.append(
    element("p", {
      className: "metadata",
      text: summary,
    }),
  );
  const list = element("div", {
    className: "change-event-list detail-change-event-list",
  });
  groups.forEach((group) => list.append(changeEvent(group)));
  section.append(list);
  return section;
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
      "Results",
      match.results,
      resultRow,
      "No result scores were supplied for this fixture.",
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
    provenance.append(detailChangeSection(changes));
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

async function refreshDashboard({ preserveChangePage = false, checkFreshness = true } = {}) {
  if (state.dashboardRefreshInFlight) return;
  state.dashboardRefreshInFlight = true;
  clearAppAlert();
  try {
    const competitionsLoaded = await loadCompetitions();
    if (competitionsLoaded) await loadMatchdays();
    await Promise.all([
      loadServiceStatus(),
      loadOverview(),
      loadInsights(),
      loadUpcomingFixtures(),
      loadFixtures(),
      loadChanges({ reset: !preserveChangePage }),
    ]);
    if (checkFreshness) await loadFreshness({ refreshOnChange: false });
  } finally {
    state.dashboardRefreshInFlight = false;
  }
}

function scheduleFreshnessPoll(delay = FRESHNESS_POLL_INTERVAL_MS) {
  if (state.freshnessPollTimer !== null) clearTimeout(state.freshnessPollTimer);
  state.freshnessPollTimer = null;
  if (document.hidden) return;
  state.freshnessPollTimer = window.setTimeout(() => {
    state.freshnessPollTimer = null;
    void loadFreshness();
  }, delay);
}

async function loadFreshness({ refreshOnChange = true } = {}) {
  if (state.freshnessRequestInFlight || document.hidden) return;
  state.freshnessRequestInFlight = true;
  try {
    const freshness = await request(
      apiPath("/api/freshness", { competition_season_id: selectedCompetitionId() }),
    );
    const revisionChanged =
      state.freshnessInitialized && state.freshnessRevision !== (freshness.revision ?? null);
    state.freshnessRevision = freshness.revision ?? null;
    state.freshnessInitialized = true;
    updateLastUpdatedTimestamp(freshness.latest_successful_sync_at_utc);
    state.freshnessRetryDelayMs = FRESHNESS_POLL_INTERVAL_MS;
    renderFreshnessCheck("");
    if (
      refreshOnChange &&
      revisionChanged
    ) {
      await refreshDashboard({ preserveChangePage: true, checkFreshness: false });
    }
    scheduleFreshnessPoll();
  } catch {
    renderFreshnessCheck("Update check unavailable; current data remains visible.");
    state.freshnessRetryDelayMs = Math.min(
      state.freshnessRetryDelayMs * 2,
      FRESHNESS_MAX_RETRY_DELAY_MS,
    );
    scheduleFreshnessPoll(state.freshnessRetryDelayMs);
  } finally {
    state.freshnessRequestInFlight = false;
  }
}

function clearFilters() {
  ui.competitionSelect.value = "";
  ui.matchdaySelect.value = "";
  ui.finishedSelect.value = "true";
  ui.sortSelect.value = "explorer";
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
    await Promise.all([
      loadOverview(),
      loadInsights(),
      loadUpcomingFixtures(),
      loadFixtures(),
      loadChanges({ reset: true }),
    ]);
  });
  ui.sortSelect.addEventListener("change", () => {
    if (!state.fixturesLoading) void loadFixtures();
  });
  document.querySelector("#clear-filters").addEventListener("click", async () => {
    clearFilters();
    renderCompetitionContext();
    const matchdaysLoaded = await loadMatchdays();
    if (!matchdaysLoaded) return;
    await Promise.all([
      loadOverview(),
      loadInsights(),
      loadUpcomingFixtures(),
      loadFixtures(),
      loadChanges({ reset: true }),
    ]);
  });
  document.querySelector("#refresh-dashboard").addEventListener("click", refreshDashboard);
  document.querySelector("#refresh-changes").addEventListener("click", loadChanges);
  ui.insightTeamSearch.addEventListener("input", renderInsightTeams);
  ui.insightTeamSort.addEventListener("change", renderInsightTeams);
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
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      if (state.freshnessPollTimer !== null) clearTimeout(state.freshnessPollTimer);
      state.freshnessPollTimer = null;
      return;
    }
    void loadFreshness();
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
  orderDashboardSections();
  setupSectionNavigation();
  attachEventListeners();
  await refreshDashboard();
}

window.addEventListener("error", () => {
  showAppAlert("The dashboard encountered a client-side error. Reload the page and check the browser console if it persists.");
});
window.addEventListener("unhandledrejection", () => {
  showAppAlert("The dashboard could not complete an asynchronous request. Check the visible panel errors and local dashboard service.");
});

initialize().catch(() => {
  showAppAlert("The dashboard could not start. Reload the page after confirming the local dashboard service is running.");
});
