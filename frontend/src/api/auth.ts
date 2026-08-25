import { apiClient } from "./client";

// Mirrors backend/src/api/routes/auth_routes.py's TokenResponse/AccessTokenResponse.
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface AccessTokenResponse {
  access_token: string;
  token_type: string;
}

/**
 * POST /api/auth/login -- OAuth2 password flow (email as `username`), the
 * exact contract `auth_routes.py`'s `/login` expects: form-encoded, not
 * JSON.
 */
export async function login(email: string, password: string): Promise<TokenResponse> {
  const body = new URLSearchParams({ username: email, password });
  const response = await apiClient.post<TokenResponse>("/api/auth/login", body, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  return response.data;
}

/** POST /api/auth/refresh -- exchanges a refresh token for a new access token only. */
export async function refresh(refreshToken: string): Promise<AccessTokenResponse> {
  const response = await apiClient.post<AccessTokenResponse>("/api/auth/refresh", {
    refresh_token: refreshToken,
  });
  return response.data;
}
