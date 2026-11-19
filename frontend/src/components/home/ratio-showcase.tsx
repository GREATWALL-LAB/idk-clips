"use client";

import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { Crop, Maximize } from "lucide-react";
import { EASE, Reveal } from "@/components/home/motion";
import { SceneArt, SPEAKER_FOCUS } from "@/components/home/scene-art";
import type { AspectRatio } from "@/lib/api/types";
import { RATIOS, ratioInfo } from "@/lib/aspect";
import { cn } from "@/lib/cn";

type Layout = "crop" | "fit";

/** Interactive demo of the four export shapes, using the exporter's crop rule. */
export function RatioShowcase() {
  const [ratio, setRatio] = useState<AspectRatio>("9:16");
  const [layout, setLayout] = useState<Layout>("crop");
  const reduced = useReducedMotion();
  const info = ratioInfo(ratio);
  const aspect = info.width / info.height;
  const box = 360;
  const width = aspect >= 1 ? box : box * aspect;
  const height = aspect >= 1 ? box / aspect : box;

  return (
    <section className="bg-ink py-24 text-white sm:py-32" aria-labelledby="ratios-title">
      <div className="mx-auto grid max-w-7xl items-center gap-14 px-4 sm:px-6 lg:grid-cols-2">
        <Reveal>
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-lime">Aspect ratios</p>
          <h2 id="ratios-title" className="mt-3 font-display text-4xl font-bold leading-[1.02] tracking-[-0.035em] sm:text-6xl">
            The shape you pick is the file you get.
          </h2>
          <p className="mt-6 max-w-lg text-lg leading-relaxed text-white/75">
            The ratio changes the exported MP4 itself, not just the preview. Fill the frame with a crop that follows the speaker, or keep the whole picture
            over a soft blurred background. Every pixel stays square, so no one is ever stretched.
          </p>
          <div className="mt-8 grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Choose an aspect ratio">
            {RATIOS.map((r) => (
              <button
                key={r.id}
                type="button"
                role="radio"
                aria-checked={r.id === ratio}
                onClick={() => setRatio(r.id)}
                className={cn(
                  "rounded-2xl border px-3 py-3 text-left transition-colors",
                  r.id === ratio ? "border-lime bg-lime text-ink" : "border-white/15 text-white hover:border-white/40",
                )}
              >
                <span className="block font-mono text-base font-bold">{r.id}</span>
                <span className={cn("block text-xs", r.id === ratio ? "text-ink/70" : "text-white/60")}>{r.label}</span>
              </button>
            ))}
          </div>
          <div role="radiogroup" aria-label="Framing" className="mt-4 inline-flex rounded-xl border border-white/15 p-1">
            {(
              [
                ["crop", "Fill (crop)", Crop],
                ["fit", "Fit (whole picture)", Maximize],
              ] as const
            ).map(([value, label, Icon]) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={layout === value}
                onClick={() => setLayout(value)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium transition-colors",
                  layout === value ? "bg-white text-ink" : "text-white/70 hover:text-white",
                )}
              >
                <Icon className="size-3.5" aria-hidden="true" /> {label}
              </button>
            ))}
          </div>
          <dl className="mt-8 grid max-w-md grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-white/55">Export size</dt>
              <dd className="mt-1 font-mono text-lg font-semibold">
                {info.width} × {info.height}
              </dd>
            </div>
            <div>
              <dt className="text-white/55">Made for</dt>
              <dd className="mt-1 font-semibold">{info.use}</dd>
            </div>
          </dl>
        </Reveal>

        <div className="grid h-[420px] place-items-center rounded-[32px] border border-white/10 bg-white/[0.03] sm:h-[460px]">
          <motion.div
            className="relative max-w-[86vw] overflow-hidden rounded-2xl border-4 border-white/90 bg-ink shadow-2xl"
            animate={{ width, height }}
            style={{ width, height }}
            transition={{ duration: reduced ? 0 : 0.6, ease: EASE }}
            data-testid="ratio-frame"
          >
            {layout === "crop" ? (
              <SceneArt className="absolute inset-0 size-full" crop={{ aspect, focus: SPEAKER_FOCUS }} title={`${ratio} crop around the speaker`} />
            ) : (
              <>
                <SceneArt className="absolute inset-0 size-full scale-125 opacity-70 blur-xl" crop={{ aspect, focus: 0.5 }} title="" />
                <div className="absolute inset-0 grid place-items-center">
                  <SceneArt className="block h-auto w-full" style={{ aspectRatio: "16 / 9", maxHeight: "100%" }} title={`${ratio} fit showing the whole picture`} />
                </div>
              </>
            )}
            <span className="absolute left-2 top-2 rounded-md bg-ink/80 px-2 py-0.5 font-mono text-[11px] text-lime">{ratio}</span>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
