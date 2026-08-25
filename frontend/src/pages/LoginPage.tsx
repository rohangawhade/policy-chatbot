import axios from "axios";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { login } from "../api/auth";
import { defaultRouteForRole, useAuthStore, type UserRole } from "../stores/authStore";

const PORTALS: { value: UserRole; label: string }[] = [
  { value: "employee", label: "Employee" },
  { value: "employer", label: "Employer" },
  { value: "admin", label: "Admin" },
];

function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError<{ detail?: string }>(error)) {
    if (error.response?.status === 401) {
      return error.response.data?.detail ?? "Incorrect email or password.";
    }
    if (error.response) {
      return error.response.data?.detail ?? "Something went wrong. Please try again.";
    }
  }
  return "Couldn't reach the server. Please try again.";
}

export default function LoginPage() {
  const navigate = useNavigate();
  const setTokens = useAuthStore((state) => state.setTokens);
  // Purely a UX convenience -- which portal's login form this looks like.
  // The backend has no concept of "logging in as" a role; the account's
  // real role (from the response's token) always decides where the user
  // actually lands.
  const [selectedPortal, setSelectedPortal] = useState<UserRole>("employee");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const tokens = await login(email, password);
      setTokens(tokens.access_token, tokens.refresh_token);
      navigate(defaultRouteForRole(useAuthStore.getState().role), { replace: true });
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm rounded-lg bg-white p-8 shadow">
        <h1 className="mb-6 text-2xl font-medium text-gray-900">Log in to PolicyPal</h1>

        <div className="mb-2 flex gap-2" role="radiogroup" aria-label="Portal">
          {PORTALS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={selectedPortal === value}
              onClick={() => setSelectedPortal(value)}
              className={`flex-1 rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                selectedPortal === value
                  ? "border-blue-600 bg-blue-50 text-blue-700"
                  : "border-gray-300 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="mb-6 text-xs text-gray-500">
          We'll always take you to the dashboard your account is set up for, regardless of which
          portal you pick above.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-gray-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-gray-700">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>

          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isSubmitting ? "Logging in..." : "Log in"}
          </button>
        </form>
      </div>
    </div>
  );
}
