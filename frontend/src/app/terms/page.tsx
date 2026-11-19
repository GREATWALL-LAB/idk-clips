import type { Metadata } from "next";
import { routes } from "@/lib/routes";
import { pageMetadata } from "@/lib/seo";
import { DocArticle } from "@/components/docs/doc-article";
import { DocsShell } from "@/components/docs/docs-shell";
import { LEGAL, readDoc } from "@/lib/docs";

export const metadata: Metadata = pageMetadata({
  title: LEGAL.terms.title,
  description: "The terms for using IDK Clips and the hosted website.",
  path: routes.terms,
});

export default function TermsPage() {
  const { html, headings } = readDoc(LEGAL.terms.file);
  return (
    <DocsShell>
      <DocArticle title={LEGAL.terms.title} html={html} headings={headings} />
    </DocsShell>
  );
}
