import type { Metadata } from "next";
import Link from "next/link";
import { NOINDEX } from "@/lib/seo";

export const metadata: Metadata = NOINDEX;
import { Logo } from "@/components/brand/logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative grid min-h-dvh place-items-center bg-canvas px-4 py-12">
      <div className="w-full max-w-sm animate-fade-up">
        <Link href="/" className="mb-8 flex justify-center" aria-label="IDK Clips home">
          <Logo />
        </Link>
        <div className="surface-card p-6 sm:p-8">{children}</div>
        <p className="mt-6 text-center text-xs text-subtle">
          Free and open source · <Link href="/privacy/" className="underline underline-offset-2 hover:text-ink">Privacy</Link> ·{" "}
          <Link href="/terms/" className="underline underline-offset-2 hover:text-ink">Terms</Link>
        </p>
      </div>
    </div>
  );
}
