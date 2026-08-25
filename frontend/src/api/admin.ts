import { apiClient } from "./client";
import type { PolicyType } from "./documents";

// Mirrors admin_routes.py's OverviewResponse (GET /api/admin/overview).
export interface OverviewDto {
  total_queries_today: number;
  total_queries_week: number;
  total_queries_month: number;
  active_users_week: number;
  document_count: number;
  avg_satisfaction: number;
  cost_this_month_usd: number;
}

// Mirrors admin_routes.py's CostByModel/CostByEmployer/CostByDay/CostDashboardResponse.
export interface CostByModelDto {
  model: string;
  total_cost_usd: number;
  call_count: number;
}

export interface CostByEmployerDto {
  employer_id: string;
  total_cost_usd: number;
}

export interface CostByDayDto {
  date: string;
  total_cost_usd: number;
}

export interface CostDashboardDto {
  total_cost_usd: number;
  by_model: CostByModelDto[];
  by_employer: CostByEmployerDto[];
  by_day: CostByDayDto[];
}

// Mirrors admin_routes.py's CostAlert (GET /api/admin/cost-dashboard/alerts).
export interface CostAlertDto {
  employer_id: string;
  date: string;
  total_cost_usd: number;
  threshold_usd: number;
}

export interface CostDashboardParams {
  employerId?: string;
  start?: string;
  end?: string;
}

export async function getOverview(): Promise<OverviewDto> {
  const response = await apiClient.get<OverviewDto>("/api/admin/overview");
  return response.data;
}

export async function getCostDashboard(
  params: CostDashboardParams = {},
): Promise<CostDashboardDto> {
  const response = await apiClient.get<CostDashboardDto>("/api/admin/cost-dashboard", {
    params: {
      employer_id: params.employerId || undefined,
      start: params.start || undefined,
      end: params.end || undefined,
    },
  });
  return response.data;
}

export async function getCostAlerts(params: CostDashboardParams = {}): Promise<CostAlertDto[]> {
  const response = await apiClient.get<CostAlertDto[]>("/api/admin/cost-dashboard/alerts", {
    params: {
      employer_id: params.employerId || undefined,
      start: params.start || undefined,
      end: params.end || undefined,
    },
  });
  return response.data;
}

// Mirrors admin_routes.py's FlaggedResponseItem (Step 9.6 + Step 10.6's
// response_text/model_used/policy_type enrichment). `top_similarity_score`
// is the only per-query retrieval signal actually persisted -- there's no
// stored list of individual retrieved chunks to expand into (see
// admin_routes.py's own documented-interpretation note).
export interface FlaggedResponseItemDto {
  id: string;
  employer_id: string;
  conversation_id: string;
  message_id: string;
  query_text: string;
  top_similarity_score: number | null;
  flag_reason: string;
  status: "pending_review" | "reviewed" | "dismissed" | "escalated";
  created_at: string;
  response_text: string | null;
  model_used: string | null;
  policy_type: PolicyType | null;
}

// Mirrors admin_routes.py's GuardrailRejectionItem.
export interface GuardrailRejectionItemDto {
  id: string;
  employer_id: string;
  query_text: string;
  rejection_reason: string;
  created_at: string;
}

export interface ListParams {
  employerId?: string;
  start?: string;
  end?: string;
}

export async function listFlaggedResponses(
  params: ListParams & { status?: string } = {},
): Promise<FlaggedResponseItemDto[]> {
  const response = await apiClient.get<FlaggedResponseItemDto[]>("/api/admin/flagged-responses", {
    params: {
      employer_id: params.employerId || undefined,
      status_filter: params.status || undefined,
    },
  });
  return response.data;
}

// "reviewed"/"dismissed"/"escalated" are the only statuses the backend
// accepts (admin_routes.py's `_TERMINAL_FLAG_STATUSES` -- `pending_review`
// is the initial state, never a target). Mapped in the UI to plan.md's
// "reviewed"/"false positive"/"needs document update" labels.
export async function updateFlaggedResponse(
  id: string,
  status: "reviewed" | "dismissed" | "escalated",
): Promise<FlaggedResponseItemDto> {
  const response = await apiClient.patch<FlaggedResponseItemDto>(
    `/api/admin/flagged-responses/${id}`,
    { status },
  );
  return response.data;
}

export async function listGuardrailRejections(
  params: ListParams = {},
): Promise<GuardrailRejectionItemDto[]> {
  const response = await apiClient.get<GuardrailRejectionItemDto[]>(
    "/api/admin/guardrail-rejections",
    {
      params: {
        employer_id: params.employerId || undefined,
        start: params.start || undefined,
        end: params.end || undefined,
      },
    },
  );
  return response.data;
}

export async function listUnansweredQueries(
  params: Pick<ListParams, "employerId"> = {},
): Promise<FlaggedResponseItemDto[]> {
  const response = await apiClient.get<FlaggedResponseItemDto[]>(
    "/api/admin/unanswered-queries",
    { params: { employer_id: params.employerId || undefined } },
  );
  return response.data;
}

// Mirrors admin_routes.py's LatencyStats/LatencyResponse (Step 10.7's
// retrieval/generation split).
export interface LatencyStatsDto {
  label: string;
  count: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
}

export interface LatencyResponseDto {
  overall: LatencyStatsDto;
  retrieval: LatencyStatsDto;
  generation: LatencyStatsDto;
  by_model_tier: LatencyStatsDto[];
}

export interface LatencyParams {
  employerId?: string;
  modelTier?: string;
  start?: string;
  end?: string;
}

export async function getLatency(params: LatencyParams = {}): Promise<LatencyResponseDto> {
  const response = await apiClient.get<LatencyResponseDto>("/api/admin/latency", {
    params: {
      employer_id: params.employerId || undefined,
      model_tier: params.modelTier || undefined,
      start: params.start || undefined,
      end: params.end || undefined,
    },
  });
  return response.data;
}

// Mirrors admin_routes.py's DocumentHealthItem (Step 10.7's error_message field).
export interface DocumentHealthItemDto {
  id: string;
  employer_id: string;
  title: string;
  version: number;
  status: "processing" | "ready" | "failed";
  error_message: string | null;
  is_stale: boolean;
  zero_query_hits: boolean;
  last_queried_at: string | null;
  updated_at: string;
}

export async function getDocumentHealth(
  params: Pick<ListParams, "employerId"> = {},
): Promise<DocumentHealthItemDto[]> {
  const response = await apiClient.get<DocumentHealthItemDto[]>("/api/admin/document-health", {
    params: { employer_id: params.employerId || undefined },
  });
  return response.data;
}

// Mirrors admin_routes.py's TopicHeatmapCell/TopicHeatmapResponse.
export interface TopicHeatmapCellDto {
  date: string;
  policy_type: PolicyType | null;
  query_count: number;
}

export async function getTopicHeatmap(params: ListParams = {}): Promise<TopicHeatmapCellDto[]> {
  const response = await apiClient.get<{ cells: TopicHeatmapCellDto[] }>(
    "/api/admin/topic-heatmap",
    {
      params: {
        employer_id: params.employerId || undefined,
        start: params.start || undefined,
        end: params.end || undefined,
      },
    },
  );
  return response.data.cells;
}
