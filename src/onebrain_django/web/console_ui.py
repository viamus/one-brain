# ruff: noqa: E501

from __future__ import annotations

from onebrain_django.web.design_system import ONEBRAIN_DESIGN_SYSTEM_CSS


def console_view_html() -> str:
    return CONSOLE_UI_HTML.replace("__ONEBRAIN_DESIGN_SYSTEM_CSS__", ONEBRAIN_DESIGN_SYSTEM_CSS)


CONSOLE_UI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OneBrain Workbench</title>
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
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
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
      height: calc(100vh - 92px);
      min-height: 620px;
      border: 1px solid var(--ob-line);
      border-radius: var(--ob-radius-panel);
      background: var(--ob-canvas);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
    }

    .api-layout {
      height: calc(100vh - 92px);
      min-height: 620px;
      display: grid;
      grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
      gap: 12px;
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
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 12px;
    }

    .job-stack {
      display: grid;
      align-content: start;
      gap: 12px;
    }

    .metric-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }

    .metric-tile {
      border: 1px solid var(--ob-line);
      border-radius: var(--ob-radius-compact);
      background: var(--ob-panel);
      padding: 10px;
      min-height: 72px;
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
          <div class="ob-brand-subtitle">Memory graph workbench</div>
        </div>
      </div>

      <nav class="ob-nav" aria-label="Workbench">
        <button class="ob-nav-link" type="button" data-tab="graph" data-active="true">Graph</button>
        <button class="ob-nav-link" type="button" data-tab="api">Swagger</button>
        <button class="ob-nav-link" type="button" data-tab="jobs">Jobs</button>
      </nav>

      <div class="ob-sidebar-section">
        <span class="ob-section-title">Runtime</span>
        <div class="ob-kv">
          <span>Django</span>
          <strong>API + Web + MCP</strong>
        </div>
        <div class="ob-kv">
          <span>Graph</span>
          <strong>RAG guided</strong>
        </div>
        <div class="ob-kv">
          <span>Docs</span>
          <strong>OpenAPI 3.1</strong>
        </div>
      </div>
    </aside>

    <main class="workbench-main">
      <header class="ob-topbar">
        <div>
          <h1 class="ob-page-title">OneBrain Workbench</h1>
          <p class="ob-page-subtitle">Operational console for correlations, memory APIs, and aggregation jobs.</p>
        </div>
        <div class="ob-topbar-actions">
          <a class="ob-button ob-button-ghost" href="/graph">Open graph</a>
          <a class="ob-button ob-button-primary" href="/api/openapi.json">OpenAPI JSON</a>
        </div>
      </header>

      <section class="workbench-content">
        <section class="tab-panel" data-panel="graph" data-active="true">
          <iframe class="graph-frame" src="/graph" title="OneBrain graph"></iframe>
        </section>

        <section class="tab-panel" data-panel="api">
          <div class="api-layout">
            <aside class="ob-surface endpoint-list" id="endpointList" aria-label="API endpoints"></aside>
            <article class="ob-surface endpoint-details" id="endpointDetails">
              <div class="ob-empty-state">Loading Swagger/OpenAPI contract...</div>
            </article>
          </div>
        </section>

        <section class="tab-panel" data-panel="jobs">
          <div class="job-layout">
            <div class="job-stack">
              <section class="ob-surface ob-panel-block">
                <span class="ob-section-title">Graph Aggregation Job</span>
                <p class="ob-page-subtitle">Scheduled aggregation materializes strong grouping opportunities as context memories, then links members back to the aggregate.</p>
                <div class="metric-grid">
                  <div class="metric-tile">
                    <span class="metric-value">500</span>
                    <span class="metric-label">Default graph limit</span>
                  </div>
                  <div class="metric-tile">
                    <span class="metric-value">750</span>
                    <span class="metric-label">Correlation budget</span>
                  </div>
                  <div class="metric-tile">
                    <span class="metric-value">25</span>
                    <span class="metric-label">Grouping window</span>
                  </div>
                </div>
              </section>

              <section class="ob-surface ob-panel-block">
                <span class="ob-section-title">Schedule</span>
                <div class="command-box">onebrain-django run_scheduled_jobs --job graph-aggregation</div>
              </section>
            </div>

            <section class="ob-surface ob-panel-block">
              <span class="ob-section-title">Configuration</span>
              <div class="ob-kv">
                <span>Interval</span>
                <strong>ONEBRAIN_GRAPH_AGGREGATION_INTERVAL_SECONDS</strong>
              </div>
              <div class="ob-kv">
                <span>Scope</span>
                <strong>ONEBRAIN_GRAPH_AGGREGATION_SCOPE_JSON</strong>
              </div>
              <div class="ob-kv">
                <span>Degree</span>
                <strong>ONEBRAIN_GRAPH_AGGREGATION_MAX_DEGREE</strong>
              </div>
              <div class="ob-kv">
                <span>Min cluster</span>
                <strong>ONEBRAIN_GRAPH_AGGREGATION_GROUPING_MIN_SIZE</strong>
              </div>
            </section>
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
    let apiSpec = null;
    let selectedOperation = null;

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        tabs.forEach((item) => item.dataset.active = String(item === tab));
        panels.forEach((panel) => panel.dataset.active = String(panel.dataset.panel === target));
        if (target === "api" && !apiSpec) {
          loadApiSpec();
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
            <p class="operation-summary">${escapeHtml(entry.operation.description || "OneBrain Django API operation.")}</p>
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
