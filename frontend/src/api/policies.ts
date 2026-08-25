import { apiClient } from "./client";
import type { PolicyType } from "./documents";

// Mirrors backend/src/api/routes/policy_routes.py's PolicyResponse.
export interface PolicyResponseDto {
  id: string;
  employer_id: string;
  policy_type: PolicyType;
  name: string;
  description: string | null;
}

// Mirrors policy_routes.py's EnrolledEmployeeResponse (Step 10.8's new
// GET /{policy_id}/enrollments route).
export interface EnrolledEmployeeDto {
  employee_id: string;
  full_name: string;
  email: string;
  is_active: boolean;
}

export async function listPolicies(): Promise<PolicyResponseDto[]> {
  const response = await apiClient.get<PolicyResponseDto[]>("/api/policies");
  return response.data;
}

export async function listPolicyEnrollments(policyId: string): Promise<EnrolledEmployeeDto[]> {
  const response = await apiClient.get<EnrolledEmployeeDto[]>(
    `/api/policies/${policyId}/enrollments`,
  );
  return response.data;
}
