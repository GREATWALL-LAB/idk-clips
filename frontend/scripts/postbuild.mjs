// Runs after `next build`:
//  1. removes media files from the export, so test videos in public/ are never published;
//  2. writes `out/_headers` (Cloudflare Pages / Netlify format) with security headers and a
//     Content-Security-Policy that allows only this site, the API and the local worker bridge.
import { readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = fileURLToPath(new URL("../out/", import.meta.url));
const MEDIA = /\.(mp4|mov|mkv|webm|avi|m4v|wmv|flv|mpg|mpeg|wav|mp3|m4a|aac|flac|ogg|opus)$/i;

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

let removed = 0;
for (const file of walk(OUT)) {
  if (MEDIA.test(file)) {
    rmSync(file);
    removed += 1;
    console.warn(`[postbuild] not publishing media file: ${relative(OUT, file)}`);
  }
}

function origin(value) {
  if (!value) return null;
  try {
    return new URL(value).origin;
  } catch {
    throw new Error(`NEXT_PUBLIC_API_URL is not a valid URL: ${value}`);
  }
}

const api = origin(process.env.NEXT_PUBLIC_API_URL);
// The worker bridge always listens on the loopback interface (hybrid mode).
const bridge = "http://127.0.0.1:*";
const sources = (...values) => values.filter(Boolean).join(" ");
const csp = [
  "default-src 'self'",
  // Next.js inlines small bootstrap scripts and styles in exported pages.
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  `img-src ${sources("'self'", "data:", "blob:", api, bridge, "https://i.ytimg.com")}`,
  `media-src ${sources("'self'", "blob:", api, bridge)}`,
  `connect-src ${sources("'self'", api, bridge)}`,
  "font-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const headers = `/*
  Content-Security-Policy: ${csp}
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Strict-Transport-Security: max-age=31536000

/_next/static/*
  Cache-Control: public, max-age=31536000, immutable
`;
writeFileSync(join(OUT, "_headers"), headers, "utf8");
console.log(`[postbuild] wrote _headers (API: ${api ?? "same origin"}); removed ${removed} media file(s)`);
