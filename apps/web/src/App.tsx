import {
  AccountTree,
  Analytics,
  Refresh,
  Search,
  Storage,
  Tune
} from "@mui/icons-material";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Divider,
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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

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
          <GraphCanvas nodes={props.graph.nodes} edges={props.graph.edges} />
        </Card>
      </Grid>
      <Grid size={{ xs: 12, lg: 3 }}>
        <Card className="side-panel">
          <CardContent>
            <Stack spacing={1.5}>
              <Typography component="h2" variant="h2">
                Grouping Opportunities
              </Typography>
              {props.graph.grouping_opportunities.slice(0, 8).map((item) => (
                <Box key={item.id} className="list-row">
                  <Typography variant="subtitle2">{item.label}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {item.member_count} members · score {item.score.toFixed(2)}
                  </Typography>
                </Box>
              ))}
              {props.graph.grouping_opportunities.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  No grouping opportunities in the current graph.
                </Typography>
              ) : null}
            </Stack>
          </CardContent>
        </Card>
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

type GraphCanvasProps = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

function GraphCanvas({ nodes, edges }: GraphCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }
    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    context.scale(dpr, dpr);
    drawGraph(context, rect.width, rect.height, nodes, edges);
  }, [edges, nodes]);

  return <canvas ref={canvasRef} className="graph-canvas" aria-label="Memory graph canvas" />;
}

function drawGraph(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  nodes: GraphNode[],
  edges: GraphEdge[]
) {
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#fbfcfe";
  context.fillRect(0, 0, width, height);
  context.strokeStyle = "#e3e9ef";
  context.lineWidth = 1;
  for (let x = 24; x < width; x += 48) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, height);
    context.stroke();
  }
  for (let y = 24; y < height; y += 48) {
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }

  if (nodes.length === 0) {
    context.fillStyle = "#536171";
    context.font = "600 16px Inter, Roboto, sans-serif";
    context.fillText("No graph data", 32, 48);
    return;
  }

  const positions = layoutNodes(nodes, width, height);
  context.lineCap = "round";
  for (const edge of edges) {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) {
      continue;
    }
    context.beginPath();
    context.moveTo(source.x, source.y);
    context.lineTo(target.x, target.y);
    context.strokeStyle = edge.label === "vector_neighbor" ? "#6b4eff" : "#a6b3c1";
    context.globalAlpha = 0.42;
    context.lineWidth = Math.max(1, Math.min(4, edge.weight * 2));
    context.stroke();
  }
  context.globalAlpha = 1;

  for (const node of nodes) {
    const point = positions.get(node.id);
    if (!point) {
      continue;
    }
    const radius = Math.max(7, Math.min(18, 7 + node.weight * 8));
    context.beginPath();
    context.arc(point.x, point.y, radius, 0, Math.PI * 2);
    context.fillStyle = nodeColor(node);
    context.fill();
    context.strokeStyle = "#ffffff";
    context.lineWidth = 2;
    context.stroke();
  }
}

function layoutNodes(nodes: GraphNode[], width: number, height: number) {
  const positions = new Map<string, { x: number; y: number }>();
  const centerX = width / 2;
  const centerY = height / 2;
  const radiusX = Math.max(120, width * 0.38);
  const radiusY = Math.max(100, height * 0.34);
  nodes.forEach((node, index) => {
    const angle = (index / Math.max(1, nodes.length)) * Math.PI * 2;
    const ring = index % 3 === 0 ? 0.62 : index % 3 === 1 ? 0.82 : 1;
    positions.set(node.id, {
      x: centerX + Math.cos(angle) * radiusX * ring,
      y: centerY + Math.sin(angle) * radiusY * ring
    });
  });
  return positions;
}

function nodeColor(node: GraphNode) {
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
