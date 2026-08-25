import { apiClient } from "./client";

// Mirrors backend/src/api/routes/employer_routes.py response schemas.
export interface EmployerResponseDto {
  id: string;
  name: string;
  is_active: boolean;
}

export async function listEmployers(): Promise<EmployerResponseDto[]> {
  const response = await apiClient.get<EmployerResponseDto[]>("/api/employers");
  return response.data;
}

export async function createEmployer(name: string): Promise<EmployerResponseDto> {
  const response = await apiClient.post<EmployerResponseDto>("/api/employers", { name });
  return response.data;
}

export async function updateEmployer(
  employerId: string,
  data: { name?: string; is_active?: boolean },
): Promise<EmployerResponseDto> {
  const response = await apiClient.patch<EmployerResponseDto>(`/api/employers/${employerId}`, data);
  return response.data;
}

export async function deactivateEmployer(employerId: string): Promise<void> {
  await updateEmployer(employerId, { is_active: false });
}
