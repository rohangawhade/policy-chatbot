import { apiClient } from "./client";

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
