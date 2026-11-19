"use client";

import { motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import { useRef } from "react";
import { ArrowRight, GitFork } from "lucide-react";
import { Marker, Reveal, StaggerLines } from "@/components/home/motion";
import { ProductPreview } from "@/components/home/product-preview";
import { ButtonLink } from "@/components/ui/button";
import { routes } from "@/lib/routes";

export function Hero() {
  const previewRef = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  // The preview starts slightly tilted back and settles flat as it scrolls into place.
  const { scrollYProgress } = useScroll({ target: previewRef, offset: ["start end", "center center"] });
  const rotateX = useTransform(scrollYProgress, [0, 1], [14, 0]);
  const scale = useTransform(scrollYProgress, [0, 1], [0.94, 1]);
  const y = useTransform(scrollYProgress, [0, 1], [40, 0]);

  return (
    <section className="relative overflow-hidden pb-16 pt-12 sm:pt-20" aria-labelledby="hero-title">
      {/* Quiet geometric accents (no gradients, no floating clutter). */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[560px] bg-[linear-gradient(to_right,rgb(23_32_51/0.045)_1px,transparent_1px),linear-gradient(to_bottom,rgb(23_32_51/0.045)_1px,transparent_1px)] bg-[size:56px_56px] [mask-image:linear-gradient(to_bottom,black_30%,transparent)]" />
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="mx-auto max-w-4xl text-center">
          <Reveal y={10}>
            <p className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3.5 py-1.5 text-xs font-semibold text-ink-soft shadow-card">
              <span className="size-2 rounded-full bg-lime ring-2 ring-lime-700/20" aria-hidden="true" />
              Free and open source · MIT licensed · no subscriptions
            </p>
          </Reveal>
          <h1 id="hero-title" className="mt-7 font-display text-[44px] font-extrabold leading-[0.95] tracking-[-0.045em] text-ink sm:text-7xl lg:text-[88px]">
            <StaggerLines
              lines={[
                "Long videos in.",
                <>
                  <Marker>Short clips</Marker> out.
                </>,
              ]}
            />
          </h1>
          <Reveal delay={0.25}>
            <p className="mx-auto mt-7 max-w-2xl text-pretty text-lg leading-relaxed text-ink-soft sm:text-xl">
              IDK Clips transcribes your video, finds the moments that stand on their own, and exports captioned clips in 9:16, 4:5, 1:1 or 16:9.
              Run it on your own computer, or use it online while your computer does the work.
            </p>
          </Reveal>
          <Reveal delay={0.35}>
            <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <ButtonLink href={routes.dashboard} variant="primary" size="lg" icon={<ArrowRight className="size-4" aria-hidden="true" />} className="w-full sm:w-auto">
                Start creating
              </ButtonLink>
              <ButtonLink href="/#open-source" size="lg" icon={<GitFork className="size-4" aria-hidden="true" />} className="w-full sm:w-auto">
                Explore open source
              </ButtonLink>
            </div>
          </Reveal>
        </div>

        <div ref={previewRef} className="mx-auto mt-14 max-w-5xl [perspective:1600px] sm:mt-20">
          <motion.div style={reduced ? undefined : { rotateX, scale, y, transformOrigin: "50% 100%" }}>
            <ProductPreview />
          </motion.div>
          <p className="mt-4 text-center text-xs text-subtle">Illustration of the IDK Clips editor: one long video, suggested moments, and a captioned 9:16 clip.</p>
        </div>
      </div>
    </section>
  );
}
