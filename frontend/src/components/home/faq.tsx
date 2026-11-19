import { ChevronDown } from "lucide-react";
import { FAQ } from "@/lib/faq";

/** Answers are plain HTML inside <details>, so they are readable without JavaScript and by crawlers. */
export function Faq() {
  return (
    <section id="faq" className="scroll-mt-16 border-t border-line bg-surface py-20 sm:py-28" aria-labelledby="faq-title">
      <div className="mx-auto max-w-3xl px-4 sm:px-6">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-brand">FAQ</p>
        <h2 id="faq-title" className="mt-3 font-display text-4xl font-bold leading-[1.05] tracking-[-0.035em] text-ink sm:text-5xl">
          Questions, answered.
        </h2>
        <div className="mt-10 divide-y divide-line rounded-3xl border border-line bg-canvas">
          {FAQ.map((item) => (
            <details key={item.question} className="group px-5 py-4 sm:px-6">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 rounded-lg py-1 text-left [&::-webkit-details-marker]:hidden">
                <h3 className="text-base font-semibold text-ink sm:text-lg">{item.question}</h3>
                <ChevronDown className="size-5 shrink-0 text-subtle transition-transform group-open:rotate-180" aria-hidden="true" />
              </summary>
              <p className="mt-3 text-[15px] leading-relaxed text-ink-soft">{item.answer}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
