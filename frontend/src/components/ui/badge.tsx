import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "brand" | "lime";

const tones: Record<Tone, string> = {
  neutral: "border-line-strong bg-canvas text-ink-soft",
  success: "border-success/20 bg-success-50 text-success",
  warning: "border-warning/20 bg-warning-50 text-warning",
  danger: "border-danger/20 bg-danger-50 text-danger",
  info: "border-brand/20 bg-brand-50 text-brand-700",
  brand: "border-brand/20 bg-brand-50 text-brand-700",
  lime: "border-lime-700/15 bg-lime-100 text-lime-700",
};

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

const dotTones: Record<Tone, string> = {
  neutral: "bg-subtle",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-brand",
  brand: "bg-brand",
  lime: "bg-lime-700",
};

export function StatusDot({ tone, pulse = false }: { tone: Tone; pulse?: boolean }) {
  return (
    <span className="relative inline-flex size-2" aria-hidden="true">
      {pulse ? <span className={cn("absolute inset-0 animate-ping rounded-full opacity-50", dotTones[tone])} /> : null}
      <span className={cn("relative inline-flex size-2 rounded-full", dotTones[tone])} />
    </span>
  );
}
