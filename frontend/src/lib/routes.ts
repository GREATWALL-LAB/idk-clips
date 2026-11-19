/**
 * App routes. Project and clip pages take their IDs from the query string, so the whole
 * site can be a static export (served by the backend in local mode, or by any static host).
 */
export const routes = {
  home: "/",
  dashboard: "/dashboard/",
  projects: "/projects/",
  newProject: "/projects/new/",
  clips: "/clips/",
  workers: "/workers/",
  settings: "/settings/",
  login: "/login/",
  register: "/register/",
  forgotPassword: "/forgot-password/",
  verify: (email: string) => `/verify/?email=${encodeURIComponent(email)}`,
  docs: "/docs/",
  privacy: "/privacy/",
  terms: "/terms/",
  project: (id: string) => `/projects/view/?id=${encodeURIComponent(id)}`,
  clip: (projectId: string, clipId: string) =>
    `/clips/edit/?project=${encodeURIComponent(projectId)}&clip=${encodeURIComponent(clipId)}`,
  doc: (slug: string) => `/docs/${slug}/`,
} as const;

/** IDs from the URL are only used in API paths after this check. */
export function isUuid(value: string | null | undefined): value is string {
  return Boolean(value && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value));
}
