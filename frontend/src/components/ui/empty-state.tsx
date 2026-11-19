import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center rounded-3xl border border-dashed border-line-strong bg-surface px-6 py-12 text-center", className)}>
      {icon ? <span className="grid size-12 place-items-center rounded-2xl bg-brand-50 text-brand">{icon}</span> : null}
      <h3 className="mt-4 text-base font-semibold text-ink">{title}</h3>
      {description ? <p className="mt-1.5 max-w-md text-sm text-muted">{description}</p> : null}
      {action ? <div className="mt-6">{action}</div> : null}
    </div>
  );
}

export function Alert({
  tone = "danger",
  title,
  children,
  className,
}: {
  tone?: "danger" | "warning" | "info" | "success";
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  const tones = {
    danger: "border-danger/20 bg-danger-50 text-danger",
    warning: "border-warning/20 bg-warning-50 text-warning",
    info: "border-brand/15 bg-brand-50 text-brand-700",
    success: "border-success/20 bg-success-50 text-success",
  };
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("rounded-2xl border px-4 py-3 text-sm", tones[tone], className)}>
      {title ? <p className="font-semibold">{title}</p> : null}
      <div className={cn(title && "mt-1", "text-[13px] leading-relaxed")}>{children}</div>
    </div>
  );
}
