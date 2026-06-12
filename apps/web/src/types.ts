export type GraphNode = {
  id: string;
  node_type: string;
  label: string;
  subtype?: string | null;
  summary?: string | null;
  weight: number;
  metadata: Record<string, unknown>;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  edge_type: string;
  label?: string | null;
  weight: number;
  confidence?: number | null;
  metadata: Record<string, unknown>;
};

export type GroupingOpportunity = {
  id: string;
  label: string;
  summary: string;
  member_node_ids: string[];
  member_count: number;
  centroid_node_id?: string | null;
  score: number;
  cohesion: number;
  separation: number;
  reasons: string[];
  keywords: string[];
  metadata: Record<string, unknown>;
};

export type GraphResponse = {
  query: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  memory_count: number;
  entity_count: number;
  omitted: number;
  grouping_opportunities: GroupingOpportunity[];
};

export type JobStatus = {
  job: string;
  status: string;
  command: string;
  scheduler: {
    interval_seconds?: number;
    max_runs?: number | null;
    run_immediately?: boolean;
  };
  configuration: Record<string, unknown>;
  last_run?: Record<string, unknown> | null;
  next_run_at?: string | null;
};
