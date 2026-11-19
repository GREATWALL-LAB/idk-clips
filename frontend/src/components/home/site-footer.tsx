"use client";

import Link from "next/link";
import { Logo } from "@/components/brand/logo";
import { publicLinks } from "@/lib/config";
import { routes } from "@/lib/routes";

export function SiteFooter() {
  const github = publicLinks().github;
  const columns = [
    {
      title: "Product",
      links: [
        { href: "/#features", label: "Features" },
        { href: "/#how-it-works", label: "How it works" },
        { href: routes.dashboard, label: "Open the app" },
      ],
    },
    {
      title: "Documentation",
      links: [
        { href: routes.doc("installation"), label: "Installation" },
        { href: routes.doc("workers"), label: "Connect a worker" },
        { href: routes.doc("self-hosting"), label: "Self-hosting" },
        { href: routes.doc("troubleshooting"), label: "Troubleshooting" },
      ],
    },
    {
      title: "Project",
      links: [
        ...(github ? [{ href: github, label: "GitHub", external: true }] : []),
        { href: routes.doc("contributing"), label: "Contributing" },
        { href: routes.doc("security"), label: "Security" },
        { href: routes.doc("license"), label: "MIT License" },
      ],
    },
    {
      title: "Legal",
      links: [
        { href: routes.privacy, label: "Privacy" },
        { href: routes.terms, label: "Terms" },
        { href: routes.doc("code-of-conduct"), label: "Code of conduct" },
      ],
    },
  ];
  return (
    <footer className="border-t border-line bg-surface">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[1.2fr_2fr]">
        <div>
          <Logo />
          <p className="mt-4 max-w-xs text-sm leading-relaxed text-muted">
            Free and open-source AI video clipping. Long videos in, short clips out, on your own hardware.
          </p>
        </div>
        <nav aria-label="Footer" className="grid grid-cols-2 gap-8 sm:grid-cols-4">
          {columns.map((column) => (
            <div key={column.title}>
              <p className="text-sm font-semibold text-ink">{column.title}</p>
              <ul className="mt-3 space-y-2">
                {column.links.map((link) => (
                  <li key={link.href}>
                    {"external" in link ? (
                      <a href={link.href} rel="noopener" className="text-sm text-muted transition-colors hover:text-ink">
                        {link.label}
                      </a>
                    ) : (
                      <Link href={link.href} className="text-sm text-muted transition-colors hover:text-ink">
                        {link.label}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </div>
      <div className="border-t border-line">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-6 text-xs text-subtle sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <span>© {new Date().getFullYear()} IDK Clips contributors · Released under the MIT License</span>
          <span>Built with Next.js, FastAPI, faster-whisper, Ollama and FFmpeg</span>
        </div>
      </div>
    </footer>
  );
}
