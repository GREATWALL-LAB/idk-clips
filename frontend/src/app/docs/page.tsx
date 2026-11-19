import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { DocsShell } from "@/components/docs/docs-shell";
import { DOCS } from "@/lib/docs";
import { routes } from "@/lib/routes";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Documentation",
  description:
    "IDK Clips documentation: install the free AI video clipping tool on Windows, Linux or macOS, run it locally, connect a worker, configure AI models and self-host it.",
  path: routes.docs,
});

export default function DocsIndexPage() {
  const groups = [...new Set(DOCS.map((doc) => doc.group))];
  return (
    <DocsShell>
      <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-brand">Documentation</p>
      <h1 className="mt-3 font-display text-5xl font-bold tracking-[-0.035em] text-ink">Everything about IDK Clips</h1>
      <p className="mt-4 max-w-2xl text-lg text-ink-soft">
        Install it, run it on your own computer, connect a worker for online use, or host it for a team. The same guides live in the repository&apos;s{" "}
        <code className="rounded bg-mist px-1.5 py-0.5 font-mono text-sm">docs/</code> folder.
      </p>
      <div className="mt-12 space-y-12">
        {groups.map((group) => (
          <section key={group} aria-labelledby={`group-${group}`}>
            <h2 id={`group-${group}`} className="text-sm font-semibold uppercase tracking-[0.12em] text-subtle">
              {group}
            </h2>
            <ul className="mt-4 grid gap-3 sm:grid-cols-2">
              {DOCS.filter((doc) => doc.group === group).map((doc) => (
                <li key={doc.slug}>
                  <Link href={routes.doc(doc.slug)} className="group flex h-full flex-col rounded-3xl border border-line bg-surface p-5 transition-colors hover:border-brand/40">
                    <span className="flex items-center justify-between gap-2 font-semibold text-ink">
                      {doc.title}
                      <ArrowRight className="size-4 text-subtle transition-transform group-hover:translate-x-0.5 group-hover:text-brand" aria-hidden="true" />
                    </span>
                    <span className="mt-1.5 text-sm text-muted">{doc.summary}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
        <p className="text-sm text-subtle">
          Also see the <Link href={routes.privacy} className="font-medium text-brand underline-offset-2 hover:underline">privacy notice</Link> and the{" "}
          <Link href={routes.terms} className="font-medium text-brand underline-offset-2 hover:underline">terms of use</Link>.
        </p>
      </div>
    </DocsShell>
  );
}
