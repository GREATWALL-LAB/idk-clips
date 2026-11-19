import type { Metadata } from "next";
import { RequireAuth } from "@/components/auth/require-auth";
import { NOINDEX } from "@/lib/seo";

// The signed-in app is private: never in search results.
export const metadata: Metadata = NOINDEX;
import { AppShell } from "@/components/layout/app-shell";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <AppShell>{children}</AppShell>
    </RequireAuth>
  );
}
