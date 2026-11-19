"use client";

import type { AspectRatio } from "@/lib/api/types";
import { RATIOS } from "@/lib/aspect";
import { cn } from "@/lib/cn";

/** Four export shapes, each drawn to scale. Used for project defaults and per clip. */
export function RatioPicker({
  value,
  onChange,
  label = "Aspect ratio",
  disabled = false,
  compact = false,
}: {
  value: AspectRatio;
  onChange: (value: AspectRatio) => void;
  label?: string;
  disabled?: boolean;
  compact?: boolean;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("grid grid-cols-2 gap-2 sm:grid-cols-4", disabled && "pointer-events-none opacity-50")}>
      {RATIOS.map((ratio) => {
        const active = ratio.id === value;
        const scale = 34 / Math.max(ratio.width, ratio.height);
        return (
          <button
            key={ratio.id}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={`${ratio.id} ${ratio.label}: ${ratio.use}`}
            disabled={disabled}
            onClick={() => onChange(ratio.id)}
            className={cn(
              "flex items-center gap-3 rounded-2xl border p-3 text-left transition-colors",
              active ? "border-brand bg-brand-50 ring-2 ring-brand/15" : "border-line-strong bg-surface hover:border-ink/25",
            )}
          >
            <span className="grid size-10 shrink-0 place-items-center" aria-hidden="true">
              <span
                className={cn("block rounded-[4px] border-2", active ? "border-brand bg-brand/10" : "border-ink/40")}
                style={{ width: ratio.width * scale, height: ratio.height * scale }}
              />
            </span>
            <span className="min-w-0">
              <span className="block font-mono text-sm font-semibold text-ink">{ratio.id}</span>
              {!compact ? <span className="block truncate text-xs text-subtle">{ratio.use}</span> : <span className="block text-xs text-subtle">{ratio.label}</span>}
            </span>
          </button>
        );
      })}
    </div>
  );
}
