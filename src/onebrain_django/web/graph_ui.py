# ruff: noqa: E501

GRAPH_UI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OneBrain Correlations</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f8;
      --canvas: #eef2f5;
      --panel: #ffffff;
      --panel-strong: #eef1f3;
      --panel-float: rgba(255, 255, 255, 0.92);
      --control: #ffffff;
      --line: #d7dde2;
      --ink: #182027;
      --label: #182027;
      --muted: #64717d;
      --memory: #2d6f73;
      --context: #315f9f;
      --skill: #7a5cbd;
      --workflow: #b36b27;
      --entity: #315f9f;
      --fact: #4a7c96;
      --note: #697783;
      --edge: #81909c;
      --correlation: #8d7b4d;
      --node-stroke: #ffffff;
      --centroid: #c78213;
      --grouping: #108e8c;
      --focus: #0b6bcb;
      --focus-soft: rgba(11, 107, 203, 0.22);
      --danger: #b54137;
    }

    :root[data-theme="dark"] {
      color-scheme: dark;
      --bg: #0b1117;
      --canvas: #081018;
      --panel: #111923;
      --panel-strong: #16212d;
      --panel-float: rgba(17, 25, 35, 0.92);
      --control: #0d1520;
      --line: #2a3949;
      --ink: #edf3f7;
      --label: #f2f6fa;
      --muted: #9aaabb;
      --memory: #45a27c;
      --context: #7ea6de;
      --skill: #a78be7;
      --workflow: #df9448;
      --entity: #7ea6de;
      --fact: #82b8c9;
      --note: #8f9eac;
      --edge: #6f8294;
      --correlation: #d2ad55;
      --node-stroke: #111923;
      --centroid: #f0bd45;
      --grouping: #28beb8;
      --focus: #5da7f0;
      --focus-soft: rgba(93, 167, 240, 0.24);
      --danger: #ee786f;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      display: flex;
      flex-direction: column;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      min-height: 56px;
      padding: 10px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }

    h1 {
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
      font-weight: 700;
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
      border-bottom: 1px solid var(--line);
      background: var(--panel-strong);
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
      border-radius: 7px;
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
      border-radius: 7px;
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
      color: #ffffff;
    }

    button:focus,
    input:focus,
    select:focus {
      outline: 2px solid rgba(11, 107, 203, 0.24);
      outline-offset: 1px;
    }

    .workspace {
      flex: 1 1 auto;
      min-height: 440px;
    }

    .canvas-shell {
      position: relative;
      min-width: 0;
      height: 100%;
      background: var(--canvas);
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
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-float);
      backdrop-filter: blur(8px);
    }

    .metric {
      min-width: 92px;
      padding: 10px 12px;
      border-right: 1px solid var(--line);
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
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-float);
      color: var(--muted);
      font-size: 12px;
      backdrop-filter: blur(8px);
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
        <div class="metric"><strong id="edgeCount">0</strong><span>Correlations</span></div>
        <div class="metric"><strong id="memoryCount">0</strong><span>Memories</span></div>
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
    </section>
  </main>

  <script>
    const canvas = document.getElementById("graph");
    const ctx = canvas.getContext("2d");
    const statusEl = document.getElementById("status");
    const nodeCountEl = document.getElementById("nodeCount");
    const edgeCountEl = document.getElementById("edgeCount");
    const memoryCountEl = document.getElementById("memoryCount");
    const queryEl = document.getElementById("query");
    const typeEl = document.getElementById("type");
    const limitEl = document.getElementById("limit");
    const scopeEl = document.getElementById("scope");
    const correlationLimitEl = document.getElementById("correlationLimit");
    const maxDegreeEl = document.getElementById("maxDegree");
    const includeVectorEl = document.getElementById("includeVectorCorrelations");
    const nightModeEl = document.getElementById("nightMode");

    let graph = { nodes: [], edges: [], memory_count: 0 };
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
      fact: "--fact"
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
        max_correlation_degree: Number(maxDegreeEl.value || 6)
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
      setStatus(`Loaded ${graph.edges.length} correlations${hidden}`);
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
      const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
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
      const clusterRing = Math.max(210, Math.min(560, 150 + Math.sqrt(Math.max(1, nodes.length)) * 32));
      const positions = new Map();

      sortedGroups.forEach(([key, groupNodes], groupIndex) => {
        const singleGroup = sortedGroups.length === 1;
        const groupAngle = singleGroup
          ? -Math.PI / 2
          : -Math.PI / 2 + (Math.PI * 2 * groupIndex) / sortedGroups.length;
        const anchorX = centerX + (singleGroup ? 0 : Math.cos(groupAngle) * clusterRing);
        const anchorY = centerY + (singleGroup ? 0 : Math.sin(groupAngle) * clusterRing * 0.72);
        const localRing = Math.max(70, Math.min(230, 46 + Math.sqrt(groupNodes.length) * 26));
        const ordered = [...groupNodes].sort((left, right) => stableHash(left.id) - stableHash(right.id));

        ordered.forEach((node, nodeIndex) => {
          const seed = stableHash(`${key}:${node.id}`);
          const localAngle = -Math.PI / 2 + (Math.PI * 2 * nodeIndex) / Math.max(1, ordered.length);
          const jitter = ((seed % 100) / 100 - 0.5) * 28;
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
          const force = 2600 / distSq;
          const dist = Math.sqrt(distSq);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.fx -= fx;
          a.fy -= fy;
          b.fx += fx;
          b.fy += fy;

          const separation = a.radius + b.radius + 34;
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
        const desired = edge.edge_type === "correlation" ? 225 : 165;
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
          node.fx += (node.anchorX - node.x) * 0.0009;
          node.fy += (node.anchorY - node.y) * 0.0009;
        }
        node.fx += (centerX - node.x) * 0.00035;
        node.fy += (centerY - node.y) * 0.00035;
        node.vx = clamp((node.vx + node.fx) * 0.86, -7, 7);
        node.vy = clamp((node.vy + node.fy) * 0.86, -7, 7);
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
      ctx.fillStyle = cssVar("--canvas");
      ctx.fillRect(0, 0, rect.width, rect.height);
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

    function drawEdge(edge) {
      const a = edge.sourceNode;
      const b = edge.targetNode;
      if (!a || !b) return;
      const focused = edgeIsFocused(edge);
      const dimmed = Boolean(activeFocusItem()) && !focused;
      ctx.save();
      ctx.globalAlpha = dimmed ? 0.12 : focused ? 0.98 : 0.38;
      ctx.strokeStyle = focused ? cssVar("--focus") : edge.edge_type === "correlation" ? cssVar("--correlation") : cssVar("--edge");
      ctx.lineWidth = focused ? 3.2 : Math.max(0.7, edge.weight || 1);
      if (focused) {
        ctx.shadowColor = cssVar("--focus");
        ctx.shadowBlur = 14;
      }
      ctx.setLineDash(edge.edge_type === "correlation" ? [5, 5] : []);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      if (focused) {
        ctx.shadowBlur = 0;
        ctx.globalAlpha = 0.95;
        ctx.lineWidth = 1.2;
        ctx.strokeStyle = edge.edge_type === "correlation" ? cssVar("--correlation") : cssVar("--edge");
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
      ctx.fillStyle = color;
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
        ctx.font = primary ? "700 12px Inter, sans-serif" : "600 11px Inter, sans-serif";
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
        const degree = graphStats.degree ? ` (${graphStats.degree} links)` : "";
        setStatus(roleLabel ? `${item.label} - ${roleLabel}${degree}` : `${item.label}${degree}`);
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
    nightModeEl.addEventListener("change", applyTheme);
    queryEl.addEventListener("keydown", (event) => {
      if (event.key === "Enter") loadGraph();
    });

    window.addEventListener("resize", resize);
    nightModeEl.checked = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
    applyTheme();
    resize();
    loadGraph();
  </script>
</body>
</html>
"""


def graph_view_html() -> str:
    return GRAPH_UI_HTML
