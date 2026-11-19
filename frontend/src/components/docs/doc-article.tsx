import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { routes } from "@/lib/routes";

/** A documentation page. `html` is rendered at build time from the repository's Markdown. */
export function DocArticle({ title, html, headings }: { title: string; html: string; headings: Array<{ id: string; text: string }> }) {
  return (
    <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_220px]">
      <article className="min-w-0">
        <Link href={routes.docs} className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
          <ArrowLeft className="size-4" aria-hidden="true" /> All documentation
        </Link>
        {html.trimStart().startsWith("<h1") ? null : <h1 className="mb-6 font-display text-4xl font-bold tracking-[-0.03em] text-ink">{title}</h1>}
        <div className="prose-docs" aria-label={title} dangerouslySetInnerHTML={{ __html: html }} />
      </article>
      {headings.length > 1 ? (
        <nav aria-label="On this page" className="hidden lg:block">
          <div className="sticky top-24">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-subtle">On this page</p>
            <ul className="mt-3 space-y-2 border-l border-line pl-4 text-sm">
              {headings.map((heading) => (
                <li key={heading.id}>
                  <a href={`#${heading.id}`} className="text-muted hover:text-ink">
                    {heading.text}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </nav>
      ) : null}
    </div>
  );
}
