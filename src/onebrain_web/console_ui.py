# ruff: noqa: E501

from __future__ import annotations

from onebrain_web.design_system import ONEBRAIN_DESIGN_SYSTEM_CSS


def console_view_html() -> str:
    return CONSOLE_UI_HTML.replace("__ONEBRAIN_DESIGN_SYSTEM_CSS__", ONEBRAIN_DESIGN_SYSTEM_CSS)


CONSOLE_UI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OneBrain</title>
  <style>
    __ONEBRAIN_DESIGN_SYSTEM_CSS__

    .workbench-frame {
      display: grid;
      grid-template-columns: 260px minmax(0, 1fr);
      min-height: 100vh;
      background: var(--ob-ink);
    }

    .workbench-main {
      min-width: 0;
      display: block;
      min-height: 100vh;
      background:
        radial-gradient(circle at 20% 0%, rgba(217, 119, 87, 0.10), transparent 28rem),
        linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent 18rem),
        var(--ob-ink);
    }

    .workbench-content {
      min-height: 0;
      overflow: hidden;
      padding: 14px;
      height: 100vh;
    }

    .tab-panel {
      display: none;
      min-height: 0;
      height: 100%;
    }

    .tab-panel[data-active="true"] {
      display: block;
    }

    .graph-frame {
      width: 100%;
      height: calc(100vh - 28px);
      min-height: 620px;
      border: 1px solid var(--ob-line);
      border-radius: var(--ob-radius-panel);
      background: var(--ob-canvas);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
    }

    .api-layout {
      height: 100%;
      min-height: 0;
      display: grid;
      grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
      gap: 12px;
    }

    .component-frame {
      height: calc(100vh - 28px);
      min-height: 620px;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      overflow: hidden;
      border: 1px solid color-mix(in srgb, var(--ob-line) 82%, transparent);
      border-radius: var(--ob-radius-panel);
      background: color-mix(in srgb, var(--ob-panel) 96%, transparent);
    }

    .component-header {
      min-height: 58px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 14px;
      border-bottom: 1px solid color-mix(in srgb, var(--ob-line) 72%, transparent);
      background: color-mix(in srgb, var(--ob-ink-2) 88%, transparent);
    }

    .component-title {
      margin: 0;
      color: var(--ob-text);
      font-size: 18px;
      line-height: 1.2;
      font-weight: 780;
    }

    .component-subtitle {
      margin: 3px 0 0;
      color: var(--ob-muted);
      font-size: 12px;
      line-height: 1.35;
    }

    .component-badge {
      min-height: 28px;
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border: 1px solid color-mix(in srgb, var(--ob-tigerlily) 24%, var(--ob-line));
      border-radius: var(--ob-radius-compact);
      background: color-mix(in srgb, var(--ob-tigerlily) 8%, transparent);
      color: var(--ob-muted);
      padding: 0 9px;
      font-size: 12px;
      font-weight: 750;
      white-space: nowrap;
    }

    .component-badge[data-state="success"],
    .component-badge[data-state="running"] {
      border-color: color-mix(in srgb, var(--ob-green) 36%, var(--ob-line));
      background: color-mix(in srgb, var(--ob-green) 8%, transparent);
      color: var(--ob-text);
    }

    .component-badge[data-state="failed"] {
      border-color: color-mix(in srgb, var(--ob-red) 40%, var(--ob-line));
      background: color-mix(in srgb, var(--ob-red) 9%, transparent);
      color: var(--ob-text);
    }

    .component-badge[data-state="not_started"],
    .component-badge[data-state="unavailable"] {
      border-color: color-mix(in srgb, var(--ob-yellow) 28%, var(--ob-line));
      background: color-mix(in srgb, var(--ob-yellow) 7%, transparent);
    }

    .component-body {
      min-height: 0;
      overflow: hidden;
      padding: 12px;
    }

    .endpoint-list,
    .endpoint-details,
    .job-layout {
      height: 100%;
      overflow: auto;
    }

    .endpoint-list {
      display: grid;
      align-content: start;
      gap: 8px;
      padding: 10px;
    }

    .endpoint-row {
      width: 100%;
      min-height: 44px;
      display: grid;
      grid-template-columns: 68px minmax(0, 1fr);
      align-items: center;
      gap: 8px;
      border: 1px solid var(--ob-line);
      border-radius: var(--ob-radius-compact);
      background: var(--ob-panel);
      color: var(--ob-text);
      text-align: left;
      padding: 8px;
    }

    .endpoint-row[data-active="true"] {
      border-color: var(--ob-tigerlily);
      box-shadow: var(--ob-shadow-focus);
    }

    .method-pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 24px;
      border-radius: 5px;
      font-size: 11px;
      font-weight: 800;
      color: #0e0f0d;
      background: var(--ob-blue);
    }

    .method-pill[data-method="POST"] {
      background: var(--ob-green);
    }

    .method-pill[data-method="GET"] {
      background: var(--ob-blue);
    }

    .endpoint-path {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-family: Consolas, "Cascadia Mono", monospace;
      font-size: 12px;
    }

    .endpoint-details {
      padding: 14px;
    }

    .operation-header {
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }

    .operation-title {
      margin: 0;
      font-size: 18px;
      line-height: 1.25;
    }

    .operation-summary {
      color: var(--ob-muted);
      margin: 4px 0 0;
      max-width: 72ch;
    }

    .schema-box {
      min-height: 160px;
      overflow: auto;
      border: 1px solid var(--ob-line);
      border-radius: var(--ob-radius-compact);
      background: #0a0b0a;
      color: #f2efe7;
      padding: 12px;
      font-family: Consolas, "Cascadia Mono", monospace;
      font-size: 12px;
      line-height: 1.5;
      white-space: pre;
    }

    .schema-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 12px;
    }

    .job-layout {
      height: 100%;
      min-height: 0;
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(320px, 0.42fr);
      gap: 12px;
    }

    .job-stack {
      display: grid;
      align-content: start;
      gap: 12px;
    }

    .metric-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }

    .metric-tile {
      border: 1px solid var(--ob-line);
      border-radius: var(--ob-radius-compact);
      background: var(--ob-panel);
      padding: 10px;
      min-height: 72px;
    }

    .metric-tile.status-ok {
      border-color: color-mix(in srgb, var(--ob-green) 34%, var(--ob-line));
      background: color-mix(in srgb, var(--ob-green) 8%, var(--ob-panel));
    }

    .metric-tile.status-muted {
      border-color: color-mix(in srgb, var(--ob-yellow) 26%, var(--ob-line));
      background: color-mix(in srgb, var(--ob-yellow) 6%, var(--ob-panel));
    }

    .metric-value {
      display: block;
      font-size: 22px;
      font-weight: 800;
      line-height: 1;
    }

    .metric-label {
      display: block;
      margin-top: 7px;
      color: var(--ob-muted);
      font-size: 12px;
      font-weight: 700;
    }

    .command-box {
      border: 1px solid var(--ob-line);
      border-radius: var(--ob-radius-compact);
      background: #0a0b0a;
      padding: 10px;
      color: var(--ob-text);
      font-family: Consolas, "Cascadia Mono", monospace;
      font-size: 12px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    .job-run-list {
      display: grid;
      gap: 8px;
    }

    .job-run-row {
      display: grid;
      grid-template-columns: minmax(120px, 0.42fr) minmax(0, 1fr);
      gap: 10px;
      align-items: center;
      min-height: 36px;
      border-top: 1px solid color-mix(in srgb, var(--ob-line) 62%, transparent);
      padding-top: 8px;
    }

    .job-run-row:first-child {
      border-top: 0;
      padding-top: 0;
    }

    .job-run-row span {
      color: var(--ob-muted);
      font-size: 12px;
      font-weight: 720;
    }

    .job-run-row strong {
      color: var(--ob-text);
      font-size: 12px;
      font-weight: 720;
      overflow-wrap: anywhere;
    }

    .job-config .ob-kv {
      display: grid;
      grid-template-columns: 132px minmax(0, 1fr);
      align-items: start;
      gap: 10px;
    }

    .job-config .ob-kv strong {
      justify-self: start;
      text-align: left;
      overflow-wrap: anywhere;
    }

    @media (max-width: 980px) {
      .workbench-frame {
        grid-template-columns: 1fr;
      }

      .ob-sidebar {
        position: static;
        min-height: auto;
      }

      .ob-nav {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }

      .api-layout,
      .job-layout,
      .schema-grid {
        grid-template-columns: 1fr;
      }

      .graph-frame,
      .api-layout,
      .job-layout {
        height: auto;
        min-height: 620px;
      }
    }
  </style>
</head>
<body>
  <div class="workbench-frame">
    <aside class="ob-sidebar">
      <div class="ob-brand">
        <div class="ob-brand-mark">OB</div>
        <div>
          <div class="ob-brand-title">OneBrain</div>
          <div class="ob-brand-subtitle">Graph intelligence</div>
        </div>
      </div>

      <nav class="ob-nav" aria-label="OneBrain sections">
        <button class="ob-nav-link" type="button" data-tab="graph" data-active="true">Graphs</button>
        <button class="ob-nav-link" type="button" data-tab="api">Swagger</button>
        <button class="ob-nav-link" type="button" data-tab="jobs">Jobs</button>
      </nav>
    </aside>

    <main class="workbench-main">
      <section class="workbench-content">
        <section class="tab-panel" data-panel="graph" data-active="true">
          <iframe class="graph-frame" src="/graph" title="OneBrain graph"></iframe>
        </section>

        <section class="tab-panel" data-panel="api">
          <div class="component-frame">
            <header class="component-header">
              <div>
                <h1 class="component-title">OneBrain Swagger</h1>
                <p class="component-subtitle">Readable OpenAPI contract for memory, graph, ingestion, and context APIs.</p>
              </div>
              <span class="component-badge" id="apiBadge">OpenAPI</span>
            </header>
            <div class="component-body">
              <div class="api-layout">
                <aside class="ob-surface endpoint-list" id="endpointList" aria-label="API endpoints"></aside>
                <article class="ob-surface endpoint-details" id="endpointDetails">
                  <div class="ob-empty-state">Loading Swagger/OpenAPI contract...</div>
                </article>
              </div>
            </div>
          </div>
        </section>

        <section class="tab-panel" data-panel="jobs">
          <div class="component-frame">
            <header class="component-header">
              <div>
                <h1 class="component-title">Graph Aggregation Jobs</h1>
                <p class="component-subtitle">Scheduled materialization of high-confidence graph clusters into context memories.</p>
              </div>
              <span class="component-badge" id="jobStatusBadge" data-state="not_started">No report</span>
            </header>
            <div class="component-body">
              <div class="job-layout">
                <div class="job-stack">
                  <section class="ob-surface ob-panel-block">
                    <span class="ob-section-title">Run Status</span>
                    <div class="metric-grid">
                      <div class="metric-tile status-muted">
                        <span class="metric-value" id="jobLastRun">No report</span>
                        <span class="metric-label">Last run</span>
                      </div>
                      <div class="metric-tile status-ok">
                        <span class="metric-value" id="jobInterval">3600s</span>
                        <span class="metric-label">Interval</span>
                      </div>
                      <div class="metric-tile">
                        <span class="metric-value" id="jobGraphLimit">500</span>
                        <span class="metric-label">Graph limit</span>
                      </div>
                      <div class="metric-tile">
                        <span class="metric-value" id="jobMaxDegree">12</span>
                        <span class="metric-label">Max degree</span>
                      </div>
                    </div>
                  </section>

                  <section class="ob-surface ob-panel-block">
                    <span class="ob-section-title">Execution Contract</span>
                    <div class="job-run-list">
                      <div class="job-run-row">
                        <span>Command</span>
                        <strong id="jobCommand">onebrain-jobs run_scheduled_jobs --job graph-aggregation</strong>
                      </div>
                      <div class="job-run-row">
                        <span>Last run</span>
                        <strong id="jobLastRunDetail">Not reported by the scheduler process yet</strong>
                      </div>
                      <div class="job-run-row">
                        <span>Next run</span>
                        <strong id="jobNextRun">Every 3600 seconds while the onebrain-jobs service is running</strong>
                      </div>
                      <div class="job-run-row">
                        <span>Materialization</span>
                        <strong id="jobMaterialization">Creates aggregate context memories and links member memories as aggregates</strong>
                      </div>
                    </div>
                  </section>
                </div>

                <section class="ob-surface ob-panel-block job-config">
                  <span class="ob-section-title">Configuration</span>
                  <div class="ob-kv">
                    <span>Scope</span>
                    <strong id="jobScope">{}</strong>
                  </div>
                  <div class="ob-kv">
                    <span>Correlation limit</span>
                    <strong id="jobCorrelationLimit">750</strong>
                  </div>
                  <div class="ob-kv">
                    <span>Grouping window</span>
                    <strong id="jobGroupingWindow">25</strong>
                  </div>
                  <div class="ob-kv">
                    <span>Minimum cluster</span>
                    <strong id="jobMinCluster">3 memories</strong>
                  </div>
                  <div class="ob-kv">
                    <span>Minimum score</span>
                    <strong id="jobMinScore">0</strong>
                  </div>
                  <div class="ob-kv">
                    <span>Source type</span>
                    <strong id="jobSourceType">graph-aggregation</strong>
                  </div>
                </section>
              </div>
            </div>
          </div>
        </section>
      </section>
    </main>
  </div>

  <script>
    const tabs = [...document.querySelectorAll("[data-tab]")];
    const panels = [...document.querySelectorAll("[data-panel]")];
    const endpointList = document.getElementById("endpointList");
    const endpointDetails = document.getElementById("endpointDetails");
    const apiBadge = document.getElementById("apiBadge");
    const jobStatusBadge = document.getElementById("jobStatusBadge");
    const jobLastRun = document.getElementById("jobLastRun");
    const jobInterval = document.getElementById("jobInterval");
    const jobGraphLimit = document.getElementById("jobGraphLimit");
    const jobMaxDegree = document.getElementById("jobMaxDegree");
    const jobCommand = document.getElementById("jobCommand");
    const jobLastRunDetail = document.getElementById("jobLastRunDetail");
    const jobNextRun = document.getElementById("jobNextRun");
    const jobMaterialization = document.getElementById("jobMaterialization");
    const jobScope = document.getElementById("jobScope");
    const jobCorrelationLimit = document.getElementById("jobCorrelationLimit");
    const jobGroupingWindow = document.getElementById("jobGroupingWindow");
    const jobMinCluster = document.getElementById("jobMinCluster");
    const jobMinScore = document.getElementById("jobMinScore");
    const jobSourceType = document.getElementById("jobSourceType");
    let apiSpec = null;
    let jobStatusLoaded = false;
    let selectedOperation = null;

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        tabs.forEach((item) => item.dataset.active = String(item === tab));
        panels.forEach((panel) => panel.dataset.active = String(panel.dataset.panel === target));
        if (target === "api" && !apiSpec) {
          loadApiSpec();
        }
        if (target === "jobs" && !jobStatusLoaded) {
          loadJobStatus();
        }
      });
    });

    function operationEntries(spec) {
      const methods = ["get", "post", "put", "patch", "delete"];
      const entries = [];
      Object.entries(spec.paths || {}).forEach(([path, operations]) => {
        methods.forEach((method) => {
          if (operations[method]) {
            entries.push({ path, method, operation: operations[method] });
          }
        });
      });
      return entries.sort((left, right) => `${left.path}:${left.method}`.localeCompare(`${right.path}:${right.method}`));
    }

    async function loadApiSpec() {
      endpointDetails.innerHTML = '<div class="ob-empty-state">Loading Swagger/OpenAPI contract...</div>';
      try {
        const response = await fetch("/api/openapi.json", { headers: { "Accept": "application/json" } });
        if (!response.ok) throw new Error(`OpenAPI request failed: ${response.status}`);
        apiSpec = await response.json();
        const entries = operationEntries(apiSpec);
        apiBadge.textContent = `${apiSpec.openapi || "OpenAPI"} - ${entries.length} operations`;
        renderEndpointList(entries);
        renderOperation(entries[0]);
      } catch (error) {
        endpointDetails.innerHTML = `<div class="ob-empty-state">${escapeHtml(error.message)}</div>`;
      }
    }

    function renderEndpointList(entries) {
      endpointList.innerHTML = "";
      entries.forEach((entry, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "endpoint-row";
        button.dataset.active = String(index === 0);
        button.innerHTML = `
          <span class="method-pill" data-method="${entry.method.toUpperCase()}">${entry.method.toUpperCase()}</span>
          <span class="endpoint-path">${escapeHtml(entry.path)}</span>
        `;
        button.addEventListener("click", () => {
          [...endpointList.querySelectorAll(".endpoint-row")].forEach((row) => row.dataset.active = "false");
          button.dataset.active = "true";
          renderOperation(entry);
        });
        endpointList.appendChild(button);
      });
    }

    function renderOperation(entry) {
      if (!entry) {
        endpointDetails.innerHTML = '<div class="ob-empty-state">No API operations found.</div>';
        return;
      }
      selectedOperation = entry;
      const requestBody = entry.operation.requestBody?.content?.["application/json"]?.schema || null;
      const responseSchema = entry.operation.responses?.["200"]?.content?.["application/json"]?.schema || entry.operation.responses?.["201"]?.content?.["application/json"]?.schema || null;
      endpointDetails.innerHTML = `
        <div class="operation-header">
          <div>
            <h2 class="operation-title">${escapeHtml(entry.operation.summary || entry.path)}</h2>
            <p class="operation-summary">${escapeHtml(entry.operation.description || "OneBrain API operation.")}</p>
          </div>
          <span class="method-pill" data-method="${entry.method.toUpperCase()}">${entry.method.toUpperCase()}</span>
        </div>
        <div class="command-box">${escapeHtml(entry.method.toUpperCase())} ${escapeHtml(entry.path)}</div>
        <div class="schema-grid">
          <section>
            <span class="ob-section-title">Request</span>
            <pre class="schema-box">${escapeHtml(JSON.stringify(resolveSchema(requestBody), null, 2))}</pre>
          </section>
          <section>
            <span class="ob-section-title">Response</span>
            <pre class="schema-box">${escapeHtml(JSON.stringify(resolveSchema(responseSchema), null, 2))}</pre>
          </section>
        </div>
      `;
    }

    function resolveSchema(schema) {
      if (!schema) return { type: "object" };
      if (schema.$ref && apiSpec?.components?.schemas) {
        const name = schema.$ref.split("/").pop();
        return apiSpec.components.schemas[name] || schema;
      }
      return schema;
    }

    async function loadJobStatus() {
      jobStatusLoaded = true;
      try {
        const response = await fetch("/api/jobs/graph-aggregation/status", { headers: { "Accept": "application/json" } });
        if (!response.ok) throw new Error(`Job status request failed: ${response.status}`);
        renderJobStatus(await response.json());
      } catch (error) {
        jobStatusBadge.textContent = "Unavailable";
        jobStatusBadge.dataset.state = "unavailable";
        jobLastRun.textContent = "Unavailable";
        jobLastRunDetail.textContent = error.message;
      }
    }

    function renderJobStatus(payload) {
      const scheduler = payload.scheduler || {};
      const configuration = payload.configuration || {};
      const lastRun = payload.last_run || null;
      const status = payload.status || lastRun?.status || "not_started";
      jobStatusBadge.textContent = statusLabel(status);
      jobStatusBadge.dataset.state = status;
      jobLastRun.textContent = lastRun?.finished_at ? relativeTimestamp(lastRun.finished_at) : statusLabel(status);
      jobInterval.textContent = formatSeconds(scheduler.interval_seconds);
      jobGraphLimit.textContent = String(configuration.limit ?? "-");
      jobMaxDegree.textContent = String(configuration.max_degree ?? "-");
      jobCommand.textContent = payload.command || "onebrain-jobs run_scheduled_jobs --job graph-aggregation";
      jobLastRunDetail.textContent = lastRun ? runDetail(lastRun) : "No scheduler execution has been persisted yet.";
      jobNextRun.textContent = payload.next_run_at
        ? formatTimestamp(payload.next_run_at)
        : `Every ${formatSeconds(scheduler.interval_seconds)} while the onebrain-jobs service is running`;
      jobMaterialization.textContent = `Creates ${configuration.memory_type || "context"} memories and links members as ${configuration.link_type || "aggregates"}.`;
      jobScope.textContent = JSON.stringify(configuration.scope || {});
      jobCorrelationLimit.textContent = String(configuration.correlation_limit ?? "-");
      jobGroupingWindow.textContent = String(configuration.grouping_limit ?? "-");
      jobMinCluster.textContent = `${configuration.grouping_min_size ?? "-"} memories`;
      jobMinScore.textContent = String(configuration.min_score ?? "-");
      jobSourceType.textContent = configuration.source_type || "graph-aggregation";
    }

    function statusLabel(status) {
      const labels = {
        failed: "Failed",
        not_started: "No report",
        running: "Running",
        success: "Healthy"
      };
      return labels[status] || status;
    }

    function runDetail(lastRun) {
      const status = statusLabel(lastRun.status || "not_started");
      const started = lastRun.started_at ? formatTimestamp(lastRun.started_at) : "unknown start";
      const duration = Number.isFinite(Number(lastRun.duration_seconds))
        ? ` in ${Number(lastRun.duration_seconds).toFixed(1)}s`
        : "";
      const result = lastRun.result
        ? ` - scanned ${lastRun.result.scanned ?? 0}, created ${lastRun.result.created ?? 0}, existing ${lastRun.result.existing ?? 0}, skipped ${lastRun.result.skipped ?? 0}`
        : "";
      const error = lastRun.error?.message ? ` - ${lastRun.error.message}` : "";
      return `${status} at ${started}${duration}${result}${error}`;
    }

    function formatSeconds(value) {
      const seconds = Number(value);
      if (!Number.isFinite(seconds)) return "-";
      if (seconds >= 3600 && seconds % 3600 === 0) return `${seconds / 3600}h`;
      if (seconds >= 60 && seconds % 60 === 0) return `${seconds / 60}m`;
      return `${seconds}s`;
    }

    function formatTimestamp(value) {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      return date.toLocaleString();
    }

    function relativeTimestamp(value) {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return "Reported";
      const diffSeconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
      if (diffSeconds < 60) return "Just now";
      if (diffSeconds < 3600) return `${Math.round(diffSeconds / 60)}m ago`;
      if (diffSeconds < 86400) return `${Math.round(diffSeconds / 3600)}h ago`;
      return formatTimestamp(value);
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }
  </script>
</body>
</html>
"""
