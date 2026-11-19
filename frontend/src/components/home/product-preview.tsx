"use client";

import { useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";
import { Download, Scissors, Sparkles } from "lucide-react";
import { SceneArt, SPEAKER_FOCUS } from "@/components/home/scene-art";
import { cn } from "@/lib/cn";

/** Deterministic pseudo-waveform for illustrations (same output on server and client). */
export const WAVE = Array.from({ length: 72 }, (_, i) => Math.round(26 + 22 * Math.abs(Math.sin(i * 0.47)) + 14 * Math.abs(Math.sin(i * 1.9 + 1))));
export const MOMENTS = [
  { from: 9, to: 19, label: "Strong opening" },
  { from: 31, to: 40, label: "Story with a payoff" },
  { from: 53, to: 63, label: "Practical tip" },
];

const CAPTION = ["The", "best", "ideas", "start", "as", "tiny", "experiments"];
const TRANSCRIPT = [
  ["12:04", "So the first version was honestly terrible."],
  ["12:09", "The best ideas start as tiny experiments."],
  ["12:15", "You ship one, you learn, you ship again."],
];

/** Word-by-word caption highlight, like the exported clips (paused for reduced motion). */
export function useCaptionWord(length: number, intervalMs = 520): number {
  const reduced = useReducedMotion();
  const [index, setIndex] = useState(2);
  useEffect(() => {
    if (reduced) return;
    const timer = setInterval(() => setIndex((i) => (i + 1) % length), intervalMs);
    return () => clearInterval(timer);
  }, [reduced, length, intervalMs]);
  return index;
}

export function CaptionLine({ words, active, className }: { words: string[]; active: number; className?: string }) {
  return (
    <p className={cn("text-center font-[family-name:var(--font-caption-montserrat)] font-bold leading-tight text-white [paint-order:stroke_fill] [-webkit-text-stroke:3px_#172033]", className)}>
      {words.map((word, i) => (
        <span key={i} className={i === active ? "text-lime" : undefined}>
          {word}
          {i < words.length - 1 ? " " : ""}
        </span>
      ))}
    </p>
  );
}

/** A faithful, illustrated mock of the IDK Clips editor (not a screenshot of fake data). */
export function ProductPreview() {
  const word = useCaptionWord(CAPTION.length);
  return (
    <div className="overflow-hidden rounded-[28px] border border-line bg-surface shadow-lift">
      <div className="flex items-center gap-2 border-b border-line bg-canvas px-4 py-3">
        <span className="size-2.5 rounded-full bg-line-strong" />
        <span className="size-2.5 rounded-full bg-line-strong" />
        <span className="size-2.5 rounded-full bg-line-strong" />
        <span className="ml-3 truncate rounded-lg bg-surface px-3 py-1 font-mono text-[11px] text-subtle">IDK Clips · Episode 42: Building in public</span>
      </div>
      <div className="grid gap-4 p-4 sm:p-5 md:grid-cols-[minmax(0,1fr)_200px] lg:grid-cols-[minmax(0,1fr)_230px]">
        <div className="min-w-0 space-y-4">
          <div className="relative overflow-hidden rounded-2xl bg-ink">
            <SceneArt className="block aspect-video w-full" />
            <span className="absolute left-3 top-3 rounded-md bg-ink/80 px-2 py-0.5 font-mono text-[11px] text-white">1:12:08 source</span>
          </div>
          <div className="rounded-2xl border border-line bg-canvas p-3">
            <div className="flex h-14 items-center gap-[3px]" aria-hidden="true">
              {WAVE.map((height, i) => {
                const moment = MOMENTS.find((m) => i >= m.from && i <= m.to);
                return <span key={i} className={cn("flex-1 rounded-full", moment ? "bg-brand" : "bg-ink/15")} style={{ height: `${height}%` }} />;
              })}
            </div>
            <div className="mt-2 hidden flex-wrap gap-1.5 sm:flex">
              {MOMENTS.map((m) => (
                <span key={m.label} className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-medium text-brand-700">
                  <Sparkles className="size-3" aria-hidden="true" /> {m.label}
                </span>
              ))}
            </div>
          </div>
          <ol className="hidden space-y-1.5 sm:block">
            {TRANSCRIPT.map(([time, text], i) => (
              <li key={time} className={cn("flex gap-3 rounded-xl px-3 py-2 text-[13px]", i === 1 ? "bg-lime-100 text-ink" : "text-ink-soft")}>
                <span className="font-mono text-[11px] text-subtle">{time}</span>
                {text}
              </li>
            ))}
          </ol>
        </div>
        <div className="flex flex-col items-center gap-3">
          <div className="relative aspect-[9/16] w-[180px] overflow-hidden rounded-[22px] border-[5px] border-ink bg-ink md:w-full">
            <SceneArt
              className="absolute inset-0 size-full"
              crop={{ aspect: 9 / 16, focus: SPEAKER_FOCUS }}
              title="The same scene cropped to a vertical clip around the speaker"
            />
            <div className="absolute inset-x-3 bottom-[17%]">
              <CaptionLine words={CAPTION.slice(1, 5)} active={Math.max(0, Math.min(3, word - 1))} className="text-[17px]" />
            </div>
            <span className="absolute left-2 top-2 rounded-md bg-ink/80 px-1.5 py-0.5 font-mono text-[10px] text-white">9:16</span>
          </div>
          <div className="w-full space-y-2">
            <div className="flex items-center justify-between rounded-xl border border-line px-3 py-2 text-xs">
              <span className="inline-flex items-center gap-1.5 font-medium text-ink">
                <Scissors className="size-3.5 text-brand" aria-hidden="true" /> 12:09 – 12:41
              </span>
              <span className="text-subtle">32s</span>
            </div>
            <div className="flex items-center justify-center gap-1.5 rounded-xl bg-brand px-3 py-2 text-xs font-semibold text-white">
              <Download className="size-3.5" aria-hidden="true" /> Export MP4
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
