"use client";

import { motion, useReducedMotion, type Variants } from "motion/react";
import type { ReactNode } from "react";

const EASE = [0.22, 1, 0.36, 1] as const;

/** Fades and lifts its children into view once. Static for people who prefer reduced motion. */
export function Reveal({ children, delay = 0, className, y = 24 }: { children: ReactNode; delay?: number; className?: string; y?: number }) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduced ? false : { opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -12% 0px" }}
      transition={{ duration: 0.7, ease: EASE, delay }}
    >
      {children}
    </motion.div>
  );
}

const lineVariants: Variants = {
  hidden: { opacity: 0, y: "0.45em" },
  shown: (index: number) => ({ opacity: 1, y: 0, transition: { duration: 0.75, ease: EASE, delay: 0.08 * index } }),
};

/** Staggered headline: each line rises in after the previous one. */
export function StaggerLines({ lines, className, lineClassName }: { lines: ReactNode[]; className?: string; lineClassName?: string }) {
  const reduced = useReducedMotion();
  return (
    <motion.span className={className} initial={reduced ? false : "hidden"} animate="shown">
      {lines.map((line, index) => (
        <span key={index} className="block overflow-hidden pb-[0.08em]">
          <motion.span className={`block ${lineClassName ?? ""}`} custom={index} variants={lineVariants}>
            {line}
          </motion.span>
        </span>
      ))}
    </motion.span>
  );
}

/** A lime "marker" stroke behind a word, drawn once when it scrolls into view. */
export function Marker({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  return (
    <span className="relative inline-block whitespace-nowrap">
      <motion.span
        aria-hidden="true"
        className="absolute inset-x-[-0.08em] bottom-[0.08em] top-[0.52em] -z-10 origin-left rounded-[0.18em] bg-lime"
        initial={reduced ? false : { scaleX: 0 }}
        whileInView={{ scaleX: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.8, ease: EASE, delay: 0.35 }}
      />
      {children}
    </span>
  );
}

export { EASE };
