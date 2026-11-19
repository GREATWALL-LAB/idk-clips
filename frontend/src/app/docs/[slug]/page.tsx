import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DocArticle } from "@/components/docs/doc-article";
import { DocsShell } from "@/components/docs/docs-shell";
import { JsonLd } from "@/components/seo/json-ld";
import { DOCS, findDoc, readDoc } from "@/lib/docs";
import { routes } from "@/lib/routes";
import { pageMetadata, techArticleLd } from "@/lib/seo";

export const dynamicParams = false;

export function generateStaticParams() {
  return DOCS.map((doc) => ({ slug: doc.slug }));
}

export async function generateMetadata({ params }: PageProps<"/docs/[slug]">): Promise<Metadata> {
  const doc = findDoc((await params).slug);
  return doc
    ? pageMetadata({ title: doc.seoTitle ?? doc.title, description: doc.description ?? doc.summary, path: routes.doc(doc.slug) })
    : {};
}

export default async function DocPage({ params }: PageProps<"/docs/[slug]">) {
  const doc = findDoc((await params).slug);
  if (!doc) notFound();
  const { html, headings } = readDoc(doc.file);
  return (
    <DocsShell>
      <JsonLd data={techArticleLd(doc.seoTitle ?? doc.title, doc.description ?? doc.summary, routes.doc(doc.slug))} />
      <DocArticle title={doc.title} html={html} headings={headings} />
    </DocsShell>
  );
}
