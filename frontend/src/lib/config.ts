/**
 * Frontend configuration. NEXT_PUBLIC_* values are inlined at build time, so rebuild
 * (or restart `npm run dev`) after changing them. They are visible to every visitor:
 * never put secrets in them.
 *
 * API location:
 * - `npm run dev`: http://localhost:8000 (the backend's default), unless set.
 * - production build without NEXT_PUBLIC_API_URL: the same origin as the page. That is
 *   how local mode works: the backend serves this exported site itself.
 * - hosted site: set NEXT_PUBLIC_API_URL to the API's public address.
 */
const DEV_API_URL = "http://localhost:8000";

const configuredApi = process.env.NEXT_PUBLIC_API_URL;

export const API_URL = (configuredApi ?? (process.env.NODE_ENV === "development" ? DEV_API_URL : "")).replace(/\/+$/, "");
export const API_V1 = `${API_URL}/api/v1`;

/** Sent with every state-changing request; the backend rejects requests without it (CSRF defense). */
export const CSRF_HEADER = { "X-Requested-With": "OpenClip" } as const;

/** Only absolute https links are used for public project links; anything else is ignored. */
export function cleanPublicUrl(value: string | undefined | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString().replace(/\/+$/, "") : null;
  } catch {
    return null;
  }
}

/**
 * Real project links. They stay hidden until they are configured, so the site never
 * shows a placeholder or a made-up repository address.
 */
export function publicLinks() {
  return {
    github: cleanPublicUrl(process.env.NEXT_PUBLIC_GITHUB_URL),
  };
}

/** The public address of the hosted website (https only), for canonical and social links. */
export function siteUrl(): URL | undefined {
  const url = cleanPublicUrl(process.env.NEXT_PUBLIC_SITE_URL);
  return url ? new URL(url) : undefined;
}

export const BRAND = {
  name: "IDK Clips",
  tagline: "Free, open-source AI video clipping",
  /** Page title of the home page. */
  title: "IDK Clips · free, open-source AI video clipping",
  /** Home page title: what people search for, in plain words. */
  homeTitle: "IDK Clips: free, open-source AI video clip generator",
  homeDescription:
    "Free, open-source AI video clipping tool. Turn podcasts and long videos into captioned Shorts, Reels and TikToks in 9:16, 4:5, 1:1 or 16:9, locally or self-hosted.",
  description:
    "Turn long videos into short clips with AI transcription, moment detection, captions and four export shapes. Free, MIT licensed, and it runs on your own computer.",
} as const;
