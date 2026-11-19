import { cn } from "@/lib/cn";

/** Determinate progress bar. Pass `value` between 0 and 1 (real progress only). */
export function ProgressBar({
  value,
  label,
  className,
  tone = "brand",
}: {
  value: number;
  label?: string;
  className?: string;
  tone?: "brand" | "success" | "danger";
}) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const fill = tone === "success" ? "bg-success" : tone === "danger" ? "bg-danger" : "bg-brand";
  return (
    <div
      className={cn("h-2 w-full overflow-hidden rounded-full bg-mist", className)}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      aria-label={label}
    >
      <div className={cn("h-full rounded-full transition-[width] duration-500 ease-out", fill)} style={{ width: `${pct}%` }} />
    </div>
  );
}

/** Indeterminate activity indicator (for steps whose duration is unknown, e.g. a model download). */
export function Spinner({ className, label = "Loading" }: { className?: string; label?: string }) {
  return <span role="status" aria-label={label} className={cn("inline-block size-4 animate-spin rounded-full border-2 border-brand/20 border-t-brand", className)} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse-soft rounded-2xl bg-mist", className)} aria-hidden="true" />;
}
