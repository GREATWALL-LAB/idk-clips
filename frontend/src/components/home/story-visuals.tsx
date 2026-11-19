"use client";

import { motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";
import { Check, CloudUpload, Download, FileVideo, Sparkles } from "lucide-react";
import { CaptionLine, MOMENTS, WAVE, useCaptionWord } from "@/components/home/product-preview";
import { SceneArt, SPEAKER_FOCUS } from "@/components/home/scene-art";
import { EASE } from "@/components/home/motion";
import { RATIOS } from "@/lib/aspect";
import { cn } from "@/lib/cn";

/** Plays a short timeline once (0..1), or jumps to the end for reduced motion. */
function useProgress(durationMs: number, delayMs = 300): number {
  const reduced = useReducedMotion();
  const [value, setValue] = useState(reduced ? 1 : 0);
  useEffect(() => {
    if (reduced) return;
    let frame = 0;
    const started = performance.now() + delayMs;
    const tick = (now: number) => {
      const t = Math.min(Math.max((now - started) / durationMs, 0), 1);
      setValue(t);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [reduced, durationMs, delayMs]);
  return value;
}

function Frame({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("relative w-full rounded-[28px] border border-line bg-surface p-5 shadow-lift sm:p-6", className)}>{children}</div>;
}

export function UploadVisual() {
  const progress = useProgress(2600);
  const reduced = useReducedMotion();
  return (
    <Frame>
      <div className="grid place-items-center rounded-2xl border-2 border-dashed border-brand/35 bg-brand-50/60 px-4 py-10 text-center">
        <span className="grid size-14 place-items-center rounded-2xl bg-surface text-brand shadow-card">
          <CloudUpload className="size-7" aria-hidden="true" />
        </span>
        <p className="mt-3 text-sm font-semibold text-ink">Drop a long video</p>
        <p className="text-xs text-subtle">MP4, MOV, MKV, WebM · talks, podcasts, lectures</p>
      </div>
      <motion.div
        className="mt-4 flex items-center gap-3 rounded-2xl border border-line bg-surface p-3"
        initial={reduced ? false : { opacity: 0, y: -28 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: EASE }}
      >
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-ink text-lime">
          <FileVideo className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-ink">episode-42-building-in-public.mp4</p>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-mist">
            <div className="h-full rounded-full bg-brand" style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
          <p className="mt-1 text-[11px] text-subtle">{progress < 1 ? "Sending to your computer…" : "Received · 1:12:08 · ready to process"}</p>
        </div>
      </motion.div>
    </Frame>
  );
}

const LINES = [
  ["00:12:02", "Welcome back. Today is about building in public."],
  ["00:12:04", "So the first version was honestly terrible."],
  ["00:12:09", "The best ideas start as tiny experiments."],
  ["00:12:15", "You ship one, you learn, and you ship again."],
  ["00:12:22", "That loop is the whole secret, really."],
];

export function TranscriptVisual() {
  const reduced = useReducedMotion();
  return (
    <Frame>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm font-semibold text-ink">Transcript</p>
        <span className="rounded-full bg-lime-100 px-2.5 py-0.5 text-[11px] font-medium text-lime-700">word-level timestamps</span>
      </div>
      <ol className="space-y-2">
        {LINES.map(([time, text], i) => (
          <motion.li
            key={time}
            className={cn("flex gap-3 rounded-xl px-3 py-2.5 text-sm", i === 2 ? "bg-brand-50 text-ink" : "text-ink-soft")}
            initial={reduced ? false : { opacity: 0, x: -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.45, ease: EASE, delay: 0.12 * i }}
          >
            <span className="w-16 shrink-0 font-mono text-[11px] leading-5 text-subtle">{time}</span>
            <span>{text}</span>
          </motion.li>
        ))}
      </ol>
    </Frame>
  );
}

export function MomentsVisual() {
  const reduced = useReducedMotion();
  return (
    <Frame>
      <p className="text-sm font-semibold text-ink">Moments that stand on their own</p>
      <p className="text-xs text-subtle">A local AI model reads the transcript and picks complete ideas.</p>
      <div className="relative mt-5 flex h-28 items-center gap-[3px]" aria-hidden="true">
        {WAVE.map((height, i) => {
          const moment = MOMENTS.findIndex((m) => i >= m.from && i <= m.to);
          return (
            <motion.span
              key={i}
              className={cn("flex-1 rounded-full", moment >= 0 ? "bg-brand" : "bg-ink/15")}
              style={{ height: `${height}%` }}
              initial={reduced || moment < 0 ? false : { opacity: 0.25 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.4, delay: 0.25 + moment * 0.35 }}
            />
          );
        })}
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        {MOMENTS.map((m, i) => (
          <motion.div
            key={m.label}
            className="rounded-xl border border-line bg-canvas p-2.5"
            initial={reduced ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: EASE, delay: 0.4 + i * 0.35 }}
          >
            <p className="flex items-center gap-1 text-xs font-semibold text-brand-700">
              <Sparkles className="size-3.5" aria-hidden="true" /> {m.label}
            </p>
            <p className="mt-0.5 font-mono text-[11px] text-subtle">{["03:41", "21:18", "48:02"][i]} · {["34s", "52s", "41s"][i]}</p>
          </motion.div>
        ))}
      </div>
    </Frame>
  );
}

const CLIPS = [
  { title: "Why version one was terrible", focus: 0.12, time: "34s" },
  { title: "Tiny experiments win", focus: SPEAKER_FOCUS, time: "52s" },
  { title: "The ship–learn loop", focus: 0.5, time: "41s" },
];

export function ClipsVisual() {
  const reduced = useReducedMotion();
  return (
    <Frame className="overflow-hidden">
      <p className="text-sm font-semibold text-ink">Clips, cut at sentence boundaries</p>
      <p className="text-xs text-subtle">Times come from the transcript, so no word is cut in half.</p>
      <div className="relative mt-6 flex h-[290px] items-end justify-center">
        {CLIPS.map((clip, i) => {
          const offset = i - 1;
          return (
            <motion.div
              key={clip.title}
              className="absolute bottom-0 w-[132px] overflow-hidden rounded-2xl border-4 border-ink bg-ink shadow-lift sm:w-[148px]"
              style={{ zIndex: i === 1 ? 3 : 1 }}
              initial={reduced ? false : { x: 0, rotate: 0, y: 30, opacity: 0 }}
              animate={{ x: offset * 118, rotate: offset * 7, y: i === 1 ? -18 : 0, opacity: 1 }}
              transition={{ duration: 0.8, ease: EASE, delay: 0.15 + i * 0.08 }}
            >
              <div className="relative aspect-[9/16]">
                <SceneArt className="absolute inset-0 size-full" crop={{ aspect: 9 / 16, focus: clip.focus }} title={clip.title} />
              </div>
              <div className="bg-surface px-2.5 py-2">
                <p className="line-clamp-1 text-[11px] font-semibold text-ink">{clip.title}</p>
                <p className="font-mono text-[10px] text-subtle">{clip.time}</p>
              </div>
            </motion.div>
          );
        })}
      </div>
    </Frame>
  );
}

export function RatiosVisual() {
  const reduced = useReducedMotion();
  const [index, setIndex] = useState(0);
  useEffect(() => {
    if (reduced) return;
    const timer = setInterval(() => setIndex((i) => (i + 1) % RATIOS.length), 1500);
    return () => clearInterval(timer);
  }, [reduced]);
  const ratio = RATIOS[index];
  const aspect = ratio.width / ratio.height;
  const box = 280;
  const width = aspect >= 1 ? box : box * aspect;
  const height = aspect >= 1 ? box / aspect : box;
  return (
    <Frame>
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-ink">One clip, every shape</p>
        <span className="rounded-full bg-ink px-2.5 py-0.5 font-mono text-[11px] text-lime">
          {ratio.id} · {ratio.width}×{ratio.height}
        </span>
      </div>
      <div className="mt-5 grid h-[300px] place-items-center">
        <motion.div
          className="relative overflow-hidden rounded-2xl border-4 border-ink bg-ink"
          animate={{ width, height }}
          transition={{ duration: reduced ? 0 : 0.7, ease: EASE }}
          style={{ width, height }}
        >
          <SceneArt className="absolute inset-0 size-full" crop={{ aspect, focus: SPEAKER_FOCUS }} title={`The clip in ${ratio.id}`} />
        </motion.div>
      </div>
      <div className="mt-2 flex justify-center gap-1.5" aria-hidden="true">
        {RATIOS.map((r, i) => (
          <span key={r.id} className={cn("h-1.5 rounded-full transition-all", i === index ? "w-6 bg-brand" : "w-1.5 bg-line-strong")} />
        ))}
      </div>
    </Frame>
  );
}

const EXPORT_WORDS = ["Tiny", "experiments", "beat", "big", "plans"];

export function ExportVisual() {
  const word = useCaptionWord(EXPORT_WORDS.length, 480);
  const progress = useProgress(2400, 900);
  return (
    <Frame>
      <div className="grid items-center gap-5 sm:grid-cols-[160px_1fr]">
        <div className="relative mx-auto aspect-[9/16] w-[150px] overflow-hidden rounded-[22px] border-[5px] border-ink bg-ink sm:w-full">
          <SceneArt className="absolute inset-0 size-full" crop={{ aspect: 9 / 16, focus: SPEAKER_FOCUS }} title="Caption preview" />
          <div className="absolute inset-x-2 bottom-[17%]">
            <CaptionLine words={EXPORT_WORDS} active={word} className="text-[15px]" />
          </div>
        </div>
        <div className="space-y-3">
          <p className="text-sm font-semibold text-ink">Captions from the real transcript</p>
          <div className="flex flex-wrap gap-1.5 text-[11px]">
            {["Montserrat Bold", "Highlight spoken word", "Bottom", "Outline 6px"].map((chip) => (
              <span key={chip} className="rounded-full border border-line px-2 py-0.5 text-ink-soft">
                {chip}
              </span>
            ))}
          </div>
          <div className="rounded-2xl border border-line bg-canvas p-3">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-ink">{progress < 1 ? "Rendering with FFmpeg" : "MP4 ready"}</span>
              <span className="font-mono text-subtle">{Math.round(progress * 100)}%</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-mist">
              <div className={cn("h-full rounded-full", progress < 1 ? "bg-brand" : "bg-success")} style={{ width: `${Math.round(progress * 100)}%` }} />
            </div>
            <div className={cn("mt-3 flex items-center gap-2 text-xs transition-opacity", progress < 1 ? "opacity-40" : "opacity-100")}>
              <span className="grid size-6 place-items-center rounded-full bg-success-50 text-success">
                <Check className="size-3.5" aria-hidden="true" />
              </span>
              <span className="text-ink-soft">1080×1920 · H.264 + AAC</span>
              <span className="ml-auto inline-flex items-center gap-1 font-semibold text-brand">
                <Download className="size-3.5" aria-hidden="true" /> Download
              </span>
            </div>
          </div>
        </div>
      </div>
    </Frame>
  );
}
