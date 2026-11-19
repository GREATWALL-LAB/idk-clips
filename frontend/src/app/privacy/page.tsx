import type { Metadata } from "next";
import { routes } from "@/lib/routes";
import { pageMetadata } from "@/lib/seo";
import { DocArticle } from "@/components/docs/doc-article";
import { DocsShell } from "@/components/docs/docs-shell";
import { LEGAL, readDoc } from "@/lib/docs";

export const metadata: Metadata = pageMetadata({
  title: LEGAL.privacy.title,
  description: "What IDK Clips stores, where, for how long, and how to delete it.",
  path: routes.privacy,
});

export default function PrivacyPage() {
  const { html, headings } = readDoc(LEGAL.privacy.file);
  return (
    <DocsShell>
      <DocArticle title={LEGAL.privacy.title} html={html} headings={headings} />
    </DocsShell>
  );
}
