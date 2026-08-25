import axios from "axios";

import { useAuthStore } from "../stores/authStore";

// Axios instance + interceptors (files/plan.md's frontend file tree). Only
// the auth-header interceptor lives here in Step 10.1 -- the 401 ->
// refresh-token -> retry interceptor is Step 10.2's job, once
// api/auth.ts's refresh call exists for it to invoke.
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
});

apiClient.interceptors.request.use((config) => {
  const { accessToken } = useAuthStore.getState();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});
