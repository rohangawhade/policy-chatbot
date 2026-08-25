import axios, { type AxiosRequestConfig } from "axios";

import { useAuthStore } from "../stores/authStore";
import type { AccessTokenResponse } from "./auth";

// Axios instance + interceptors (files/plan.md's frontend file tree).
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

interface RetriableRequestConfig extends AxiosRequestConfig {
  _retried?: boolean;
}

// The refresh call below deliberately uses a bare `axios.post` -- not
// `apiClient`, and not api/auth.ts's own `refresh()` -- so this interceptor
// never imports api/auth.ts's function. api/auth.ts imports *this* file
// (apiClient), so calling back into it here would be a circular
// dependency; a plain axios call also sidesteps this interceptor
// recursively firing on its own request.
apiClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error) || error.response?.status !== 401) {
      return Promise.reject(error);
    }

    const originalRequest = error.config as RetriableRequestConfig | undefined;
    const { refreshToken } = useAuthStore.getState();
    if (!originalRequest || originalRequest._retried || !refreshToken) {
      useAuthStore.getState().logout();
      window.location.assign("/login");
      return Promise.reject(error);
    }

    originalRequest._retried = true;
    try {
      const { data } = await axios.post<AccessTokenResponse>(
        `${import.meta.env.VITE_API_BASE_URL}/api/auth/refresh`,
        { refresh_token: refreshToken },
      );
      useAuthStore.getState().setAccessToken(data.access_token);
      return apiClient(originalRequest);
    } catch (refreshError) {
      useAuthStore.getState().logout();
      window.location.assign("/login");
      return Promise.reject(refreshError);
    }
  },
);
