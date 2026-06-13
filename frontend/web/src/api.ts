import type { GraphResponse, JobStatus } from "./types";

export type GraphQuery = {
  query: string;
  memoryType: string;
  scoringProfile: string;
  limit: number;
  correlationLimit: number;
  maxDegree: number;
};

export async function fetchGraph(query: GraphQuery): Promise<GraphResponse> {
  const response = await fetch("/graph/data", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      query: query.query.trim() || null,
      limit: query.limit,
      filters: {
        memory_types: query.memoryType ? [query.memoryType] : null
      },
      scoring_profile: query.scoringProfile,
      include_entities: true,
      include_relations: true,
      include_correlations: true,
      include_vector_correlations: true,
      correlation_limit: query.correlationLimit,
      max_correlation_degree: query.maxDegree,
      include_grouping_opportunities: true,
      grouping_limit: 25,
      grouping_min_size: 3
    })
  });

  if (!response.ok) {
    throw new Error(`Graph request failed with ${response.status}`);
  }
  return (await response.json()) as GraphResponse;
}

export async function fetchJobStatus(): Promise<JobStatus> {
  const response = await fetch("/api/jobs/graph-aggregation/status", {
    headers: { Accept: "application/json" }
  });
  if (!response.ok) {
    throw new Error(`Job status request failed with ${response.status}`);
  }
  return (await response.json()) as JobStatus;
}
