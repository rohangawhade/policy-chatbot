import { apiClient } from "./client";

// Mirrors backend/src/core/domain/policy.py's PolicyType.
export type PolicyType = "health" | "dental" | "vision" | "life" | "disability";

// Mirrors document_routes.py's DocumentListItemResponse (GET /api/documents) --
// deliberately a different shape than DocumentStatusResponseDto below: the
// list endpoint and the upload/status endpoints return different fields.
export interface DocumentListItemDto {
  id: string;
  employer_id: string;
  title: string;
  policy_type: PolicyType | null;
  status: "processing" | "ready" | "failed";
  version: number;
}

// Mirrors document_routes.py's DocumentStatusResponse (POST /upload, GET /status).
export interface DocumentStatusResponseDto {
  id: string;
  status: "processing" | "ready" | "failed";
  version: number;
  error_message: string | null;
}

export async function uploadDocument(
  file: File,
  title: string,
  options?: { employerId?: string; policyType?: PolicyType },
): Promise<DocumentStatusResponseDto> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("title", title);
  if (options?.employerId) {
    formData.append("employer_id", options.employerId);
  }
  if (options?.policyType) {
    formData.append("policy_type", options.policyType);
  }

  const response = await apiClient.post<DocumentStatusResponseDto>(
    "/api/documents/upload",
    formData,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return response.data;
}

// For an ADMIN account (no employer_id of its own), omitting employerId
// returns every tenant's documents; passing one narrows to that employer.
// EMPLOYER/EMPLOYEE accounts always see only their own regardless of this
// param -- the backend derives their scope from the token, never the query.
export async function listDocuments(employerId?: string): Promise<DocumentListItemDto[]> {
  const response = await apiClient.get<DocumentListItemDto[]>("/api/documents", {
    params: employerId ? { employer_id: employerId } : undefined,
  });
  return response.data;
}

export async function deleteDocument(documentId: string): Promise<void> {
  await apiClient.delete(`/api/documents/${documentId}`);
}

export async function getDocumentStatus(documentId: string): Promise<DocumentStatusResponseDto> {
  const response = await apiClient.get<DocumentStatusResponseDto>(
    `/api/documents/${documentId}/status`,
  );
  return response.data;
}
