import { cn } from "@/lib/cn";

/**
 * The IDK Clips mark: a cobalt tile holding a vertical clip frame with a lime cut marker.
 * Flat colours only (no gradients), so it reads well at favicon size.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn("shrink-0", className)}>
      <rect width="32" height="32" rx="9" fill="#2457F5" />
      <rect x="10" y="6" width="12" height="20" rx="3.2" fill="none" stroke="#FFFFFF" strokeWidth="2.2" />
      <path d="M14.4 12.3v7.4l5.6-3.7z" fill="#FFFFFF" />
      <rect x="6" y="14.9" width="20" height="2.2" rx="1.1" fill="#B9F56A" />
    </svg>
  );
}

export function Logo({ className, inverted = false }: { className?: string; inverted?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark className="size-8" />
      <span className={cn("font-display text-[17px] font-bold tracking-tight", inverted ? "text-white" : "text-ink")}>
        IDK<span className="text-brand"> Clips</span>
      </span>
    </span>
  );
}
