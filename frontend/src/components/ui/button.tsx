import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import { LoaderCircle } from "lucide-react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "lime" | "dark";
type Size = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 rounded-xl font-semibold whitespace-nowrap " +
  "transition-[background-color,border-color,color,box-shadow,transform] duration-200 " +
  "active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 select-none";

export const buttonVariants: Record<Variant, string> = {
  primary: "bg-brand text-white shadow-brand hover:bg-brand-600",
  secondary: "border border-line-strong bg-surface text-ink shadow-[0_1px_2px_rgb(23_32_51/0.05)] hover:border-ink/25 hover:bg-canvas",
  ghost: "text-ink-soft hover:bg-mist hover:text-ink",
  danger: "border border-danger/25 bg-danger-50 text-danger hover:bg-danger hover:text-white",
  lime: "bg-lime text-ink hover:brightness-95",
  dark: "bg-ink text-white hover:bg-ink-soft",
};

export const buttonSizes: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-[15px]",
};

type CommonProps = { variant?: Variant; size?: Size; icon?: ReactNode; className?: string };

export function buttonClass(variant: Variant = "secondary", size: Size = "md", className?: string): string {
  return cn(base, buttonVariants[variant], buttonSizes[size], className);
}

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  loading = false,
  className,
  children,
  disabled,
  type = "button",
  ...props
}: CommonProps & ComponentProps<"button"> & { loading?: boolean }) {
  return (
    <button
      type={type}
      className={buttonClass(variant, size, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : icon}
      {children}
    </button>
  );
}

export function ButtonLink({
  variant = "secondary",
  size = "md",
  icon,
  className,
  children,
  ...props
}: CommonProps & ComponentProps<typeof Link>) {
  return (
    <Link className={buttonClass(variant, size, className)} {...props}>
      {icon}
      {children}
    </Link>
  );
}

/** A plain anchor styled as a button (downloads and external links). */
export function ButtonAnchor({
  variant = "secondary",
  size = "md",
  icon,
  className,
  children,
  ...props
}: CommonProps & ComponentProps<"a">) {
  return (
    <a className={buttonClass(variant, size, className)} {...props}>
      {icon}
      {children}
    </a>
  );
}
