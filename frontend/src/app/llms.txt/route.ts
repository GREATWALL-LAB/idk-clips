import { BRAND, publicLinks } from "@/lib/config";
import { DOCS } from "@/lib/docs";
import { FAQ } from "@/lib/faq";
import { routes } from "@/lib/routes";
import { absoluteUrl } from "@/lib/seo";

export const dynamic = "force-static";

/**
 * /llms.txt: a plain-text summary for AI assistants and answer engines (llmstxt.org).
 * Generated from the same sources as the website, so it never drifts from it.
 */
export function GET() {
  const link = (path: string) => absoluteUrl(path) ?? path;
  const github = publicLinks().github;
  const lines = [
    `# ${BRAND.name}`,
    "",
    `> ${BRAND.description}`,
    "",
    `${BRAND.name} is free, open-source software under the MIT License. It has no subscriptions, paid tiers, watermarks or administrator accounts.`,
    "It runs in three modes: locally on one computer with no account; as a website where each user's own computer (a paired worker) processes their videos; or as a self-hosted server.",
    "",
    "## Official links",
    "",
    `- Website: ${link(routes.home)}`,
    ...(github ? [`- Source code (GitHub): ${github}`] : []),
    `- Documentation: ${link(routes.docs)}`,
    "",
    "## Documentation",
    "",
    ...DOCS.map((doc) => `- [${doc.title}](${link(routes.doc(doc.slug))}): ${doc.summary}`),
    "",
    "## FAQ",
    "",
    ...FAQ.flatMap((item) => [`### ${item.question}`, "", item.answer, ""]),
  ];
  return new Response(lines.join("\n"), { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
