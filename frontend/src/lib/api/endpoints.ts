import { apiFetch } from "@/lib/api/client";
import type {
  Account,
  AISettings,
  AIStatus,
  AuthStatus,
  CodeSent,
  RegisterResult,
  CaptionLine,
  Clip,
  ClipCaptions,
  ClipList,
  ClipUpdate,
  ClientConfig,
  Dashboard,
  HealthResponse,
  Job,
  Meta,
  PairingCode,
  ProcessingOptions,
  Project,
  ProjectList,
  SystemStatusResponse,
  TransferToken,
  Transcript,
  User,
  Worker,
  YouTubeVideo,
} from "@/lib/api/types";

type Signal = AbortSignal | undefined;

export const api = {
  // System
  health: (signal?: Signal) => apiFetch<HealthResponse>("/health", { signal, timeoutMs: 5_000 }),
  meta: (signal?: Signal) => apiFetch<Meta>("/meta", { signal, timeoutMs: 8_000 }),
  systemStatus: (signal?: Signal) => apiFetch<SystemStatusResponse>("/system/status", { signal, timeoutMs: 15_000 }),
  config: (signal?: Signal) => apiFetch<ClientConfig>("/config", { signal }),
  dashboard: (signal?: Signal) => apiFetch<Dashboard>("/dashboard", { signal }),

  // Auth
  authStatus: (signal?: Signal) => apiFetch<AuthStatus>("/auth/status", { signal }),
  me: (signal?: Signal) => apiFetch<User>("/auth/me", { signal }),
  login: (email: string, password: string, age_confirmed = false) =>
    apiFetch<User>("/auth/login", { method: "POST", json: { email, password, ...(age_confirmed ? { age_confirmed: true } : {}) } }),
  /** `age_confirmed` must be the person's own Yes to the 18+ question; it is never assumed. */
  register: (email: string, password: string, display_name: string, age_confirmed: boolean) =>
    apiFetch<RegisterResult>("/auth/register", { method: "POST", json: { email, password, display_name, age_confirmed } }),
  verifyEmail: (email: string, code: string) => apiFetch<User>("/auth/verify-email", { method: "POST", json: { email, code } }),
  resendCode: (email: string) => apiFetch<CodeSent>("/auth/resend-code", { method: "POST", json: { email } }),
  requestPasswordReset: (email: string) => apiFetch<CodeSent>("/auth/password-reset/request", { method: "POST", json: { email } }),
  confirmPasswordReset: (email: string, code: string, new_password: string) =>
    apiFetch<void>("/auth/password-reset/confirm", { method: "POST", json: { email, code, new_password } }),
  logout: () => apiFetch<void>("/auth/logout", { method: "POST" }),
  changePassword: (current_password: string, new_password: string) =>
    apiFetch<void>("/auth/password", { method: "POST", json: { current_password, new_password } }),

  // Account and data
  account: (signal?: Signal) => apiFetch<Account>("/account", { signal }),
  updateAccount: (body: { display_name?: string; retention_days?: number }) =>
    apiFetch<Account>("/account", { method: "PATCH", json: body }),
  deleteAllProjects: () => apiFetch<{ deleted_projects: number }>("/account/projects", { method: "DELETE" }),
  deleteAccount: (password: string) => apiFetch<void>("/account/delete", { method: "POST", json: { password } }),

  // Projects
  projects: (signal?: Signal, limit = 100) => apiFetch<ProjectList>(`/projects?limit=${limit}`, { signal }),
  project: (id: string, signal?: Signal) => apiFetch<Project>(`/projects/${encodeURIComponent(id)}`, { signal }),
  createProject: (body: ProcessingOptions & { name: string }) => apiFetch<Project>("/projects", { method: "POST", json: body }),
  importUrl: (body: ProcessingOptions & { url: string; name?: string }) =>
    apiFetch<Project>("/projects/import-url", { method: "POST", json: body }),
  youtubeLookup: (url: string) => apiFetch<YouTubeVideo>("/projects/youtube/lookup", { method: "POST", json: { url }, timeoutMs: 15_000 }),
  createFromYouTube: (body: ProcessingOptions & { url: string; name?: string }) =>
    apiFetch<Project>("/projects/from-youtube", { method: "POST", json: body, timeoutMs: 20_000 }),
  updateProject: (id: string, body: Partial<ProcessingOptions & { name: string }>) =>
    apiFetch<Project>(`/projects/${id}`, { method: "PATCH", json: body }),
  deleteProject: (id: string) => apiFetch<void>(`/projects/${id}`, { method: "DELETE" }),
  processProject: (id: string, body: { language?: string; whisper_model?: string; transcribe?: boolean } = {}) =>
    apiFetch<Job>(`/projects/${id}/process`, { method: "POST", json: body }),
  transcript: (id: string, signal?: Signal) => apiFetch<Transcript>(`/projects/${id}/transcript`, { signal }),

  // Jobs
  job: (id: string, signal?: Signal) => apiFetch<Job>(`/jobs/${id}`, { signal }),
  cancelJob: (id: string) => apiFetch<Job>(`/jobs/${id}/cancel`, { method: "POST" }),

  // Clips
  projectClips: (projectId: string, signal?: Signal) => apiFetch<ClipList>(`/projects/${projectId}/clips`, { signal }),
  clips: (status: string | null, signal?: Signal) =>
    apiFetch<ClipList>(`/clips${status ? `?status=${encodeURIComponent(status)}` : ""}`, { signal }),
  clip: (id: string, signal?: Signal) => apiFetch<Clip>(`/clips/${encodeURIComponent(id)}`, { signal }),
  createClip: (projectId: string, body: { title: string; start_seconds: number; end_seconds: number }) =>
    apiFetch<Clip>(`/projects/${projectId}/clips`, { method: "POST", json: body }),
  updateClip: (id: string, body: ClipUpdate) => apiFetch<Clip>(`/clips/${id}`, { method: "PATCH", json: body }),
  deleteClip: (id: string) => apiFetch<void>(`/clips/${id}`, { method: "DELETE" }),
  clipCaptions: (id: string, signal?: Signal) => apiFetch<ClipCaptions>(`/clips/${id}/captions`, { signal }),
  resetCaptions: (id: string) => apiFetch<Clip>(`/clips/${id}`, { method: "PATCH", json: { caption_lines: [] as CaptionLine[] } }),
  renderClip: (id: string) => apiFetch<Job>(`/clips/${id}/render`, { method: "POST" }),
  renderAll: (projectId: string) => apiFetch<Job[]>(`/projects/${projectId}/render-all`, { method: "POST" }),

  // Workers (hybrid mode)
  workers: (signal?: Signal) => apiFetch<Worker[]>("/workers", { signal }),
  createPairingCode: () => apiFetch<PairingCode>("/workers/pairing-codes", { method: "POST" }),
  updateWorker: (id: string, body: { name?: string; preferred_model?: string }) =>
    apiFetch<Worker>(`/workers/${id}`, { method: "PATCH", json: body }),
  deleteWorker: (id: string) => apiFetch<void>(`/workers/${id}`, { method: "DELETE" }),
  transferToken: (workerId: string, body: { scope: "read" | "upload"; project_id?: string }) =>
    apiFetch<TransferToken>(`/workers/${workerId}/transfer-tokens`, { method: "POST", json: body }),

  // AI settings
  aiSettings: (signal?: Signal) => apiFetch<AISettings>("/settings/ai", { signal }),
  updateAiSettings: (body: Partial<Pick<AISettings, "provider" | "ollama_base_url" | "ollama_model">>) =>
    apiFetch<AISettings>("/settings/ai", { method: "PUT", json: body }),
  aiStatus: (signal?: Signal) => apiFetch<AIStatus>("/ai/status", { signal, timeoutMs: 15_000 }),
};
