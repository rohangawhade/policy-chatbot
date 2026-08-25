import { create } from "zustand";

// Mirrors backend/src/core/domain/employee.py's UserRole values exactly.
export type UserRole = "admin" | "employer" | "employee";

interface DecodedAccessToken {
  userId: string;
  employerId: string | null;
  role: UserRole;
  exp: number;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  userId: string | null;
  employerId: string | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  /** Store a fresh access + refresh token pair (POST /api/auth/login or /register). */
  setTokens: (accessToken: string, refreshToken: string) => void;
  /** Store a refreshed access token only (POST /api/auth/refresh doesn't rotate the refresh token). */
  setAccessToken: (accessToken: string) => void;
  logout: () => void;
}

/**
 * Reads the claims out of a JWT's payload segment without verifying its
 * signature -- that verification is meaningless client-side (it would need
 * the server's secret) and every real authorization decision is enforced
 * server-side regardless. This exists purely to drive UI routing (which
 * role/employer view to render) without an extra round trip to
 * GET /api/auth/me right after login.
 */
function decodeAccessToken(token: string): DecodedAccessToken {
  const payloadSegment = token.split(".")[1];
  if (!payloadSegment) {
    throw new Error("Malformed access token: missing payload segment.");
  }
  const base64 = payloadSegment.replace(/-/g, "+").replace(/_/g, "/");
  const claims = JSON.parse(atob(base64)) as Record<string, unknown>;

  return {
    userId: String(claims.sub),
    employerId: claims.employer_id ? String(claims.employer_id) : null,
    role: claims.role as UserRole,
    exp: Number(claims.exp),
  };
}

type PersistedAuthFields = Pick<
  AuthState,
  "accessToken" | "refreshToken" | "userId" | "employerId" | "role" | "isAuthenticated"
>;

const loggedOutState: PersistedAuthFields = {
  accessToken: null,
  refreshToken: null,
  userId: null,
  employerId: null,
  role: null,
  isAuthenticated: false,
};

// In-memory only, deliberately not persisted to localStorage/sessionStorage
// (files/plan.md Step 10.2: "JWT storage in memory... not localStorage") --
// a page refresh logs the user out, which is the accepted tradeoff for not
// exposing tokens to XSS-readable storage.
export const useAuthStore = create<AuthState>((set) => ({
  ...loggedOutState,

  setTokens: (accessToken, refreshToken) => {
    const decoded = decodeAccessToken(accessToken);
    set({
      accessToken,
      refreshToken,
      userId: decoded.userId,
      employerId: decoded.employerId,
      role: decoded.role,
      isAuthenticated: true,
    });
  },

  setAccessToken: (accessToken) => {
    const decoded = decodeAccessToken(accessToken);
    set({
      accessToken,
      userId: decoded.userId,
      employerId: decoded.employerId,
      role: decoded.role,
      isAuthenticated: true,
    });
  },

  logout: () => set({ ...loggedOutState }),
}));

const DEFAULT_ROUTE_BY_ROLE: Record<UserRole, string> = {
  admin: "/admin",
  employer: "/employer",
  employee: "/chat",
};

export function defaultRouteForRole(role: UserRole | null): string {
  return role ? DEFAULT_ROUTE_BY_ROLE[role] : "/login";
}
