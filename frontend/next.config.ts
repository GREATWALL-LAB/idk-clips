import type { NextConfig } from "next";

/**
 * The web interface is a static export (`out/`): plain HTML, CSS and JavaScript.
 *
 * - In local mode the backend serves `out/` itself, so running IDK Clips needs no Node.js.
 * - The hosted site can go to any static host (for example Cloudflare Pages).
 *
 * Static exports cannot set HTTP headers from Next.js, so security headers are written
 * by `scripts/postbuild.mjs` (a `_headers` file for static hosts) and by the backend
 * when it serves the files (backend/app/core/webapp.py).
 */
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  reactStrictMode: true,
  poweredByHeader: false,
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
