import axios from "axios";
import type {
  TokenResponse,
  User,
  Session,
  Skill,
  Question,
  SubmitAnswerResult,
  Evaluation,
} from "@/types";

type ApiErrorPayload = {
  detail?: string;
  message?: string;
};

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
  withCredentials: true,
});

// Attach access token from localStorage on every request
api.interceptors.request.use((config) => {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status as number | undefined;
    const url = (error?.config?.url as string | undefined) ?? "";

    if (
      typeof window !== "undefined" &&
      status === 401 &&
      !url.includes("/api/v1/auth/login") &&
      !url.includes("/api/v1/auth/signup") &&
      !url.includes("/api/v1/auth/refresh")
    ) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      if (window.location.pathname !== "/auth") {
        window.location.replace("/auth");
      }
    }

    return Promise.reject(error);
  }
);

export const getApiErrorMessage = (
  error: unknown,
  fallback = "Something went wrong"
): string => {
  const payload = (error as { response?: { data?: ApiErrorPayload } })?.response
    ?.data;
  return payload?.detail ?? payload?.message ?? fallback;
};

export const authApi = {
  signup: (data: { email: string; password: string; full_name: string }) =>
    api.post<TokenResponse>("/api/v1/auth/signup", data),
  login: (data: { email: string; password: string }) =>
    api.post<TokenResponse>("/api/v1/auth/login", data),
  me: () => api.get<User>("/api/v1/auth/me"),
};

export const sessionsApi = {
  list: () => api.get<Session[]>("/api/v1/sessions"),
  get: (id: string) => api.get<Session>(`/api/v1/sessions/${id}`),
  create: (formData: FormData) =>
    api.post<Session>("/api/v1/sessions", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  delete: (id: string) => api.delete(`/api/v1/sessions/${id}`),
  process: (id: string) => api.post<Skill[]>(`/api/v1/sessions/${id}/process`),
  listQuestions: (id: string) =>
    api.get<Question[]>(`/api/v1/sessions/${id}/questions`),
  submitAnswer: (sessionId: string, questionId: string, text: string) =>
    api.post<SubmitAnswerResult>(
      `/api/v1/sessions/${sessionId}/questions/${questionId}/answer`,
      { text }
    ),
  evaluate: (id: string) =>
    api.post<Evaluation>(`/api/v1/sessions/${id}/evaluate`),
  getEvaluation: (id: string) =>
    api.get<Evaluation>(`/api/v1/sessions/${id}/evaluation`),
};

export default api;
