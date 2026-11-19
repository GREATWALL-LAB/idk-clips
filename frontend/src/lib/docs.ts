import { readFileSync } from "node:fs";
import path from "node:path";
import { Marked, type Tokens } from "marked";

/**
 * Documentation pages are rendered at build time from the repository's own Markdown
 * files, so the website, GitHub and a downloaded copy always show the same text.
 * The files are part of this repository (trusted content), never user input.
 */
export type DocEntry = {
  slug: string;
  title: string;
  file: string;
  summary: string;
  group: string;
  /** Optional search title and description (otherwise title and summary are used). */
  seoTitle?: string;
  description?: string;
};

export const DOCS: DocEntry[] = [
  { group: "Start here", slug: "installation", title: "Installation", file: "docs/INSTALLATION.md", summary: "Requirements, setup scripts and the requirements checker for Windows, Linux and macOS.", seoTitle: "Install IDK Clips on Windows, Linux or macOS", description: "Install IDK Clips, the free open-source AI video clipping tool: requirements (Python, Node.js, FFmpeg, Ollama) and setup scripts for Windows, Linux and macOS." },
  { group: "Start here", slug: "local-mode", title: "Run locally", file: "docs/LOCAL_MODE.md", summary: "Use IDK Clips on your own computer with no account and nothing uploaded.", seoTitle: "Run IDK Clips locally: private AI video clipping", description: "Run IDK Clips entirely on your own computer: no account, no uploads. Transcribe, find clips with a local AI model in Ollama and export captioned MP4s." },
  { group: "Start here", slug: "online", title: "Use online", file: "docs/USING_ONLINE.md", summary: "Log in on the website and let your own computer do the processing." },
  { group: "Start here", slug: "workers", title: "Connect a worker", file: "docs/WORKERS.md", summary: "Pair your computer, keep it running, revoke it, and how it stays secure." },
  { group: "Configure", slug: "configuration", title: "Configuration", file: "docs/CONFIGURATION.md", summary: "Every setting, plus how to set up FFmpeg, faster-whisper and Ollama." },
  { group: "Configure", slug: "youtube", title: "YouTube videos", file: "docs/YOUTUBE.md", summary: "How YouTube links work and why IDK Clips never downloads from YouTube." },
  { group: "Configure", slug: "troubleshooting", title: "Troubleshooting", file: "docs/TROUBLESHOOTING.md", summary: "Fixes for the problems people run into most.", description: "Fixes for common IDK Clips problems: FFmpeg not found, Ollama not reachable, slow transcription, workers that do not connect and failed exports." },
  { group: "Run a server", slug: "self-hosting", title: "Self-hosting", file: "docs/SELF_HOSTING.md", summary: "Run IDK Clips for a team, with Docker or directly.", seoTitle: "Self-host IDK Clips: open-source AI video clipping server", description: "Self-host IDK Clips for a team or community with Docker Compose or directly on Linux, in server or hybrid mode, with security, limits and backups explained." },
  { group: "Run a server", slug: "deployment", title: "Deployment and hosting", file: "docs/DEPLOYMENT.md", summary: "The low-cost hosting plan, free-tier limits and the exact deployment steps." },
  { group: "Run a server", slug: "architecture", title: "Architecture", file: "docs/ARCHITECTURE.md", summary: "How the website, API, job pipeline and workers fit together.", seoTitle: "IDK Clips architecture", description: "How IDK Clips works inside: Next.js website, FastAPI backend, job pipeline, faster-whisper transcription, AI clip detection, FFmpeg rendering and workers." },
  { group: "Run a server", slug: "testing", title: "Testing", file: "docs/TESTING.md", summary: "Running the test suites and what they cover.", description: "How to run the IDK Clips test suites (backend, processing, web interface and security checks) and what each of them covers." },
  { group: "Project", slug: "contributing", title: "Contributing", file: "CONTRIBUTING.md", summary: "Development setup, code style and how to send a change." },
  { group: "Project", slug: "security", title: "Security policy", file: "SECURITY.md", summary: "How to report a vulnerability and how IDK Clips protects your data." },
  { group: "Project", slug: "code-of-conduct", title: "Code of conduct", file: "CODE_OF_CONDUCT.md", summary: "How we work together.", description: "The code of conduct for the IDK Clips open-source community: how contributors and maintainers work together and report problems." },
  { group: "Project", slug: "license", title: "MIT License", file: "LICENSE", summary: "The license IDK Clips is released under.", description: "IDK Clips is released under the MIT License: free to use, modify and share, including commercially, as long as the copyright notice is kept." },
];

/** Pages with their own short URL instead of /docs/<slug>/. */
export const LEGAL = {
  privacy: { title: "Privacy", file: "docs/PRIVACY.md" },
  terms: { title: "Terms of use", file: "docs/TERMS.md" },
} as const;

const REPO_ROOT = path.resolve(process.cwd(), "..");

function routeForFile(href: string): string | null {
  const [target, hash] = href.split("#");
  const base = path.posix.basename(target.replace(/\\/g, "/"));
  if (!base) return null;
  if (base.toUpperCase() === "PRIVACY.MD") return `/privacy/${hash ? `#${hash}` : ""}`;
  if (base.toUpperCase() === "TERMS.MD") return `/terms/${hash ? `#${hash}` : ""}`;
  const doc = DOCS.find((d) => path.posix.basename(d.file).toUpperCase() === base.toUpperCase());
  return doc ? `/docs/${doc.slug}/${hash ? `#${hash}` : ""}` : null;
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/<[^>]+>/g, "")
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-");
}

function renderer(): Marked {
  const marked = new Marked({ gfm: true });
  marked.use({
    walkTokens(token) {
      if (token.type === "link") {
        const link = token as Tokens.Link;
        const scheme = /^([a-z][a-z0-9+.-]*):/i.exec(link.href)?.[1]?.toLowerCase();
        if (scheme && !["http", "https", "mailto"].includes(scheme)) {
          link.href = "#"; // never javascript:, data: or other active schemes
        } else if (!scheme && !link.href.startsWith("#") && !link.href.startsWith("/")) {
          // Links between repository files become links between documentation pages.
          link.href = routeForFile(link.href) ?? link.href;
        }
      }
    },
    renderer: {
      heading({ tokens, depth, text }) {
        const inner = this.parser.parseInline(tokens);
        return `<h${depth} id="${slugify(text)}">${inner}</h${depth}>\n`;
      },
      html() {
        return ""; // raw HTML in Markdown is never passed through
      },
    },
  });
  return marked;
}

export function readDoc(file: string): { html: string; headings: Array<{ id: string; text: string }> } {
  const source = readFileSync(path.join(REPO_ROOT, file), "utf8");
  if (!file.toLowerCase().endsWith(".md")) {
    const escaped = source.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return { html: `<pre>${escaped}</pre>`, headings: [] };
  }
  const headings = [...source.matchAll(/^##\s+(.+)$/gm)].map((match) => ({ id: slugify(match[1]), text: match[1].replace(/[`*_]/g, "") }));
  const html = renderer().parse(source, { async: false }) as string;
  return { html, headings };
}

export function findDoc(slug: string): DocEntry | undefined {
  return DOCS.find((doc) => doc.slug === slug);
}
