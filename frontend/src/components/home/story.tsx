"use client";

import { AnimatePresence, motion, useInView, useReducedMotion, useScroll, useSpring } from "motion/react";
import { useEffect, useRef, useState, type ComponentType } from "react";
import { Reveal } from "@/components/home/motion";
import { ClipsVisual, ExportVisual, MomentsVisual, RatiosVisual, TranscriptVisual, UploadVisual } from "@/components/home/story-visuals";
import { cn } from "@/lib/cn";

type Step = { id: string; kicker: string; title: string; body: string; note: string; Visual: ComponentType };

export const STEPS: Step[] = [
  {
    id: "upload",
    kicker: "01 · Upload",
    title: "Start with the long version.",
    body: "Drop in a talk, podcast, lecture or interview. Running locally, the file never leaves your computer. Online, it goes straight from your browser to your own connected computer.",
    note: "MP4, MOV, MKV, WebM and AVI",
    Visual: UploadVisual,
  },
  {
    id: "transcript",
    kicker: "02 · Transcribe",
    title: "Every word, on the clock.",
    body: "faster-whisper turns speech into a transcript with a timestamp for every word, on your CPU or NVIDIA GPU. You can read it, search it and jump to any line.",
    note: "English by default, plus 37 other languages",
    Visual: TranscriptVisual,
  },
  {
    id: "moments",
    kicker: "03 · Find moments",
    title: "AI finds what stands on its own.",
    body: "A local AI model reads the transcript and picks complete moments: strong openings, stories with a payoff, useful tips. It chooses transcript lines; it never invents timestamps.",
    note: "Runs on Ollama, on your machine",
    Visual: MomentsVisual,
  },
  {
    id: "clips",
    kicker: "04 · Generate clips",
    title: "Five to ten clips, ready to refine.",
    body: "Each suggestion comes with a title and the reason it was picked, cut at sentence boundaries. Drag the start and end, rename it, or add your own clips by hand.",
    note: "Your edits are kept when you ask for new suggestions",
    Visual: ClipsVisual,
  },
  {
    id: "ratios",
    kicker: "05 · Reshape",
    title: "9:16, 4:5, 1:1 or 16:9.",
    body: "Pick the shape per clip. The export really is that size: IDK Clips crops around the speaker or fits the whole picture over a soft blur, and never stretches anyone.",
    note: "1080×1920 · 1080×1350 · 1080×1080 · 1920×1080",
    Visual: RatiosVisual,
  },
  {
    id: "export",
    kicker: "06 · Caption and export",
    title: "Preview it, then press export.",
    body: "Captions come from the real transcript, with the spoken word highlighted. Choose the font, size, colours and position, fix any word, and render a clean MP4 with FFmpeg.",
    note: "H.264 + AAC, hardware encoding when available",
    Visual: ExportVisual,
  },
];

function StepText({ step, index, onActive }: { step: Step; index: number; onActive: (index: number) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { margin: "-45% 0px -45% 0px" });
  useEffect(() => {
    if (inView) onActive(index);
  }, [inView, index, onActive]);
  const Visual = step.Visual;
  return (
    <div ref={ref} className="py-10 lg:flex lg:min-h-[78vh] lg:items-center lg:py-0" data-step={step.id}>
      <div className="max-w-xl">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-brand">{step.kicker}</p>
        <h3 className="mt-3 font-display text-[34px] font-bold leading-[1.02] tracking-[-0.03em] text-ink sm:text-5xl">{step.title}</h3>
        <p className="mt-5 text-lg leading-relaxed text-ink-soft">{step.body}</p>
        <p className="mt-5 inline-flex rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-muted">{step.note}</p>
      </div>
      {/* Small screens: the visual sits right under its text instead of in a sticky stage. */}
      <Reveal className="mt-8 lg:hidden">
        <Visual />
      </Reveal>
    </div>
  );
}

export function Story() {
  const [active, setActive] = useState(0);
  const container = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: container, offset: ["start center", "end center"] });
  const progress = useSpring(scrollYProgress, { stiffness: 120, damping: 28, mass: 0.4 });
  const Visual = STEPS[active].Visual;

  return (
    <div ref={container} className="relative grid gap-x-16 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <div>
        {STEPS.map((step, index) => (
          <StepText key={step.id} step={step} index={index} onActive={setActive} />
        ))}
      </div>
      <div className="hidden lg:block">
        <div className="sticky top-24 flex h-[calc(100vh-8rem)] flex-col justify-center">
          <div className="mb-5 flex items-center gap-4" aria-hidden="true">
            <div className="relative h-1 flex-1 overflow-hidden rounded-full bg-line-strong">
              <motion.div className="absolute inset-y-0 left-0 w-full origin-left rounded-full bg-brand" style={{ scaleX: reduced ? (active + 1) / STEPS.length : progress }} />
            </div>
            <span className="font-mono text-xs font-semibold text-ink">
              {String(active + 1).padStart(2, "0")} / {String(STEPS.length).padStart(2, "0")}
            </span>
          </div>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={STEPS[active].id}
              initial={reduced ? false : { opacity: 0, y: 28, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={reduced ? { opacity: 0 } : { opacity: 0, y: -20, scale: 0.98 }}
              transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            >
              <Visual />
            </motion.div>
          </AnimatePresence>
          <ol className="mt-6 flex flex-wrap gap-2" aria-label="Steps">
            {STEPS.map((step, index) => (
              <li key={step.id}>
                <span
                  className={cn(
                    "inline-flex rounded-full px-3 py-1 text-xs font-medium transition-colors",
                    index === active ? "bg-ink text-white" : index < active ? "bg-brand-50 text-brand-700" : "bg-mist text-subtle",
                  )}
                >
                  {step.kicker.split(" · ")[1]}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}
