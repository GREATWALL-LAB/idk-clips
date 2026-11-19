import type { ReactNode } from "react";
import { SiteFooter } from "@/components/home/site-footer";
import { SiteHeader } from "@/components/home/site-header";

export function DocsShell({ children }: { children: ReactNode }) {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">{children}</main>
      <SiteFooter />
    </>
  );
}
