import { useAuthStore } from "../../stores/authStore";

interface LogoutButtonProps {
  className?: string;
}

/**
 * Hard-navigates to /login (matching api/client.ts's own 401 logout path)
 * rather than using react-router's navigate -- a client-side route change
 * would leave chatStore/employerStore/adminStore's in-memory state from the
 * previous user sitting around for whichever role logs in next, since none
 * of those stores reset on logout().
 */
export function LogoutButton({ className }: LogoutButtonProps) {
  function handleLogout() {
    useAuthStore.getState().logout();
    window.location.assign("/login");
  }

  return (
    <button
      type="button"
      onClick={handleLogout}
      className={
        className ??
        "rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100"
      }
    >
      Log out
    </button>
  );
}
