import {
  AccountTree,
  Analytics,
  Hub,
  JoinInner,
  Refresh,
  Search,
  Storage,
  Timeline,
  Tune
} from "@mui/icons-material";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  CircularProgress,
  Container,
  Divider,
  FormControlLabel,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  Slider,
  Stack,
  Tab,
  Tabs,
  TextField,
  Toolbar,
  Tooltip,
  Typography
} from "@mui/material";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Panel,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useState, type ReactElement, type ReactNode } from "react";
import "@xyflow/react/dist/style.css";

import { fetchGraph, fetchJobStatus, type GraphQuery } from "./api";
import type { GraphEdge, GraphNode, GraphResponse, JobStatus } from "./types";

const memoryTypes = [
  "",
  "context",
  "skill",
  "workflow",
  "rule",
  "decision",
  "runbook",
  "fact",
  "note"
];

const initialGraph: GraphResponse = {
  query: null,
  nodes: [],
  edges: [],
  memory_count: 0,
  entity_count: 0,
  omitted: 0,
  grouping_opportunities: []
};

type TabValue = "graph" | "jobs" | "storage";
type GraphSelection = { type: "node" | "edge"; id: string } | null;

export function App() {
  const [tab, setTab] = useState<TabValue>(() =>
    window.location.pathname.includes("graph") ? "graph" : "graph"
  );
  const [query, setQuery] = useState("onebrain");
  const [memoryType, setMemoryType] = useState("");
  const [limit, setLimit] = useState(160);
  const [correlationLimit, setCorrelationLimit] = useState(300);
  const [maxDegree, setMaxDegree] = useState(8);
  const [graph, setGraph] = useState<GraphResponse>(initialGraph);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [loadingGraph, setLoadingGraph] = useState(false);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const graphQuery = useMemo<GraphQuery>(
    () => ({ query, memoryType, limit, correlationLimit, maxDegree }),
    [correlationLimit, limit, maxDegree, memoryType, query]
  );

  const loadGraph = useCallback(async () => {
    setLoadingGraph(true);
    setError(null);
    try {
      setGraph(await fetchGraph(graphQuery));
    } catch (currentError) {
      setError(currentError instanceof Error ? currentError.message : String(currentError));
    } finally {
      setLoadingGraph(false);
    }
  }, [graphQuery]);

  const loadJobs = useCallback(async () => {
    setLoadingJobs(true);
    setError(null);
    try {
      setJobStatus(await fetchJobStatus());
    } catch (currentError) {
      setError(currentError instanceof Error ? currentError.message : String(currentError));
    } finally {
      setLoadingJobs(false);
    }
  }, []);

  useEffect(() => {
    void loadGraph();
    void loadJobs();
  }, [loadGraph, loadJobs]);

  return (
    <Box className="app-shell">
      <AppBar position="sticky" color="inherit" elevation={0} className="top-bar">
        <Toolbar className="top-toolbar">
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Box className="brand-mark">
              <AccountTree fontSize="small" />
            </Box>
            <Box>
              <Typography component="h1" variant="h1">
                OneBrain Web
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Graph, jobs and vector memory operations
              </Typography>
            </Box>
          </Stack>
          <Tabs
            value={tab}
            onChange={(_, value) => setTab(value)}
            aria-label="OneBrain sections"
            className="section-tabs"
          >
            <Tab icon={<AccountTree />} iconPosition="start" value="graph" label="Graph" />
            <Tab icon={<Analytics />} iconPosition="start" value="jobs" label="Jobs" />
            <Tab icon={<Storage />} iconPosition="start" value="storage" label="Storage" />
          </Tabs>
        </Toolbar>
      </AppBar>

      <Container maxWidth={false} className="main-container">
        {error ? (
          <Alert severity="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        ) : null}

        {tab === "graph" ? (
          <GraphPanel
            graph={graph}
            loading={loadingGraph}
            query={query}
            memoryType={memoryType}
            limit={limit}
            correlationLimit={correlationLimit}
            maxDegree={maxDegree}
            onQueryChange={setQuery}
            onMemoryTypeChange={setMemoryType}
            onLimitChange={setLimit}
            onCorrelationLimitChange={setCorrelationLimit}
            onMaxDegreeChange={setMaxDegree}
            onRefresh={loadGraph}
          />
        ) : null}

        {tab === "jobs" ? (
          <JobsPanel jobStatus={jobStatus} loading={loadingJobs} onRefresh={loadJobs} />
        ) : null}

        {tab === "storage" ? (
          <StoragePanel graph={graph} jobStatus={jobStatus} />
        ) : null}
      </Container>
    </Box>
  );
}

type GraphPanelProps = {
  graph: GraphResponse;
  loading: boolean;
  query: string;
  memoryType: string;
  limit: number;
  correlationLimit: number;
  maxDegree: number;
  onQueryChange: (value: string) => void;
  onMemoryTypeChange: (value: string) => void;
  onLimitChange: (value: number) => void;
  onCorrelationLimitChange: (value: number) => void;
  onMaxDegreeChange: (value: number) => void;
  onRefresh: () => void;
};

function GraphPanel(props: GraphPanelProps) {
  const [selection, setSelection] = useState<GraphSelection>(null);

  useEffect(() => {
    setSelection(null);
  }, [props.graph]);

  const summaryChips = [
    ["Nodes", props.graph.nodes.length],
    ["Edges", props.graph.edges.length],
    ["Memories", props.graph.memory_count],
    ["Groups", props.graph.grouping_opportunities.length]
  ];

  return (
    <Grid container spacing={2.5}>
      <Grid size={{ xs: 12, lg: 3 }}>
        <Stack spacing={2}>
          <Card>
            <CardContent>
              <Stack spacing={2}>
                <Stack direction="row" alignItems="center" spacing={1}>
                  <Tune color="primary" />
                  <Typography component="h2" variant="h2">
                    Graph Query
                  </Typography>
                </Stack>
                <TextField
                  label="Search"
                  value={props.query}
                  onChange={(event) => props.onQueryChange(event.target.value)}
                  size="small"
                  fullWidth
                />
                <FormControl fullWidth size="small">
                  <InputLabel id="memory-type-label">Type</InputLabel>
                  <Select
                    labelId="memory-type-label"
                    label="Type"
                    value={props.memoryType}
                    onChange={(event) => props.onMemoryTypeChange(event.target.value)}
                  >
                    {memoryTypes.map((type) => (
                      <MenuItem key={type || "all"} value={type}>
                        {type || "All"}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <NumberSlider
                  label="Limit"
                  value={props.limit}
                  min={25}
                  max={500}
                  step={25}
                  onChange={props.onLimitChange}
                />
                <NumberSlider
                  label="Correlations"
                  value={props.correlationLimit}
                  min={0}
                  max={2000}
                  step={50}
                  onChange={props.onCorrelationLimitChange}
                />
                <NumberSlider
                  label="Max degree"
                  value={props.maxDegree}
                  min={1}
                  max={50}
                  step={1}
                  onChange={props.onMaxDegreeChange}
                />
                <Tooltip title="Refresh graph">
                  <Button
                    variant="contained"
                    startIcon={props.loading ? <CircularProgress size={16} /> : <Search />}
                    onClick={props.onRefresh}
                    disabled={props.loading}
                    fullWidth
                  >
                    Query
                  </Button>
                </Tooltip>
              </Stack>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Stack spacing={1.25}>
                <Typography component="h2" variant="h2">
                  Summary
                </Typography>
                <Stack direction="row" flexWrap="wrap" gap={1}>
                  {summaryChips.map(([label, value]) => (
                    <Chip key={label} label={`${label}: ${value}`} size="small" />
                  ))}
                </Stack>
              </Stack>
            </CardContent>
          </Card>
        </Stack>
      </Grid>
      <Grid size={{ xs: 12, lg: 6 }}>
        <Card className="graph-card">
          <LiveGraph graph={props.graph} selection={selection} onSelectionChange={setSelection} />
        </Card>
      </Grid>
      <Grid size={{ xs: 12, lg: 3 }}>
        <GraphInsights
          graph={props.graph}
          selection={selection}
          onSelectNode={(id) => setSelection({ type: "node", id })}
          onSelectEdge={(id) => setSelection({ type: "edge", id })}
        />
      </Grid>
    </Grid>
  );
}

type NumberSliderProps = {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
};

function NumberSlider({ label, value, min, max, step, onChange }: NumberSliderProps) {
  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="body2">{label}</Typography>
        <Typography variant="body2" color="text.secondary">
          {value}
        </Typography>
      </Stack>
      <Slider
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(_, nextValue) => onChange(Array.isArray(nextValue) ? nextValue[0] : nextValue)}
        size="small"
      />
    </Box>
  );
}

type EdgeKind = "vector" | "correlation" | "entity" | "explicit" | "other";
type FlowNodeData = {
  label: string;
  node: GraphNode;
  role: string;
  accent: string;
  groupLabels: string[];
  [key: string]: unknown;
};
type FlowEdgeData = {
  edge: GraphEdge;
  kind: EdgeKind;
  [key: string]: unknown;
};
type MemoryFlowNode = Node<FlowNodeData>;
type MemoryFlowEdge = Edge<FlowEdgeData>;

const edgeLegend: Record<EdgeKind, { label: string; color: string; icon: ReactElement }> = {
  vector: { label: "Vector", color: "#6b4eff", icon: <Timeline fontSize="small" /> },
  correlation: { label: "Correlation", color: "#0f766e", icon: <JoinInner fontSize="small" /> },
  entity: { label: "Entity", color: "#b7791f", icon: <Hub fontSize="small" /> },
  explicit: { label: "Explicit", color: "#d04437", icon: <AccountTree fontSize="small" /> },
  other: { label: "Other", color: "#64748b", icon: <AccountTree fontSize="small" /> }
};

const graphNodeTypes = {
  memory: MemoryGraphNode
};

function LiveGraph({
  graph,
  selection,
  onSelectionChange
}: {
  graph: GraphResponse;
  selection: GraphSelection;
  onSelectionChange: (selection: GraphSelection) => void;
}) {
  const [enabledEdges, setEnabledEdges] = useState<Record<EdgeKind, boolean>>({
    vector: true,
    correlation: true,
    entity: true,
    explicit: true,
    other: true
  });
  const initialNodes = useMemo(() => buildFlowNodes(graph), [graph]);
  const initialEdges = useMemo(
    () => buildFlowEdges(graph.edges).filter((edge) => enabledEdges[edge.data?.kind || "other"]),
    [enabledEdges, graph.edges]
  );
  const [nodes, setNodes, onNodesChange] = useNodesState<MemoryFlowNode>(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<MemoryFlowEdge>(initialEdges);

  useEffect(() => {
    setNodes((currentNodes) => {
      const currentPositions = new Map(currentNodes.map((node) => [node.id, node.position]));
      return initialNodes.map((node) => ({
        ...node,
        position: currentPositions.get(node.id) || node.position,
        selected: selection?.type === "node" && selection.id === node.id
      }));
    });
  }, [initialNodes, selection, setNodes]);

  useEffect(() => {
    setEdges(
      initialEdges.map((edge) => ({
        ...edge,
        selected: selection?.type === "edge" && selection.id === edge.id
      }))
    );
  }, [initialEdges, selection, setEdges]);

  const toggleEdgeKind = (kind: EdgeKind) => {
    setEnabledEdges((current) => ({ ...current, [kind]: !current[kind] }));
  };

  if (graph.nodes.length === 0) {
    return (
      <Box className="empty-graph">
        <AccountTree />
        <Typography variant="h2">No graph data</Typography>
        <Typography variant="body2" color="text.secondary">
          Run a query or wait for graph aggregation to populate the vector view.
        </Typography>
      </Box>
    );
  }

  return (
    <ReactFlow
      className="live-graph"
      nodes={nodes}
      edges={edges}
      nodeTypes={graphNodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={(_, node) => onSelectionChange({ type: "node", id: node.id })}
      onEdgeClick={(_, edge) => onSelectionChange({ type: "edge", id: edge.id })}
      onPaneClick={() => onSelectionChange(null)}
      fitView
      fitViewOptions={{ padding: 0.22, maxZoom: 1.25 }}
      minZoom={0.12}
      maxZoom={1.8}
    >
      <Background color="#dbe4ef" gap={28} />
      <Controls showInteractive={false} />
      <MiniMap
        pannable
        zoomable
        nodeBorderRadius={8}
        nodeColor={(node) => (node.data as FlowNodeData).accent}
      />
      <Panel position="top-left" className="flow-panel">
        <Stack spacing={1}>
          <Stack direction="row" spacing={1} alignItems="center">
            <AccountTree fontSize="small" color="primary" />
            <Typography variant="subtitle2">Live vector graph</Typography>
          </Stack>
          <Stack direction="row" flexWrap="wrap" gap={0.5}>
            {(Object.keys(edgeLegend) as EdgeKind[]).map((kind) => (
              <FormControlLabel
                key={kind}
                className="edge-filter"
                control={
                  <Checkbox
                    size="small"
                    checked={enabledEdges[kind]}
                    onChange={() => toggleEdgeKind(kind)}
                    sx={{ color: edgeLegend[kind].color }}
                  />
                }
                label={edgeLegend[kind].label}
              />
            ))}
          </Stack>
        </Stack>
      </Panel>
    </ReactFlow>
  );
}

function MemoryGraphNode({ data, selected }: NodeProps<MemoryFlowNode>) {
  return (
    <Box
      className={`flow-node ${selected ? "flow-node-selected" : ""}`}
      style={{ borderColor: data.accent }}
    >
      <Handle type="target" position={Position.Left} />
      <Stack spacing={0.75}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
          <Typography variant="subtitle2" className="flow-node-title">
            {data.label}
          </Typography>
          <span className="flow-node-weight">{data.node.weight.toFixed(2)}</span>
        </Stack>
        <Stack direction="row" flexWrap="wrap" gap={0.5}>
          <span className="node-chip">{data.node.node_type}</span>
          {data.node.subtype ? <span className="node-chip">{data.node.subtype}</span> : null}
          {data.role !== "node" ? <span className="node-chip accent-chip">{data.role}</span> : null}
        </Stack>
        {data.groupLabels.length > 0 ? (
          <Typography variant="caption" className="flow-node-group">
            {data.groupLabels.slice(0, 2).join(", ")}
          </Typography>
        ) : null}
      </Stack>
      <Handle type="source" position={Position.Right} />
    </Box>
  );
}

function GraphInsights({
  graph,
  selection,
  onSelectNode,
  onSelectEdge
}: {
  graph: GraphResponse;
  selection: GraphSelection;
  onSelectNode: (id: string) => void;
  onSelectEdge: (id: string) => void;
}) {
  const selectedNode =
    selection?.type === "node" ? graph.nodes.find((node) => node.id === selection.id) : null;
  const selectedEdge =
    selection?.type === "edge" ? graph.edges.find((edge) => edge.id === selection.id) : null;
  const relationCounts = countEdgesByKind(graph.edges);
  const centroids = getCentroidNodes(graph);

  return (
    <Card className="side-panel">
      <CardContent>
        <Stack spacing={2}>
          <InsightSection title="Centroids" icon={<Hub color="primary" />}>
            {centroids.slice(0, 8).map((node) => (
              <button
                type="button"
                key={node.id}
                className={`insight-row ${selection?.id === node.id ? "insight-row-selected" : ""}`}
                onClick={() => onSelectNode(node.id)}
              >
                <span className="swatch" style={{ backgroundColor: nodeAccent(node) }} />
                <span>
                  <strong>{node.label}</strong>
                  <small>{node.subtype || node.node_type}</small>
                </span>
              </button>
            ))}
            {centroids.length === 0 ? <EmptyText>No centroid candidates in this slice.</EmptyText> : null}
          </InsightSection>

          <InsightSection title="Relation Mix" icon={<JoinInner color="primary" />}>
            <Stack spacing={0.75}>
              {(Object.keys(edgeLegend) as EdgeKind[]).map((kind) => (
                <button
                  type="button"
                  key={kind}
                  className="relation-row"
                  onClick={() => {
                    const firstEdge = graph.edges.find((edge) => edgeKind(edge) === kind);
                    if (firstEdge) {
                      onSelectEdge(firstEdge.id);
                    }
                  }}
                >
                  <span className="swatch" style={{ backgroundColor: edgeLegend[kind].color }} />
                  <span className="relation-icon" style={{ color: edgeLegend[kind].color }}>
                    {edgeLegend[kind].icon}
                  </span>
                  <span>{edgeLegend[kind].label}</span>
                  <strong>{relationCounts[kind]}</strong>
                </button>
              ))}
            </Stack>
          </InsightSection>

          <InsightSection title="Groups" icon={<AccountTree color="primary" />}>
            {graph.grouping_opportunities.slice(0, 8).map((item) => (
              <button
                type="button"
                key={item.id}
                className="group-row"
                onClick={() => item.centroid_node_id && onSelectNode(item.centroid_node_id)}
              >
                <strong>{item.label}</strong>
                <span>
                  {item.member_count} members - score {item.score.toFixed(2)}
                </span>
              </button>
            ))}
            {graph.grouping_opportunities.length === 0 ? (
              <EmptyText>No grouping opportunities in the current graph.</EmptyText>
            ) : null}
          </InsightSection>

          <InsightSection title="Selection" icon={<Timeline color="primary" />}>
            <SelectionDetails node={selectedNode || null} edge={selectedEdge || null} />
          </InsightSection>
        </Stack>
      </CardContent>
    </Card>
  );
}

function InsightSection({
  title,
  icon,
  children
}: {
  title: string;
  icon: ReactElement;
  children: ReactNode;
}) {
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1} alignItems="center">
        {icon}
        <Typography component="h2" variant="h2">
          {title}
        </Typography>
      </Stack>
      {children}
    </Stack>
  );
}

function SelectionDetails({ node, edge }: { node: GraphNode | null; edge: GraphEdge | null }) {
  if (node) {
    return (
      <Box className="detail-block">
        <Typography variant="subtitle2">{node.label}</Typography>
        <Typography variant="body2" color="text.secondary">
          {node.summary || "No summary captured for this node."}
        </Typography>
        <DetailRow label="Type" value={[node.node_type, node.subtype].filter(Boolean).join(" / ")} />
        <DetailRow label="Role" value={nodeRole(node)} />
        <DetailRow label="Weight" value={node.weight.toFixed(3)} />
      </Box>
    );
  }

  if (edge) {
    const kind = edgeKind(edge);
    return (
      <Box className="detail-block">
        <Typography variant="subtitle2">{edge.label || edge.edge_type}</Typography>
        <DetailRow label="Kind" value={edgeLegend[kind].label} />
        <DetailRow label="Source" value={edge.source} />
        <DetailRow label="Target" value={edge.target} />
        <DetailRow label="Weight" value={edge.weight.toFixed(3)} />
        <DetailRow label="Confidence" value={edge.confidence?.toFixed(3) || "-"} />
      </Box>
    );
  }

  return <EmptyText>Select a node, edge, centroid, or group to inspect it.</EmptyText>;
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <Box className="detail-row">
      <span>{label}</span>
      <strong title={value}>{value}</strong>
    </Box>
  );
}

function EmptyText({ children }: { children: ReactNode }) {
  return (
    <Typography variant="body2" color="text.secondary">
      {children}
    </Typography>
  );
}

function buildFlowNodes(graph: GraphResponse): MemoryFlowNode[] {
  const memberships = groupMemberships(graph);
  const centroids = new Set(
    graph.grouping_opportunities
      .map((group) => group.centroid_node_id)
      .filter((id): id is string => Boolean(id))
  );
  const centroidNodes = graph.nodes.filter(
    (node) => centroids.has(node.id) || nodeRole(node).includes("centroid")
  );
  const memoryNodes = graph.nodes.filter(
    (node) => node.node_type !== "entity" && !centroidNodes.some((centroid) => centroid.id === node.id)
  );
  const entityNodes = graph.nodes.filter((node) => node.node_type === "entity");

  const toFlowNode = (
    node: GraphNode,
    index: number,
    count: number,
    ring: number
  ): MemoryFlowNode => {
    const role = nodeRole(node);
    const isCentroid = ring === 0;
    return {
      id: node.id,
      type: "memory",
      position: ringPosition(index, count, ring),
      data: {
        label: node.label,
        node,
        role,
        accent: isCentroid ? "#c2410c" : nodeAccent(node),
        groupLabels: memberships.get(node.id) || []
      }
    };
  };

  return [
    ...centroidNodes.map((node, index) => toFlowNode(node, index, centroidNodes.length, 0)),
    ...memoryNodes.map((node, index) => toFlowNode(node, index, memoryNodes.length, 1)),
    ...entityNodes.map((node, index) => toFlowNode(node, index, entityNodes.length, 2))
  ];
}

function buildFlowEdges(edges: GraphEdge[]): MemoryFlowEdge[] {
  return edges.map((edge) => {
    const kind = edgeKind(edge);
    const legend = edgeLegend[kind];
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label || edge.edge_type,
      type: "smoothstep",
      animated: kind === "vector",
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: legend.color
      },
      style: {
        stroke: legend.color,
        strokeWidth: Math.max(1.25, Math.min(5, 1 + edge.weight * 2.5)),
        opacity: kind === "other" ? 0.42 : 0.72
      },
      labelStyle: {
        fill: "#334155",
        fontWeight: 600,
        fontSize: 11
      },
      data: { edge, kind }
    };
  });
}

function ringPosition(index: number, total: number, ring: number) {
  if (ring === 0) {
    const angle = (index / Math.max(1, total)) * Math.PI * 2;
    return {
      x: Math.cos(angle) * 260 - 105,
      y: Math.sin(angle) * 160 - 45
    };
  }
  const radiusX = ring === 1 ? 900 : 1320;
  const radiusY = ring === 1 ? 560 : 850;
  const angle = (index / Math.max(1, total)) * Math.PI * 2;
  return {
    x: Math.cos(angle) * radiusX - 100,
    y: Math.sin(angle) * radiusY - 50
  };
}

function groupMemberships(graph: GraphResponse) {
  const memberships = new Map<string, string[]>();
  for (const group of graph.grouping_opportunities) {
    for (const nodeId of group.member_node_ids) {
      memberships.set(nodeId, [...(memberships.get(nodeId) || []), group.label]);
    }
  }
  return memberships;
}

function getCentroidNodes(graph: GraphResponse) {
  const centroidIds = new Set(
    graph.grouping_opportunities
      .map((group) => group.centroid_node_id)
      .filter((id): id is string => Boolean(id))
  );
  return graph.nodes.filter((node) => centroidIds.has(node.id) || nodeRole(node).includes("centroid"));
}

function countEdgesByKind(edges: GraphEdge[]) {
  const counts: Record<EdgeKind, number> = {
    vector: 0,
    correlation: 0,
    entity: 0,
    explicit: 0,
    other: 0
  };
  for (const edge of edges) {
    counts[edgeKind(edge)] += 1;
  }
  return counts;
}

function edgeKind(edge: GraphEdge): EdgeKind {
  const label = `${edge.label || ""} ${edge.edge_type || ""}`.toLowerCase();
  if (label.includes("vector") || label.includes("neighbor") || label.includes("embedding")) {
    return "vector";
  }
  if (label.includes("correlation") || label.includes("similarity")) {
    return "correlation";
  }
  if (label.includes("entity") || label.includes("shared") || label.includes("mentions")) {
    return "entity";
  }
  if (label.includes("link") || label.includes("explicit") || label.includes("related")) {
    return "explicit";
  }
  return "other";
}

function nodeRole(node: GraphNode) {
  const graphMetadata = asRecord(node.metadata.graph);
  const role = graphMetadata.role;
  return typeof role === "string" && role.trim() ? role : "node";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function nodeAccent(node: GraphNode) {
  if (node.node_type === "entity") {
    return "#b7791f";
  }
  if (node.subtype === "skill") {
    return "#6b4eff";
  }
  if (node.subtype === "workflow" || node.subtype === "decision") {
    return "#d04437";
  }
  if (node.subtype === "rule" || node.subtype === "runbook") {
    return "#0f766e";
  }
  return "#2f6fb0";
}

type JobsPanelProps = {
  jobStatus: JobStatus | null;
  loading: boolean;
  onRefresh: () => void;
};

function JobsPanel({ jobStatus, loading, onRefresh }: JobsPanelProps) {
  const lastRun = jobStatus?.last_run;
  return (
    <Grid container spacing={2.5}>
      <Grid size={{ xs: 12, md: 4 }}>
        <Card>
          <CardContent>
            <Stack spacing={1.5}>
              <Stack direction="row" alignItems="center" justifyContent="space-between">
                <Typography component="h2" variant="h2">
                  Graph Aggregation
                </Typography>
                <Tooltip title="Refresh jobs">
                  <Button
                    variant="outlined"
                    startIcon={loading ? <CircularProgress size={16} /> : <Refresh />}
                    onClick={onRefresh}
                    disabled={loading}
                  >
                    Refresh
                  </Button>
                </Tooltip>
              </Stack>
              <StatusChip value={jobStatus?.status || "unknown"} />
              <Typography variant="body2" color="text.secondary">
                {jobStatus?.command || "onebrain-jobs run_scheduled_jobs --job graph-aggregation"}
              </Typography>
            </Stack>
          </CardContent>
        </Card>
      </Grid>
      <Grid size={{ xs: 12, md: 8 }}>
        <Card>
          <CardContent>
            <Stack spacing={1.5}>
              <Typography component="h2" variant="h2">
                Last Run
              </Typography>
              <Divider />
              <Grid container spacing={1.5}>
                <Metric label="Run count" value={String(lastRun?.run_count ?? "-")} />
                <Metric label="Started" value={String(lastRun?.started_at ?? "-")} />
                <Metric label="Finished" value={String(lastRun?.finished_at ?? "-")} />
                <Metric label="Next run" value={jobStatus?.next_run_at || "-"} />
              </Grid>
            </Stack>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
}

function StoragePanel({ graph, jobStatus }: { graph: GraphResponse; jobStatus: JobStatus | null }) {
  return (
    <Grid container spacing={2.5}>
      <Metric label="Vector store" value="PostgreSQL pgvector" />
      <Metric label="Loaded memories" value={String(graph.memory_count)} />
      <Metric label="Visible entities" value={String(graph.entity_count)} />
      <Metric label="Job status" value={jobStatus?.status || "unknown"} />
    </Grid>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
      <Card>
        <CardContent className="metric-card">
          <Typography variant="body2" color="text.secondary">
            {label}
          </Typography>
          <Typography variant="h2">{value}</Typography>
        </CardContent>
      </Card>
    </Grid>
  );
}

function StatusChip({ value }: { value: string }) {
  const color = value === "success" ? "success" : value === "failed" ? "error" : "default";
  return <Chip color={color} size="small" label={value} className="status-chip" />;
}
