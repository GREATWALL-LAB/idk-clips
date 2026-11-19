import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/cn";

const control =
  "w-full rounded-xl border border-line-strong bg-surface px-3.5 text-sm text-ink placeholder:text-subtle " +
  "transition-colors hover:border-ink/25 focus:border-brand focus:outline-none focus:ring-4 focus:ring-brand/15 disabled:bg-canvas disabled:opacity-70";

export function Field({
  label,
  htmlFor,
  hint,
  error,
  children,
  className,
}: {
  label: ReactNode;
  htmlFor?: string;
  hint?: ReactNode;
  error?: string | null;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={htmlFor} className="block text-[13px] font-medium text-ink">
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-xs text-danger" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-subtle">{hint}</p>
      ) : null}
    </div>
  );
}

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(control, "h-10", className)} {...props} />;
}

export function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <select className={cn(control, "h-10 pr-9", className)} {...props}>
      {children}
    </select>
  );
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(control, "min-h-20 py-2.5", className)} {...props} />;
}

export function Switch({
  checked,
  onChange,
  label,
  description,
  id,
  disabled,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  description?: string;
  id: string;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <label htmlFor={id} className="text-[13px] font-medium text-ink">
          {label}
        </label>
        {description ? <p className="mt-0.5 text-xs text-subtle">{description}</p> : null}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative h-6 w-11 shrink-0 rounded-full border transition-colors disabled:opacity-50",
          checked ? "border-brand bg-brand" : "border-line-strong bg-mist",
        )}
      >
        <span className={cn("absolute top-0.5 size-[18px] rounded-full bg-white shadow transition-transform", checked ? "translate-x-[22px]" : "translate-x-0.5")} />
      </button>
    </div>
  );
}

export function RangeInput({ className, ...props }: ComponentProps<"input">) {
  return <input type="range" className={cn("h-2 w-full cursor-pointer accent-brand", className)} {...props} />;
}

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  label,
  className,
}: {
  value: T;
  options: Array<{ value: T; label: string; icon?: ReactNode; disabled?: boolean }>;
  onChange: (value: T) => void;
  label: string;
  className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("inline-flex w-full rounded-xl border border-line bg-canvas p-1", className)}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          disabled={option.disabled}
          onClick={() => onChange(option.value)}
          className={cn(
            "flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium transition-colors disabled:opacity-40",
            value === option.value ? "bg-surface text-ink shadow-[0_1px_3px_rgb(23_32_51/0.12)]" : "text-muted hover:text-ink",
          )}
        >
          {option.icon}
          {option.label}
        </button>
      ))}
    </div>
  );
}
