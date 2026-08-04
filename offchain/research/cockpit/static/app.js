"use strict";

const state = {
  meta: null,
  envelope: null,
  selectedTrialId: null,
  refreshing: false,
  timer: null
};

const byId = (id) => document.getElementById(id);

function labelFor(value) {
  return String(value).replaceAll("_", " ").toUpperCase();
}

function textNode(value) {
  return document.createTextNode(value === null ? "null" : String(value));
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

function renderNested(value) {
  if (value === null || typeof value !== "object") {
    return textNode(value === null ? "null" : String(value));
  }
  const container = element("div", "nested-value");
  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      const row = element("div", "nested-row");
      row.append(element("span", "nested-key", String(index)), renderNested(item));
      container.append(row);
    });
  } else {
    Object.entries(value).forEach(([key, item]) => {
      const row = element("div", "nested-row");
      row.append(element("span", "nested-key", labelFor(key)), renderNested(item));
      container.append(row);
    });
  }
  if (!container.hasChildNodes()) {
    container.append(textNode("—"));
  }
  return container;
}

function detailList(entries) {
  const list = element("dl", "detail-list");
  entries.forEach(([key, value]) => {
    const term = element("dt", null, labelFor(key));
    const detail = element("dd");
    detail.append(renderNested(value));
    list.append(term, detail);
  });
  return list;
}

function setOptions(select, values, allLabel) {
  const previous = select.value;
  const nodes = [element("option", null, allLabel)];
  nodes[0].value = "";
  values.forEach((value) => {
    const option = element("option", null, value);
    option.value = value;
    nodes.push(option);
  });
  select.replaceChildren(...nodes);
  if (values.includes(previous)) {
    select.value = previous;
  }
}

function renderHeader(snapshot, envelope) {
  const system = snapshot.system;
  byId("mode-badge").textContent = envelope.cockpit_mode;
  byId("health-badge").textContent = system.health_token;
  byId("health-badge").className =
    system.health_token === "HEALTHY" ? "badge" : "badge badge-attention";
  byId("snapshot-time").textContent = system.as_of;
  byId("commit-short").textContent = system.repository_commit.slice(0, 12);
  if (envelope.cockpit_mode === "DEMO") {
    byId("mode-banner").textContent = "DEMO — SYNTHETIC NON-ALPHA EVIDENCE";
    byId("scenario-control").hidden = false;
    byId("scenario-select").value = envelope.demo_scenario;
    byId("incident-banner").hidden = envelope.demo_scenario !== "DEGRADED";
  } else {
    byId("mode-banner").textContent = "CONNECTED LOCAL READ-ONLY OBSERVATION";
    byId("scenario-control").hidden = true;
    byId("incident-banner").hidden = true;
  }
}

function renderOverview(snapshot) {
  const system = snapshot.system;
  const entries = [
    ["Health", system.health_token],
    ["Budgets", system.total_budget_count],
    ["Reservations", system.total_reservation_count],
    ["Lifecycle events", system.total_event_count],
    ["Result links", system.total_result_link_count],
    ["Verified results", system.verified_linked_result_count],
    ["Incidents", system.incident_count]
  ];
  const nodes = entries.map(([key, value]) => {
    const wrapper = element("div", "stat");
    wrapper.append(element("dt", null, key), element("dd", null, value));
    return wrapper;
  });
  byId("overview-grid").replaceChildren(...nodes);
  byId("snapshot-id").textContent = snapshot.snapshot_id;
  byId("snapshot-hash").textContent = snapshot.canonical_snapshot_hash;
}

function renderAuthority(snapshot) {
  const authorized = [];
  const prohibited = [];
  Object.entries(snapshot.system.authority_projection).forEach(([key, value]) => {
    const wrapper = element("div", "authority-item");
    wrapper.append(
      element("dt", null, labelFor(key)),
      element("dd", null, String(value).toUpperCase())
    );
    if (value === true) {
      authorized.push(wrapper);
    } else {
      prohibited.push(wrapper);
    }
  });
  byId("authorized-list").replaceChildren(...authorized);
  byId("prohibited-list").replaceChildren(...prohibited);
}

function normalizedTrialText(trial) {
  return [
    trial.trial_id,
    trial.budget_id,
    trial.experiment_family,
    trial.latest_status_token,
    trial.latest_reason_token,
    trial.result_verification_token
  ].join(" ").toLocaleLowerCase();
}

function filteredTrials(trials) {
  const text = byId("text-filter").value.trim().toLocaleLowerCase();
  const lifecycle = byId("lifecycle-filter").value;
  const verification = byId("verification-filter").value;
  return trials.filter((trial) => {
    const textMatches = !text || normalizedTrialText(trial).includes(text);
    const lifecycleMatches = !lifecycle || trial.latest_status_token === lifecycle;
    const verificationMatches =
      !verification || trial.result_verification_token === verification;
    return textMatches && lifecycleMatches && verificationMatches;
  });
}

function selectTrial(trialId) {
  state.selectedTrialId = trialId;
  renderTrials(state.envelope.snapshot.trials);
  renderResult(state.envelope.snapshot);
}

function renderTrials(trials) {
  const lifecycleValues = [...new Set(trials.map((item) => item.latest_status_token).filter(Boolean))];
  const verificationValues = [...new Set(trials.map((item) => item.result_verification_token).filter(Boolean))];
  setOptions(byId("lifecycle-filter"), lifecycleValues, "All lifecycle statuses");
  setOptions(byId("verification-filter"), verificationValues, "All verification statuses");

  const visible = filteredTrials(trials);
  const rows = visible.map((trial) => {
    const row = document.createElement("tr");
    const button = element("button", "trial-button", trial.trial_id);
    button.type = "button";
    button.setAttribute("aria-pressed", String(state.selectedTrialId === trial.trial_id));
    button.setAttribute("aria-label", `Inspect trial ${trial.trial_id}`);
    button.addEventListener("click", () => selectTrial(trial.trial_id));
    const first = document.createElement("td");
    first.append(button);
    const values = [
      trial.budget_id,
      trial.experiment_family,
      trial.declared_trial_number,
      trial.reserved_at,
      trial.latest_status_token,
      trial.latest_reason_token,
      trial.event_count,
      trial.result_verification_token,
      trial.incident_ids.length.toString()
    ];
    row.append(first);
    values.forEach((value) => {
      row.append(element("td", null, value === null ? "—" : value));
    });
    return row;
  });
  byId("trial-rows").replaceChildren(...rows);
  byId("no-trials").hidden = rows.length !== 0;
  byId("trial-count").textContent = `${visible.length} displayed · ${trials.length} projected`;
}

function inspectorSection(title, entries) {
  const section = element("section", "inspector-section");
  section.append(element("h3", null, title), detailList(entries));
  return section;
}

function renderResult(snapshot) {
  const trial = snapshot.trials.find((item) => item.trial_id === state.selectedTrialId);
  const result = snapshot.results.find((item) => item.trial_id === state.selectedTrialId);
  if (!trial || !result || trial.result_verification_token !== "VERIFIED") {
    byId("result-inspector").replaceChildren(
      element("p", "empty-state", "No verified result selected.")
    );
    return;
  }
  const identity = [
    ["result_bundle_id", result.result_bundle_id],
    ["result_bundle_hash", result.result_bundle_hash],
    ["trial_status_token", result.trial_status_token],
    ["trial_reason_token", result.trial_reason_token],
    ["result_status_token", result.result_status_token],
    ["result_reason_token", result.result_reason_token],
    ["human_explanation", result.human_explanation],
    ["control_identifier", result.control_identifier],
    ["control_parameters", result.control_parameters]
  ];
  const provenance = [
    ["dataset_identity", result.dataset_identity],
    ["code_identity", result.code_identity],
    ["simulator_identity", result.simulator_identity],
    ["execution_model_identity", result.execution_model_identity],
    ["cost_model_identity", result.cost_model_identity],
    ["risk_model_identity", result.risk_model_identity],
    ["implementation_repository_commit", result.implementation_repository_commit]
  ];
  const metrics = [
    ["gross_result", result.gross_result],
    ["net_result", result.net_result],
    ["benchmark", result.benchmark],
    ["costs_by_component", result.costs_by_component],
    ["maximum_drawdown", result.maximum_drawdown],
    ["exposure", result.exposure],
    ["turnover", result.turnover],
    ["trade_count", result.trade_count],
    ["concentration", result.concentration],
    ["timing_diagnostics", result.timing_diagnostics]
  ];
  const verification = [
    ["protected_access_counts", result.protected_access_counts],
    ["artifact_declarations", result.artifact_declarations],
    ["warnings", result.warnings],
    ["verification_declarations", result.verification_declarations],
    ["canonical_result_projection_hash", result.canonical_result_projection_hash]
  ];
  byId("result-inspector").replaceChildren(
    inspectorSection("Lifecycle and control", identity),
    inspectorSection("Dataset and implementation identity", provenance),
    inspectorSection("Authoritative metrics", metrics),
    inspectorSection("Artifacts, warnings and verification", verification)
  );
}

function renderIncidents(incidents) {
  if (incidents.length === 0) {
    byId("incident-list").replaceChildren(
      element("p", "empty-state", "NO INTEGRITY INCIDENTS IN THIS SNAPSHOT")
    );
  } else {
    const cards = incidents.map((incident) => {
      const card = element("article", "incident-card");
      card.append(
        element("h3", null, `${incident.severity} · ${incident.category}`),
        detailList([
          ["incident_id", incident.incident_id],
          ["reason", incident.reason_token],
          ["explanation", incident.human_explanation],
          ["trial_id", incident.trial_id],
          ["detected_timestamp", incident.detected_at],
          ["evidence_identities", incident.evidence_identities],
          ["canonical_incident_hash", incident.canonical_incident_hash]
        ])
      );
      return card;
    });
    byId("incident-list").replaceChildren(...cards);
  }
  byId("incident-count").textContent = `${incidents.length} projected`;
}

function governanceCard(title, entries) {
  const card = element("article", "governance-card");
  card.append(element("h3", null, title), detailList(entries));
  return card;
}

function renderGovernance(snapshot) {
  const system = snapshot.system;
  const verification = system.contract_verification;
  const cards = [
    governanceCard("Mission 93", [
      ["contract_id", system.mission_93_contract_id],
      ["contract_hash", system.mission_93_contract_hash],
      ["verified", verification.mission_93_verified]
    ]),
    governanceCard("Mission 94", [
      ["contract_id", system.mission_94_contract_id],
      ["contract_hash", system.mission_94_contract_hash],
      ["verified", verification.mission_94_verified]
    ]),
    governanceCard("Mission 95", [
      ["contract_id", system.mission_95_contract_id],
      ["contract_hash", system.mission_95_contract_hash],
      ["verified", verification.mission_95_verified]
    ]),
    governanceCard("Mission 96A", [
      ["contract_id", system.mission_96a_contract_id],
      ["contract_hash", system.mission_96a_contract_hash],
      ["verified", verification.mission_96a_verified]
    ]),
    governanceCard("Mission 96B Cockpit", [
      ["contract_id", state.meta.cockpit_contract_id],
      ["contract_hash", state.meta.cockpit_contract_hash],
      ["authorization_stage", state.meta.authorization_stage],
      ["predecessor_chain_verified", verification.predecessor_chain_verified]
    ]),
    governanceCard("Repository identity", [
      ["repository_root_path_identity", system.repository_root_path_identity],
      ["repository_commit", system.repository_commit],
      ["ledger_path_identity", system.ledger_path_identity],
      ["result_root_path_identity", system.result_root_path_identity]
    ])
  ];
  byId("governance-grid").replaceChildren(...cards);
}

function renderEvidence(snapshot) {
  const blocks = [];
  snapshot.results.forEach((result) => {
    const block = element("article", "evidence-block");
    block.append(
      element("h3", null, `Verified result · ${result.result_bundle_id}`),
      detailList([
        ["warnings", result.warnings],
        ["artifact_paths_and_hashes", result.artifact_declarations],
        ["verification_declarations", result.verification_declarations],
        ["canonical_result_projection_hash", result.canonical_result_projection_hash]
      ])
    );
    blocks.push(block);
  });
  if (blocks.length === 0) {
    blocks.push(element("p", "empty-state", "No verified result evidence in this snapshot."));
  }
  byId("evidence-content").replaceChildren(...blocks);
}

function renderSnapshot(envelope) {
  const snapshot = envelope.snapshot;
  renderHeader(snapshot, envelope);
  renderOverview(snapshot);
  renderAuthority(snapshot);
  const selectedStillExists = snapshot.trials.some(
    (trial) => trial.trial_id === state.selectedTrialId
  );
  if (!selectedStillExists) {
    state.selectedTrialId = null;
  }
  renderTrials(snapshot.trials);
  renderResult(snapshot);
  renderIncidents(snapshot.incidents);
  renderGovernance(snapshot);
  renderEvidence(snapshot);
}

async function requestJson(path) {
  const response = await fetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    headers: { Accept: "application/json" }
  });
  const value = await response.json();
  if (!response.ok) {
    const reason = value.error && value.error.reason_token
      ? value.error.reason_token
      : "SNAPSHOT_UNAVAILABLE";
    throw new Error(reason);
  }
  return value;
}

async function refreshSnapshot(scenario) {
  if (state.refreshing) {
    return;
  }
  state.refreshing = true;
  byId("refresh-status").textContent = "Refreshing local snapshot…";
  const query = scenario ? `?scenario=${encodeURIComponent(scenario)}` : "";
  try {
    const envelope = await requestJson(`/api/v1/snapshot${query}`);
    state.envelope = envelope;
    renderSnapshot(envelope);
    byId("error-banner").hidden = true;
    byId("refresh-status").textContent = `Last successful refresh · ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    byId("error-banner").textContent =
      "The local refresh failed. The previous verified display has been preserved.";
    byId("error-banner").hidden = false;
    byId("refresh-status").textContent = "Refresh failed · previous display retained";
  } finally {
    state.refreshing = false;
  }
}

function bindControls() {
  ["text-filter", "lifecycle-filter", "verification-filter"].forEach((id) => {
    byId(id).addEventListener("input", () => {
      if (state.envelope) {
        renderTrials(state.envelope.snapshot.trials);
      }
    });
  });
  byId("scenario-select").addEventListener("change", (event) => {
    refreshSnapshot(event.target.value);
  });
}

async function start() {
  bindControls();
  try {
    state.meta = await requestJson("/api/v1/meta");
    await refreshSnapshot(null);
    state.timer = window.setInterval(
      () => refreshSnapshot(
        state.envelope && state.envelope.cockpit_mode === "DEMO"
          ? state.envelope.demo_scenario
          : null
      ),
      state.meta.refresh_seconds * 1000
    );
  } catch (error) {
    byId("error-banner").textContent =
      "The local cockpit could not initialize its read-only observation.";
    byId("error-banner").hidden = false;
    byId("refresh-status").textContent = "Initialization failed";
  }
}

start();
