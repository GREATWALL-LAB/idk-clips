"use client";

import { BookOpen, GitFork, HeartHandshake, Scale, ShieldCheck } from "lucide-react";
import { Marker, Reveal } from "@/components/home/motion";
import { ButtonAnchor, ButtonLink } from "@/components/ui/button";
import { publicLinks } from "@/lib/config";
import { routes } from "@/lib/routes";

const PRINCIPLES = [
  { icon: Scale, title: "MIT licensed", text: "Use it, change it, ship it, commercially or not. The full license is in the repository." },
  { icon: HeartHandshake, title: "Free, for real", text: "No subscriptions, no paid tiers, no credits, no watermark. Every feature is for everyone." },
  { icon: ShieldCheck, title: "Built in the open", text: "Read exactly what happens to your videos. Security reports are handled privately and quickly." },
];

export function OpenSource() {
  const github = publicLinks().github;
  return (
    <section id="open-source" className="scroll-mt-20 pb-24 sm:pb-32" aria-labelledby="open-source-title">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="overflow-hidden rounded-[36px] border border-line bg-surface shadow-card">
          <div className="grid gap-12 p-7 sm:p-12 lg:grid-cols-[1.1fr_0.9fr] lg:p-16">
            <Reveal>
              <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-brand">Open source</p>
              <h2 id="open-source-title" className="mt-3 font-display text-4xl font-bold leading-[1.02] tracking-[-0.035em] text-ink sm:text-6xl">
                Made by creators, <Marker>for</Marker> creators.
              </h2>
              <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-soft">
                IDK Clips exists to make good clips easier to produce, not to charge you for it. Improve the AI prompts, add a language, fix a bug or write
                a guide: contributions of every size are welcome.
              </p>
              <div className="mt-9 flex flex-wrap gap-3">
                {github ? (
                  <ButtonAnchor href={github} variant="dark" size="lg" rel="noopener" icon={<GitFork className="size-4" aria-hidden="true" />}>
                    View on GitHub
                  </ButtonAnchor>
                ) : null}
                <ButtonLink href={routes.doc("contributing")} size="lg" variant={github ? "secondary" : "dark"} icon={<HeartHandshake className="size-4" aria-hidden="true" />}>
                  How to contribute
                </ButtonLink>
                <ButtonLink href={routes.docs} size="lg" icon={<BookOpen className="size-4" aria-hidden="true" />}>
                  Read the docs
                </ButtonLink>
              </div>
              {!github ? <p className="mt-4 text-sm text-subtle">The public repository link will appear here once the repository is published.</p> : null}
            </Reveal>
            <ul className="space-y-4">
              {PRINCIPLES.map(({ icon: Icon, title, text }, index) => (
                <Reveal key={title} delay={index * 0.08}>
                  <li className="flex gap-4 rounded-3xl bg-canvas p-5">
                    <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-lime text-ink">
                      <Icon className="size-5" aria-hidden="true" />
                    </span>
                    <div>
                      <p className="font-semibold text-ink">{title}</p>
                      <p className="mt-1 text-[15px] leading-relaxed text-muted">{text}</p>
                    </div>
                  </li>
                </Reveal>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
