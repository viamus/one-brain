# ruff: noqa: E501

from __future__ import annotations

from onebrain_django.web.design_system import ONEBRAIN_DESIGN_SYSTEM_CSS

GRAPH_UI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OneBrain Correlations</title>
  <style>
    __ONEBRAIN_DESIGN_SYSTEM_CSS__

    :root,
    :root[data-theme="dark"],
    :root[data-theme="light"] {
      color-scheme: dark;
      --bg: var(--ob-ink);
      --canvas: #090a09;
      --panel: var(--ob-panel);
      --panel-strong: var(--ob-panel-raised);
      --panel-float: rgba(18, 19, 17, 0.92);
      --control: var(--ob-control);
      --line: var(--ob-line);
      --ink: var(--ob-text);
      --label: var(--ob-text);
      --muted: var(--ob-muted);
      --memory: #45a27c;
      --context: var(--ob-blue);
      --skill: #b99df1;
      --workflow: var(--ob-tigerlily);
      --entity: var(--ob-blue);
      --fact: #82b8c9;
      --note: #a9a39a;
      --edge: #6f7569;
      --correlation: var(--ob-yellow);
      --node-stroke: var(--ob-panel);
      --centroid: var(--ob-tigerlily);
      --grouping: #28beb8;
      --grouping-soft: rgba(40, 190, 184, 0.14);
      --focus: var(--ob-tigerlily);
      --focus-soft: rgba(217, 119, 87, 0.22);
      --danger: var(--ob-red);
      --graph-grid: rgba(242, 239, 231, 0.035);
      --graph-grid-strong: rgba(217, 119, 87, 0.075);
      --graph-vignette: rgba(217, 119, 87, 0.08);
      --node-glint: rgba(242, 239, 231, 0.18);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 18% 0%, var(--graph-vignette), transparent 34rem),
        linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent 18rem),
        var(--bg);
      color: var(--ink);
      display: flex;
      flex-direction: column;
      font-family: "Segoe UI Variable", "Segoe UI", -apple-system, BlinkMacSystemFont, Inter, Roboto, Arial, sans-serif;
      letter-spacing: 0;
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      min-height: 56px;
      padding: 10px 18px;
      border-bottom: 1px solid color-mix(in srgb, var(--line) 72%, transparent);
      background: color-mix(in srgb, var(--ob-ink-2) 94%, transparent);
      backdrop-filter: blur(14px);
    }

    h1 {
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
      font-weight: 780;
    }

    .status {
      min-width: 160px;
      max-width: min(520px, 44vw);
      text-align: right;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .toolbar {
      display: flex;
      flex-wrap: wrap;
      align-items: end;
      gap: 10px;
      padding: 12px 18px;
      border-bottom: 1px solid color-mix(in srgb, var(--line) 72%, transparent);
      background: color-mix(in srgb, var(--panel-strong) 92%, transparent);
      box-shadow: inset 0 1px 0 rgba(242, 239, 231, 0.035);
    }

    .control {
      display: grid;
      gap: 4px;
      flex: 1 1 150px;
      min-width: 120px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }

    .control-query {
      flex: 2 1 260px;
    }

    .control-scope {
      flex: 1.4 1 230px;
    }

    .control-short {
      flex: 0 1 118px;
    }

    .toggle-control {
      min-height: 34px;
      display: inline-flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex: 0 0 auto;
      padding: 6px 10px;
      border: 1px solid var(--line);
      border-radius: var(--ob-radius-compact);
      background: var(--control);
      color: var(--ink);
      font-size: 13px;
      font-weight: 700;
      white-space: nowrap;
    }

    .toggle-control input {
      width: 17px;
      height: 17px;
      min-height: 17px;
      margin: 0;
      padding: 0;
      accent-color: var(--focus);
    }

    .toolbar-actions {
      display: inline-flex;
      gap: 8px;
      align-self: end;
    }

    input,
    select,
    button {
      min-height: 34px;
      border-radius: var(--ob-radius-compact);
      border: 1px solid var(--line);
      background: var(--control);
      color: var(--ink);
      font: inherit;
      font-size: 14px;
      letter-spacing: 0;
    }

    input,
    select {
      width: 100%;
      padding: 6px 9px;
    }

    button {
      align-self: end;
      padding: 0 12px;
      font-weight: 700;
      cursor: pointer;
    }

    button.primary {
      border-color: var(--focus);
      background: var(--focus);
      color: #151513;
    }

    button:focus,
    input:focus,
    select:focus {
      outline: 0;
      box-shadow: var(--ob-shadow-focus);
    }

    .workspace {
      flex: 1 1 auto;
      min-height: 440px;
    }

    .canvas-shell {
      position: relative;
      min-width: 0;
      height: 100%;
      background:
        radial-gradient(circle at 28% 12%, rgba(217, 119, 87, 0.08), transparent 28rem),
        var(--canvas);
      overflow: hidden;
    }

    canvas {
      display: block;
      width: 100%;
      height: 100%;
    }

    .metrics {
      position: absolute;
      z-index: 2;
      top: 12px;
      right: 12px;
      display: flex;
      overflow: hidden;
      border: 1px solid color-mix(in srgb, var(--line) 82%, transparent);
      border-radius: var(--ob-radius-panel);
      background: var(--panel-float);
      backdrop-filter: blur(8px);
      box-shadow: 0 18px 44px rgba(0, 0, 0, 0.24);
    }

    .metric {
      min-width: 92px;
      padding: 10px 12px;
      border-right: 1px solid color-mix(in srgb, var(--line) 72%, transparent);
    }

    .metric:last-child { border-right: 0; }

    .metric strong {
      display: block;
      font-size: 20px;
      line-height: 1;
    }

    .metric span {
      display: block;
      margin-top: 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }

    .legend {
      position: absolute;
      z-index: 3;
      top: 12px;
      left: 12px;
      display: grid;
      gap: 7px;
      width: min(280px, calc(100% - 24px));
      padding: 8px 10px;
      border: 1px solid color-mix(in srgb, var(--line) 82%, transparent);
      border-radius: var(--ob-radius-panel);
      background: var(--panel-float);
      color: var(--muted);
      font-size: 12px;
      backdrop-filter: blur(8px);
      box-shadow: 0 18px 44px rgba(0, 0, 0, 0.24);
    }

    .group-panel {
      position: absolute;
      z-index: 3;
      left: 12px;
      bottom: 12px;
      display: grid;
      gap: 8px;
      width: min(360px, calc(100% - 24px));
      max-height: min(340px, calc(100% - 120px));
      overflow: hidden;
      padding: 10px;
      border: 1px solid color-mix(in srgb, var(--line) 82%, transparent);
      border-radius: var(--ob-radius-panel);
      background: var(--panel-float);
      backdrop-filter: blur(8px);
      box-shadow: 0 18px 44px rgba(0, 0, 0, 0.24);
    }

    .group-panel[hidden] {
      display: none;
    }

    .group-panel-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      color: var(--ink);
      font-size: 12px;
      font-weight: 800;
    }

    .group-list {
      display: grid;
      gap: 6px;
      overflow: auto;
      padding-right: 2px;
    }

    .group-item {
      width: 100%;
      min-height: 0;
      display: grid;
      gap: 3px;
      padding: 8px;
      border: 1px solid color-mix(in srgb, var(--grouping) 34%, var(--line));
      border-radius: var(--ob-radius-compact);
      background: var(--grouping-soft);
      color: var(--ink);
      text-align: left;
    }

    .group-item strong {
      display: block;
      overflow: hidden;
      color: var(--ink);
      font-size: 12px;
      line-height: 1.2;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .group-item span {
      color: var(--muted);
      font-size: 11px;
      line-height: 1.25;
    }

    .legend-title {
      color: var(--ink);
      font-size: 12px;
      font-weight: 800;
    }

    .legend-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 10px;
    }

    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }

    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--edge);
    }

    .line-sample {
      width: 22px;
      height: 0;
      border-top: 2px solid var(--edge);
    }

    .line-sample.correlation {
      border-top-color: var(--correlation);
      border-top-style: dashed;
    }

    .ring-sample {
      width: 13px;
      height: 13px;
      border-radius: 50%;
      border: 2px solid var(--centroid);
      background: transparent;
    }

    .ring-sample.grouping {
      border-color: var(--grouping);
      border-style: dashed;
    }

    @media (max-width: 980px) {
      .metrics {
        right: 12px;
      }
    }

    @media (max-width: 760px) {
      .metrics {
        top: auto;
        right: 12px;
        bottom: 12px;
      }

      .metric {
        min-width: 76px;
        padding: 8px 9px;
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>OneBrain Correlations</h1>
    <div class="status" id="status">Idle</div>
  </header>

  <section class="toolbar" aria-label="Correlation filters">
    <label class="control control-query">Search
      <input id="query" type="search" autocomplete="off" placeholder="memory, skill, workflow">
    </label>
    <label class="control">Memory type
      <select id="type">
        <option value="">All</option>
        <option value="skill">Skill</option>
        <option value="workflow">Workflow</option>
        <option value="rule">Rule</option>
        <option value="decision">Decision</option>
        <option value="context">Context</option>
        <option value="fact">Fact</option>
        <option value="note">Note</option>
      </select>
    </label>
    <label class="control control-short">Memory limit
      <input id="limit" type="number" min="1" max="500" step="1" value="100">
    </label>
    <label class="control control-scope">Scope JSON
      <input id="scope" type="text" autocomplete="off" placeholder='{"project":"one-brain"}'>
    </label>
    <label class="control control-short">Correlation limit
      <input id="correlationLimit" type="number" min="0" max="2000" step="10" value="250">
    </label>
    <label class="control control-short">Max degree
      <input id="maxDegree" type="number" min="1" max="50" step="1" value="6">
    </label>
    <label class="toggle-control" title="Include vector-neighbor correlation edges">
      <span>Vector edges</span>
      <input id="includeVectorCorrelations" type="checkbox" checked>
    </label>
    <label class="toggle-control" title="Show detected grouping opportunity nodes">
      <span>Groups</span>
      <input id="includeGroupingOpportunities" type="checkbox" checked>
    </label>
    <label class="toggle-control" title="Use the dark graph theme">
      <span>Night mode</span>
      <input id="nightMode" type="checkbox">
    </label>
    <div class="toolbar-actions">
      <button class="primary" id="load">Load</button>
      <button id="spread">Spread</button>
      <button id="fit">Fit</button>
    </div>
  </section>

  <main class="workspace">
    <section class="canvas-shell">
      <canvas id="graph" aria-label="OneBrain correlation canvas"></canvas>
      <section class="metrics" aria-label="Graph metrics">
        <div class="metric"><strong id="nodeCount">0</strong><span>Nodes</span></div>
        <div class="metric"><strong id="edgeCount">0</strong><span>Edges</span></div>
        <div class="metric"><strong id="memoryCount">0</strong><span>Memories</span></div>
        <div class="metric"><strong id="groupCount">0</strong><span>Groups</span></div>
      </section>
      <div class="legend" aria-label="Color legend">
        <span class="legend-title">Legend</span>
        <div class="legend-grid">
          <span class="legend-item"><span class="dot" style="background: var(--memory)"></span>Memory</span>
          <span class="legend-item"><span class="dot" style="background: var(--context)"></span>Context</span>
          <span class="legend-item"><span class="dot" style="background: var(--skill)"></span>Skill</span>
          <span class="legend-item"><span class="dot" style="background: var(--workflow)"></span>Workflow</span>
          <span class="legend-item"><span class="dot" style="background: var(--fact)"></span>Fact</span>
          <span class="legend-item"><span class="dot" style="background: var(--note)"></span>Note</span>
          <span class="legend-item"><span class="line-sample correlation"></span>Correlation edge</span>
          <span class="legend-item"><span class="ring-sample"></span>Centroid candidate</span>
          <span class="legend-item"><span class="ring-sample grouping"></span>Grouping opportunity</span>
        </div>
      </div>
      <section class="group-panel" id="groupPanel" aria-label="Grouping opportunities" hidden>
        <div class="group-panel-head">
          <span>Grouping Opportunities</span>
          <span id="groupPanelCount">0</span>
        </div>
        <div class="group-list" id="groupList"></div>
      </section>
    </section>
  </main>

  <script>
    const canvas = document.getElementById("graph");
    const ctx = canvas.getContext("2d");
    const statusEl = document.getElementById("status");
    const nodeCountEl = document.getElementById("nodeCount");
    const edgeCountEl = document.getElementById("edgeCount");
    const memoryCountEl = document.getElementById("memoryCount");
    const groupCountEl = document.getElementById("groupCount");
    const groupPanelEl = document.getElementById("groupPanel");
    const groupPanelCountEl = document.getElementById("groupPanelCount");
    const groupListEl = document.getElementById("groupList");
    const queryEl = document.getElementById("query");
    const typeEl = document.getElementById("type");
    const limitEl = document.getElementById("limit");
    const scopeEl = document.getElementById("scope");
    const correlationLimitEl = document.getElementById("correlationLimit");
    const maxDegreeEl = document.getElementById("maxDegree");
    const includeVectorEl = document.getElementById("includeVectorCorrelations");
    const includeGroupingEl = document.getElementById("includeGroupingOpportunities");
    const nightModeEl = document.getElementById("nightMode");

    let graph = { nodes: [], edges: [], memory_count: 0, grouping_opportunities: [] };
    let nodeById = new Map();
    let transform = { x: 0, y: 0, scale: 1 };
    let pointer = { x: 0, y: 0 };
    let hover = null;
    let selected = null;
    let dragging = null;
    let panning = false;
    let lastPointer = null;
    let running = false;
    let animationFrameId = null;

    const colors = {
      memory: "--memory",
      skill: "--skill",
      workflow: "--workflow",
      entity: "--entity",
      rule: "--memory",
      decision: "--workflow",
      context: "--context",
      note: "--note",
      fact: "--fact",
      group: "--grouping",
      grouping: "--grouping"
    };

    function cssVar(name) {
      return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }

    function nodeColor(node) {
      return cssVar(colors[node.subtype] || colors[node.node_type] || "--memory");
    }

    function graphRole(node) {
      return node.metadata?.graph?.role || "";
    }

    function graphRoleLabel(role) {
      if (role === "centroid_candidate") return "Centroid candidate";
      if (role === "grouping_opportunity") return "Grouping opportunity";
      return "";
    }

    function graphRoleColor(role) {
      if (role === "centroid_candidate") return cssVar("--centroid");
      if (role === "grouping_opportunity") return cssVar("--grouping");
      return cssVar("--focus");
    }

    function resize() {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw();
    }

    function setStatus(value, isError = false) {
      statusEl.textContent = value;
      statusEl.style.color = isError ? "var(--danger)" : "var(--muted)";
    }

    function parseScope() {
      const text = scopeEl.value.trim();
      if (!text) return null;
      return JSON.parse(text);
    }

    function requestPayload() {
      const memoryType = typeEl.value;
      const filters = { statuses: ["active"] };
      const scope = parseScope();
      if (scope) filters.scope = scope;
      if (memoryType) filters.memory_types = [memoryType];
      return {
        query: queryEl.value.trim() || null,
        limit: Number(limitEl.value || 100),
        filters,
        include_entities: false,
        include_relations: false,
        include_correlations: true,
        include_vector_correlations: includeVectorEl.checked,
        correlation_limit: Number(correlationLimitEl.value || 250),
        max_correlation_degree: Number(maxDegreeEl.value || 6),
        include_grouping_opportunities: includeGroupingEl.checked,
        grouping_limit: 8,
        grouping_min_size: 3
      };
    }

    async function loadGraph() {
      try {
        setStatus("Loading");
        const headers = { "Content-Type": "application/json" };
        const response = await fetch("/graph/data", {
          method: "POST",
          headers,
          body: JSON.stringify(requestPayload())
        });
        if (!response.ok) {
          throw new Error(await responseErrorMessage(response));
        }
        const previousPositions = new Map(graph.nodes.map((node) => [
          node.id,
          { x: node.x, y: node.y, vx: node.vx, vy: node.vy }
        ]));
        graph = await response.json();
        hydrateGraph(previousPositions);
        fitGraph();
        nodeCountEl.textContent = graph.nodes.length;
        edgeCountEl.textContent = graph.edges.length;
        memoryCountEl.textContent = graph.memory_count;
        groupCountEl.textContent = (graph.grouping_opportunities || []).length;
        renderGroupingOpportunities();
        setLoadedStatus();
      } catch (error) {
        setStatus(error.message, true);
      }
    }

    async function responseErrorMessage(response) {
      if (response.status === 401) return "API key required";
      if (response.status === 403) return "API key rejected";
      try {
        const payload = await response.json();
        if (payload.detail) return `${response.status} ${payload.detail}`;
      } catch {
        return `${response.status} ${response.statusText}`;
      }
      return `${response.status} ${response.statusText}`;
    }

    function setLoadedStatus() {
      const hidden = graph.omitted ? `; ${graph.omitted} raw file sections hidden` : "";
      const groups = (graph.grouping_opportunities || []).length;
      const groupText = groups ? `; ${groups} grouping opportunities` : "";
      setStatus(`Loaded ${graph.edges.length} correlations${groupText}${hidden}`);
    }

    function hydrateGraph(previousPositions = new Map()) {
      const rect = canvas.getBoundingClientRect();
      const layout = layoutGraphPositions(graph.nodes, rect);
      for (const node of graph.nodes) {
        const previous = previousPositions.get(node.id);
        const planned = layout.get(node.id) || { x: rect.width / 2, y: rect.height / 2 };
        node.x = Number.isFinite(previous?.x) ? previous.x : planned.x;
        node.y = Number.isFinite(previous?.y) ? previous.y : planned.y;
        node.vx = Number.isFinite(previous?.vx) ? previous.vx * 0.2 : 0;
        node.vy = Number.isFinite(previous?.vy) ? previous.vy * 0.2 : 0;
        node.anchorX = planned.anchorX;
        node.anchorY = planned.anchorY;
        node.radius = nodeRadius(node);
        node.degree = 0;
      }
      nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
      graph.edges = graph.edges.filter((edge) => nodeById.has(edge.source) && nodeById.has(edge.target));
      for (const edge of graph.edges) {
        edge.sourceNode = nodeById.get(edge.source);
        edge.targetNode = nodeById.get(edge.target);
        edge.sourceNode.degree += 1;
        edge.targetNode.degree += 1;
      }
      selected = null;
      hover = null;
      startSimulation();
    }

    function renderGroupingOpportunities() {
      const groups = graph.grouping_opportunities || [];
      groupPanelEl.hidden = !groups.length;
      groupPanelCountEl.textContent = groups.length;
      groupListEl.replaceChildren();
      for (const group of groups) {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "group-item";
        item.dataset.groupNodeId = `group:${group.id}`;
        const title = document.createElement("strong");
        title.textContent = group.label;
        const meta = document.createElement("span");
        meta.textContent = `${group.member_count} memories - score ${Number(group.score || 0).toFixed(1)} - cohesion ${Number(group.cohesion || 0).toFixed(2)}`;
        item.append(title, meta);
        item.addEventListener("click", () => {
          const node = nodeById.get(item.dataset.groupNodeId);
          if (node) selectItem(node);
        });
        groupListEl.append(item);
      }
    }

    function layoutGraphPositions(nodes, rect) {
      const groups = new Map();
      for (const node of nodes) {
        const key = layoutGroup(node);
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(node);
      }

      const sortedGroups = Array.from(groups.entries()).sort(([left], [right]) => left.localeCompare(right));
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const clusterRing = Math.max(260, Math.min(720, 180 + Math.sqrt(Math.max(1, nodes.length)) * 42));
      const positions = new Map();

      sortedGroups.forEach(([key, groupNodes], groupIndex) => {
        const singleGroup = sortedGroups.length === 1;
        const groupAngle = singleGroup
          ? -Math.PI / 2
          : -Math.PI / 2 + (Math.PI * 2 * groupIndex) / sortedGroups.length;
        const anchorX = centerX + (singleGroup ? 0 : Math.cos(groupAngle) * clusterRing);
        const anchorY = centerY + (singleGroup ? 0 : Math.sin(groupAngle) * clusterRing * 0.72);
        const localRing = Math.max(100, Math.min(320, 64 + Math.sqrt(groupNodes.length) * 34));
        const ordered = [...groupNodes].sort((left, right) => stableHash(left.id) - stableHash(right.id));

        ordered.forEach((node, nodeIndex) => {
          const seed = stableHash(`${key}:${node.id}`);
          const localAngle = -Math.PI / 2 + (Math.PI * 2 * nodeIndex) / Math.max(1, ordered.length);
          const jitter = ((seed % 100) / 100 - 0.5) * 44;
          const distance = ordered.length === 1 ? 0 : localRing + jitter;
          positions.set(node.id, {
            x: anchorX + Math.cos(localAngle) * distance,
            y: anchorY + Math.sin(localAngle) * distance * 0.78,
            anchorX,
            anchorY
          });
        });
      });

      return positions;
    }

    function layoutGroup(node) {
      const role = graphRole(node);
      if (role === "centroid_candidate") return "01-centroid";
      if (role === "grouping_opportunity") return "02-grouping";
      if (node.node_type === "group") return "02-grouping";
      return `${node.node_type}:${node.subtype || "memory"}`;
    }

    function stableHash(value) {
      let hash = 0;
      const text = String(value || "");
      for (let index = 0; index < text.length; index += 1) {
        hash = (hash * 31 + text.charCodeAt(index)) >>> 0;
      }
      return hash;
    }

    function nodeRadius(node) {
      const base = node.node_type === "entity" ? 8 : 10;
      const bonus = node.subtype === "skill" ? 4 : node.subtype === "workflow" ? 3 : 0;
      return base + bonus + Math.min(6, Math.round((node.weight || 1) * 4));
    }

    function startSimulation() {
      if (animationFrameId !== null) {
        cancelAnimationFrame(animationFrameId);
      }
      running = true;
      animationFrameId = requestAnimationFrame(tick);
    }

    function tick() {
      animationFrameId = null;
      if (!running) return;
      simulate();
      draw();
      animationFrameId = requestAnimationFrame(tick);
    }

    function simulate() {
      const nodes = graph.nodes;
      const edges = graph.edges;
      if (!nodes.length) return;
      for (const node of nodes) {
        node.fx = 0;
        node.fy = 0;
      }

      for (let i = 0; i < nodes.length; i += 1) {
        for (let j = i + 1; j < nodes.length; j += 1) {
          const a = nodes[i];
          const b = nodes[j];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const distSq = Math.max(100, dx * dx + dy * dy);
          const force = 4300 / distSq;
          const dist = Math.sqrt(distSq);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.fx -= fx;
          a.fy -= fy;
          b.fx += fx;
          b.fy += fy;

          const separation = a.radius + b.radius + 48;
          if (dist < separation) {
            const collision = (separation - dist) * 0.045;
            const cx = (dx / dist) * collision;
            const cy = (dy / dist) * collision;
            a.fx -= cx;
            a.fy -= cy;
            b.fx += cx;
            b.fy += cy;
          }
        }
      }

      for (const edge of edges) {
        const a = edge.sourceNode;
        const b = edge.targetNode;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
        const desired = edge.edge_type === "correlation" ? 270 : edge.edge_type === "group_member" ? 190 : 205;
        const weight = Math.max(0.35, Math.min(1.35, edge.weight || 1));
        const force = (dist - desired) * 0.0026 * weight;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.fx += fx;
        a.fy += fy;
        b.fx -= fx;
        b.fy -= fy;
      }

      const rect = canvas.getBoundingClientRect();
      const centerX = (rect.width / 2 - transform.x) / transform.scale;
      const centerY = (rect.height / 2 - transform.y) / transform.scale;
      for (const node of nodes) {
        if (node === dragging) continue;
        if (Number.isFinite(node.anchorX) && Number.isFinite(node.anchorY)) {
          node.fx += (node.anchorX - node.x) * 0.0015;
          node.fy += (node.anchorY - node.y) * 0.0015;
        }
        node.fx += (centerX - node.x) * 0.00012;
        node.fy += (centerY - node.y) * 0.00012;
        node.vx = clamp((node.vx + node.fx) * 0.84, -7, 7);
        node.vy = clamp((node.vy + node.fy) * 0.84, -7, 7);
        node.x += node.vx;
        node.y += node.vy;
      }
    }

    function clamp(value, min, max) {
      return Math.max(min, Math.min(max, value));
    }

    function activeFocusItem() {
      return selected || hover;
    }

    function edgeIsFocused(edge) {
      const item = activeFocusItem();
      if (!item) return false;
      if (item.node_type) {
        return edge.sourceNode === item || edge.targetNode === item;
      }
      return edge === item;
    }

    function nodeIsFocused(node) {
      const item = activeFocusItem();
      if (!item) return false;
      if (item.node_type) {
        if (node === item) return true;
        return graph.edges.some((edge) => edgeIsFocused(edge) && (edge.sourceNode === node || edge.targetNode === node));
      }
      return item.sourceNode === node || item.targetNode === node;
    }

    function nodeIsPrimaryFocus(node) {
      const item = activeFocusItem();
      return Boolean(item?.node_type && item === node);
    }

    function draw() {
      const rect = canvas.getBoundingClientRect();
      ctx.clearRect(0, 0, rect.width, rect.height);
      drawCanvasBackground(rect);
      ctx.save();
      ctx.translate(transform.x, transform.y);
      ctx.scale(transform.scale, transform.scale);

      for (const edge of graph.edges) {
        if (!edgeIsFocused(edge)) drawEdge(edge);
      }
      for (const edge of graph.edges) {
        if (edgeIsFocused(edge)) drawEdge(edge);
      }
      for (const node of graph.nodes) drawNode(node);

      ctx.restore();
    }

    function drawCanvasBackground(rect) {
      ctx.fillStyle = cssVar("--canvas");
      ctx.fillRect(0, 0, rect.width, rect.height);
      drawGrid(rect, 32, cssVar("--graph-grid"), 0.8);
      drawGrid(rect, 128, cssVar("--graph-grid-strong"), 1);
      const glow = ctx.createRadialGradient(rect.width * 0.22, rect.height * 0.14, 0, rect.width * 0.22, rect.height * 0.14, Math.max(rect.width, rect.height) * 0.55);
      glow.addColorStop(0, cssVar("--graph-vignette"));
      glow.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, rect.width, rect.height);
    }

    function drawGrid(rect, size, color, width) {
      const offsetX = ((transform.x % size) + size) % size;
      const offsetY = ((transform.y % size) + size) % size;
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();
      for (let x = offsetX; x < rect.width; x += size) {
        ctx.moveTo(x, 0);
        ctx.lineTo(x, rect.height);
      }
      for (let y = offsetY; y < rect.height; y += size) {
        ctx.moveTo(0, y);
        ctx.lineTo(rect.width, y);
      }
      ctx.stroke();
      ctx.restore();
    }

    function drawEdge(edge) {
      const a = edge.sourceNode;
      const b = edge.targetNode;
      if (!a || !b) return;
      const focused = edgeIsFocused(edge);
      const dimmed = Boolean(activeFocusItem()) && !focused;
      ctx.save();
      ctx.globalAlpha = dimmed ? 0.12 : focused ? 0.98 : 0.38;
      ctx.strokeStyle = focused ? cssVar("--focus") : edge.edge_type === "correlation" ? cssVar("--correlation") : edge.edge_type === "group_member" ? cssVar("--grouping") : cssVar("--edge");
      ctx.lineWidth = focused ? 3.2 : Math.max(0.7, edge.weight || 1);
      if (focused) {
        ctx.shadowColor = cssVar("--focus");
        ctx.shadowBlur = 14;
      }
      ctx.setLineDash(edge.edge_type === "correlation" ? [5, 5] : edge.edge_type === "group_member" ? [2, 4] : []);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      if (focused) {
        ctx.shadowBlur = 0;
        ctx.globalAlpha = 0.95;
        ctx.lineWidth = 1.2;
        ctx.strokeStyle = edge.edge_type === "correlation" ? cssVar("--correlation") : edge.edge_type === "group_member" ? cssVar("--grouping") : cssVar("--edge");
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
      ctx.restore();
    }

    function drawNode(node) {
      const color = nodeColor(node);
      const role = graphRole(node);
      const primary = nodeIsPrimaryFocus(node);
      const focused = nodeIsFocused(node);
      const dimmed = Boolean(activeFocusItem()) && !focused;
      ctx.save();
      if (primary || focused) {
        ctx.shadowColor = primary ? cssVar("--focus") : cssVar("--focus-soft");
        ctx.shadowBlur = primary ? 20 : 10;
      }
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      const fill = ctx.createRadialGradient(node.x - node.radius * 0.35, node.y - node.radius * 0.45, node.radius * 0.15, node.x, node.y, node.radius);
      fill.addColorStop(0, cssVar("--node-glint"));
      fill.addColorStop(0.38, color);
      fill.addColorStop(1, color);
      ctx.fillStyle = fill;
      ctx.globalAlpha = dimmed ? 0.32 : primary ? 1 : focused ? 0.96 : 0.88;
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.lineWidth = primary ? 3.2 : focused ? 2.2 : 1;
      ctx.strokeStyle = primary ? cssVar("--focus") : focused ? cssVar("--ink") : cssVar("--node-stroke");
      ctx.stroke();

      if (role) {
        ctx.globalAlpha = dimmed ? 0.26 : primary ? 1 : 0.88;
        ctx.lineWidth = primary ? 3.2 : 2.3;
        ctx.strokeStyle = graphRoleColor(role);
        ctx.setLineDash(role === "grouping_opportunity" ? [5, 4] : []);
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius + 5, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
        if (role === "centroid_candidate") {
          ctx.globalAlpha = primary ? 0.55 : dimmed ? 0.18 : 0.35;
          ctx.beginPath();
          ctx.arc(node.x, node.y, node.radius + 8, 0, Math.PI * 2);
          ctx.stroke();
        }
      }

      if (transform.scale > 0.55 || focused) {
        ctx.font = primary ? "760 12px Segoe UI, sans-serif" : "650 11px Segoe UI, sans-serif";
        ctx.fillStyle = cssVar("--label");
        ctx.globalAlpha = dimmed ? 0.34 : primary ? 1 : 0.84;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        wrapLabel(node.label, node.x, node.y + node.radius + 4, primary ? 140 : 100);
      }
      ctx.restore();
    }

    function wrapLabel(label, x, y, maxWidth) {
      const words = String(label || "").split(/\\s+/).slice(0, 8);
      let line = "";
      let lineY = y;
      for (const word of words) {
        const test = line ? `${line} ${word}` : word;
        if (ctx.measureText(test).width > maxWidth && line) {
          ctx.fillText(line, x, lineY);
          line = word;
          lineY += 13;
        } else {
          line = test;
        }
      }
      if (line) ctx.fillText(line, x, lineY);
    }

    function fitGraph() {
      if (!graph.nodes.length) {
        transform = { x: 0, y: 0, scale: 1 };
        draw();
        return;
      }
      const rect = canvas.getBoundingClientRect();
      const xs = graph.nodes.map((node) => node.x);
      const ys = graph.nodes.map((node) => node.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const padding = Math.max(220, Math.min(rect.width, rect.height) * 0.18);
      const width = Math.max(1, maxX - minX + padding);
      const height = Math.max(1, maxY - minY + padding);
      const scale = Math.min(1.15, Math.max(0.18, Math.min(rect.width / width, rect.height / height)));
      transform = {
        scale,
        x: rect.width / 2 - ((minX + maxX) / 2) * scale,
        y: rect.height / 2 - ((minY + maxY) / 2) * scale
      };
      draw();
    }

    function spreadGraph() {
      if (!graph.nodes.length) return;
      const rect = canvas.getBoundingClientRect();
      const layout = layoutGraphPositions(graph.nodes, rect);
      for (const node of graph.nodes) {
        const planned = layout.get(node.id);
        if (!planned) continue;
        node.x = planned.x;
        node.y = planned.y;
        node.anchorX = planned.anchorX;
        node.anchorY = planned.anchorY;
        node.vx = 0;
        node.vy = 0;
      }
      startSimulation();
      fitGraph();
    }

    function screenToWorld(point) {
      return {
        x: (point.x - transform.x) / transform.scale,
        y: (point.y - transform.y) / transform.scale
      };
    }

    function pickNode(world) {
      for (let i = graph.nodes.length - 1; i >= 0; i -= 1) {
        const node = graph.nodes[i];
        const dx = world.x - node.x;
        const dy = world.y - node.y;
        if (Math.sqrt(dx * dx + dy * dy) <= node.radius + 4) return node;
      }
      return null;
    }

    function pickEdge(world) {
      let closest = null;
      let closestDistance = 8 / transform.scale;
      for (const edge of graph.edges) {
        const distance = distanceToSegment(world, edge.sourceNode, edge.targetNode);
        if (distance < closestDistance) {
          closest = edge;
          closestDistance = distance;
        }
      }
      return closest;
    }

    function distanceToSegment(point, a, b) {
      if (!a || !b) return Infinity;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const lengthSq = dx * dx + dy * dy || 1;
      const t = Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / lengthSq));
      const x = a.x + t * dx;
      const y = a.y + t * dy;
      return Math.hypot(point.x - x, point.y - y);
    }

    function selectItem(item) {
      selected = item;
      if (!item) {
        setLoadedStatus();
        draw();
        return;
      }
      if (item.node_type) {
        const role = graphRole(item);
        const roleLabel = graphRoleLabel(role);
        const graphStats = item.metadata?.graph || {};
        if (item.node_type === "group") {
          const memberCount = graphStats.member_count || item.metadata?.grouping?.member_count || 0;
          const cohesion = Number(graphStats.cohesion || 0).toFixed(2);
          setStatus(`${item.label} - ${memberCount} memories; cohesion ${cohesion}`);
          draw();
          return;
        }
        const degree = graphStats.degree ? ` (${graphStats.degree} links)` : "";
        setStatus(roleLabel ? `${item.label} - ${roleLabel}${degree}` : `${item.label}${degree}`);
        draw();
        return;
      }
      if (item.edge_type === "group_member") {
        setStatus("Grouping membership");
        draw();
        return;
      }
      const shared = item.metadata?.shared_entities || [];
      const facets = item.metadata?.shared_facets || [];
      const reasons = shared.length ? shared : facets;
      setStatus(reasons.length ? `Correlation: ${reasons.slice(0, 3).join(", ")}` : "Correlation");
      draw();
    }

    function applyTheme() {
      document.documentElement.dataset.theme = nightModeEl.checked ? "dark" : "light";
      draw();
    }

    canvas.addEventListener("pointerdown", (event) => {
      canvas.setPointerCapture(event.pointerId);
      const rect = canvas.getBoundingClientRect();
      pointer = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      const world = screenToWorld(pointer);
      dragging = pickNode(world);
      if (dragging) {
        selectItem(dragging);
      } else {
        panning = true;
        selectItem(pickEdge(world));
      }
      lastPointer = pointer;
    });

    canvas.addEventListener("pointermove", (event) => {
      const rect = canvas.getBoundingClientRect();
      pointer = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      const world = screenToWorld(pointer);
      if (dragging) {
        dragging.x = world.x;
        dragging.y = world.y;
        dragging.vx = 0;
        dragging.vy = 0;
      } else if (panning && lastPointer) {
        transform.x += pointer.x - lastPointer.x;
        transform.y += pointer.y - lastPointer.y;
      } else {
        hover = pickNode(world) || pickEdge(world);
      }
      lastPointer = pointer;
      draw();
    });

    canvas.addEventListener("pointerup", () => {
      dragging = null;
      panning = false;
      lastPointer = null;
    });

    canvas.addEventListener("pointerleave", () => {
      if (!selected) {
        hover = null;
        draw();
      }
    });

    canvas.addEventListener("wheel", (event) => {
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const point = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      const before = screenToWorld(point);
      const factor = event.deltaY < 0 ? 1.08 : 0.92;
      transform.scale = Math.max(0.18, Math.min(3.5, transform.scale * factor));
      transform.x = point.x - before.x * transform.scale;
      transform.y = point.y - before.y * transform.scale;
      draw();
    }, { passive: false });

    document.getElementById("load").addEventListener("click", loadGraph);
    document.getElementById("spread").addEventListener("click", spreadGraph);
    document.getElementById("fit").addEventListener("click", fitGraph);
    includeVectorEl.addEventListener("change", loadGraph);
    includeGroupingEl.addEventListener("change", loadGraph);
    nightModeEl.addEventListener("change", applyTheme);
    queryEl.addEventListener("keydown", (event) => {
      if (event.key === "Enter") loadGraph();
    });

    window.addEventListener("resize", resize);
    nightModeEl.checked = true;
    applyTheme();
    resize();
    loadGraph();
  </script>
</body>
</html>
"""


def graph_view_html() -> str:
    return GRAPH_UI_HTML.replace("__ONEBRAIN_DESIGN_SYSTEM_CSS__", ONEBRAIN_DESIGN_SYSTEM_CSS)
