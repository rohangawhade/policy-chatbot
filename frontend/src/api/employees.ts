import { apiClient } from "./client";

// Mirrors backend/src/api/routes/employee_routes.py's EmployeeResponse.
export interface EmployeeResponseDto {
  id: string;
  employer_id: string | null;
  email: string;
  full_name: string;
  role: "admin" | "employer" | "employee";
  is_active: boolean;
}

export async function listEmployees(): Promise<EmployeeResponseDto[]> {
  const response = await apiClient.get<EmployeeResponseDto[]>("/api/employees");
  return response.data;
}

// "Invite" (plan.md's wording) is really direct account creation with a
// temporary password -- POST /api/employees has no separate email-invite
// flow (no email/SMTP integration exists anywhere in this app), so the
// caller must set an initial password the new account can change later.
export async function inviteEmployee(data: {
  email: string;
  password: string;
  fullName: string;
  role: "employee" | "employer";
}): Promise<EmployeeResponseDto> {
  const response = await apiClient.post<EmployeeResponseDto>("/api/employees", {
    email: data.email,
    password: data.password,
    full_name: data.fullName,
    role: data.role,
  });
  return response.data;
}

export async function updateEmployee(
  employeeId: string,
  data: { full_name?: string; is_active?: boolean },
): Promise<EmployeeResponseDto> {
  const response = await apiClient.patch<EmployeeResponseDto>(`/api/employees/${employeeId}`, data);
  return response.data;
}

export async function deactivateEmployee(employeeId: string): Promise<void> {
  await updateEmployee(employeeId, { is_active: false });
}
