import type { Metadata } from "next";
import { Faq } from "@/components/home/faq";
import { JsonLd } from "@/components/seo/json-ld";
import { BRAND } from "@/lib/config";
import { FAQ } from "@/lib/faq";
import { faqLd, pageMetadata, softwareApplicationLd, webSiteLd } from "@/lib/seo";
import { MotionProvider } from "@/components/home/motion-provider";
import { Features } from "@/components/home/features";
import { Hero } from "@/components/home/hero";
import { Reveal } from "@/components/home/motion";
import { OpenSource } from "@/components/home/open-source";
import { RatioShowcase } from "@/components/home/ratio-showcase";
import { SiteFooter } from "@/components/home/site-footer";
import { SiteHeader } from "@/components/home/site-header";
import { Story } from "@/components/home/story";
import { TwoWays } from "@/components/home/two-ways";

export const metadata: Metadata = pageMetadata({
  title: BRAND.homeTitle,
  description: BRAND.homeDescription,
  path: "/",
  absoluteTitle: true,
});

export default function HomePage() {
  return (
    <MotionProvider>
      <JsonLd data={softwareApplicationLd()} />
      <JsonLd data={webSiteLd()} />
      <JsonLd data={faqLd(FAQ)} />
      <a href="#content" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-4 focus:py-2 focus:shadow-lift">
        Skip to content
      </a>
      <SiteHeader />
      <main id="content">
        <Hero />
        <section id="how-it-works" className="scroll-mt-16 border-t border-line bg-surface py-20 sm:py-28" aria-labelledby="story-title">
          <div className="mx-auto max-w-7xl px-4 sm:px-6">
            <Reveal className="max-w-3xl">
              <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-brand">How it works</p>
              <h2 id="story-title" className="mt-3 font-display text-4xl font-bold leading-[1.02] tracking-[-0.035em] text-ink sm:text-6xl">
                From one long video to a stack of clips.
              </h2>
            </Reveal>
            <Story />
          </div>
        </section>
        <Features />
        <RatioShowcase />
        <TwoWays />
        <OpenSource />
        <Faq />
      </main>
      <SiteFooter />
    </MotionProvider>
  );
}
