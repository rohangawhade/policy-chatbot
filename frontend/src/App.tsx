import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";

import { ProtectedRoute } from "./components/common/ProtectedRoute";
import AdminDashboard from "./pages/AdminDashboard";
import ChatPage from "./pages/ChatPage";
import EmployerPortal from "./pages/EmployerPortal";
import LoginPage from "./pages/LoginPage";
import { defaultRouteForRole, useAuthStore } from "./stores/authStore";

function RoleHome() {
  const role = useAuthStore((state) => state.role);
  return <Navigate to={defaultRouteForRole(role)} replace />;
}

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <ProtectedRoute allowedRoles={["employee", "employer"]} />,
    children: [{ path: "/chat", element: <ChatPage /> }],
  },
  {
    element: <ProtectedRoute allowedRoles={["admin"]} />,
    children: [{ path: "/admin", element: <AdminDashboard /> }],
  },
  {
    element: <ProtectedRoute allowedRoles={["employer"]} />,
    children: [{ path: "/employer", element: <EmployerPortal /> }],
  },
  { path: "/", element: <RoleHome /> },
  { path: "*", element: <RoleHome /> },
]);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
