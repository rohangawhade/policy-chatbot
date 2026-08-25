import { Navigate, Outlet } from "react-router-dom";

import { defaultRouteForRole, useAuthStore, type UserRole } from "../../stores/authStore";

interface ProtectedRouteProps {
  /** Omit to allow any authenticated role through. */
  allowedRoles?: UserRole[];
}

/**
 * Route guard: unauthenticated visitors are sent to /login; an
 * authenticated user whose role isn't in `allowedRoles` is sent to their
 * own default route rather than shown a bare 403 page, since every role
 * has somewhere real to land.
 */
export function ProtectedRoute({ allowedRoles }: ProtectedRouteProps) {
  const { isAuthenticated, role } = useAuthStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  if (allowedRoles && (!role || !allowedRoles.includes(role))) {
    return <Navigate to={defaultRouteForRole(role)} replace />;
  }
  return <Outlet />;
}
