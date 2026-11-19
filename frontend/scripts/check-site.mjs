// Checks the built site in out/ for SEO and link problems. Run after `npm run build`.
//
// - every indexable page has one <title>, a meta description and exactly one <h1>;
// - titles and descriptions are unique across indexable pages;
// - with NEXT_PUBLIC_SITE_URL set: each page's canonical URL is its own address on that
//   site, and no published URL points at localhost;
// - internal links and assets resolve to files in out/;
// - structured data (JSON-LD) parses; sitemap.xml lists only pages that exist.
//
// Exits with code 1 when something is wrong, so CI and deployments stop.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = fileURLToPath(new URL("../out", import.meta.url));
const SITE = (process.env.NEXT_PUBLIC_SITE_URL || "").replace(/\/+$/, "");
const problems = [];
const warn = (msg) => problems.push(msg);

if (!existsSync(OUT)) {
  console.error("[check-site] out/ does not exist. Run `npm run build` first.");
  process.exit(1);
}

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const files = walk(OUT);
const pages = files.filter((f) => f.endsWith(".html"));

function routeOf(file) {
  const rel = relative(OUT, file).split(sep).join("/");
  if (rel === "index.html") return "/";
  if (rel.endsWith("/index.html")) return `/${rel.slice(0, -"index.html".length)}`;
  return `/${rel.replace(/\.html$/, "")}`;
}

function resolves(path) {
  const clean = decodeURIComponent(path.split("#")[0].split("?")[0]);
  if (clean === "" || clean === "/") return existsSync(join(OUT, "index.html"));
  const target = join(OUT, clean);
  return existsSync(target) && statSync(target).isFile()
    ? true
    : existsSync(join(target, "index.html")) || existsSync(`${target}.html`);
}

const attr = (tag, name) => new RegExp(`${name}="([^"]*)"`).exec(tag)?.[1];
const seenTitles = new Map();
const seenDescriptions = new Map();
let indexable = 0;

for (const file of pages) {
  const html = readFileSync(file, "utf8");
  const route = routeOf(file);
  const isErrorPage = route === "/404" || route.startsWith("/_not-found") || route === "/404/";
  const noindex = /<meta name="robots" content="[^"]*noindex/.test(html);

  for (const match of html.matchAll(/(?:href|src)="(\/[^"]*)"/g)) {
    const url = match[1];
    if (url.startsWith("//") || url.startsWith("/api/")) continue;
    if (!resolves(url)) warn(`${route}: broken internal link ${url}`);
  }
  for (const match of html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)) {
    try {
      JSON.parse(match[1]);
    } catch {
      warn(`${route}: invalid JSON-LD`);
    }
  }
  // Metadata must never point at a development address (docs text may mention one).
  const metadataUrls = [
    ...html.matchAll(/<link rel="(?:canonical|alternate)"[^>]*href="([^"]*)"/g),
    ...html.matchAll(/<meta (?:property|name)="(?:og|twitter):[^"]*" content="([^"]*)"/g),
    ...[...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].flatMap((m) =>
      [...m[1].matchAll(/"(https?:\/\/[^"]*)"/g)],
    ),
  ].map((m) => m[1]);
  for (const url of metadataUrls) {
    if (/^https?:\/\/(localhost|127\.0\.0\.1)([:/]|$)/.test(url)) warn(`${route}: metadata points at ${url}`);
  }
  if (noindex || isErrorPage) continue;

  indexable += 1;
  const title = /<title>([^<]*)<\/title>/.exec(html)?.[1]?.trim();
  const descTag = /<meta name="description"[^>]*>/.exec(html)?.[0];
  const description = descTag ? attr(descTag, "content") : undefined;
  const h1s = (html.match(/<h1[\s>]/g) || []).length;
  if (!title) warn(`${route}: missing <title>`);
  if (!description) warn(`${route}: missing meta description`);
  else if (description.length < 50 || description.length > 170)
    warn(`${route}: meta description is ${description.length} characters (aim for 50-170)`);
  if (h1s !== 1) warn(`${route}: has ${h1s} <h1> elements (expected 1)`);
  if (title) {
    if (seenTitles.has(title)) warn(`${route}: same title as ${seenTitles.get(title)}`);
    seenTitles.set(title, route);
  }
  if (description) {
    if (seenDescriptions.has(description)) warn(`${route}: same description as ${seenDescriptions.get(description)}`);
    seenDescriptions.set(description, route);
  }
  if (SITE) {
    const canonicalTag = /<link rel="canonical"[^>]*>/.exec(html)?.[0];
    const canonical = canonicalTag ? attr(canonicalTag, "href") : undefined;
    if (!canonical) warn(`${route}: missing canonical link`);
    else if (canonical.replace(/\/?$/, "/") !== `${SITE}${route}`.replace(/\/?$/, "/"))
      warn(`${route}: canonical ${canonical} does not match ${SITE}${route}`);
  }
}

for (const required of ["robots.txt", "sitemap.xml", "llms.txt", "manifest.webmanifest"]) {
  if (!existsSync(join(OUT, required))) warn(`missing /${required}`);
}
if (existsSync(join(OUT, "sitemap.xml"))) {
  const sitemap = readFileSync(join(OUT, "sitemap.xml"), "utf8");
  const urls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
  if (SITE && urls.length === 0) warn("sitemap.xml lists no pages");
  for (const url of urls) {
    if (!url.startsWith(`${SITE}/`)) warn(`sitemap.xml: ${url} is not on ${SITE}`);
    else if (!resolves(url.slice(SITE.length) || "/")) warn(`sitemap.xml: ${url} has no page`);
  }
}

console.log(`[check-site] ${pages.length} HTML files, ${indexable} indexable pages, site URL: ${SITE || "(not set)"}`);
if (problems.length) {
  for (const p of problems) console.error(`  ✗ ${p}`);
  console.error(`[check-site] ${problems.length} problem(s) found.`);
  process.exit(1);
}
console.log("[check-site] no problems found.");
