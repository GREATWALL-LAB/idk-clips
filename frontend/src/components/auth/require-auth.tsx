"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { RefreshCw, ServerOff } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { LogoMark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/progress";
import { routes } from "@/lib/routes";

/** Renders children only for signed-in users (always true in local mode); otherwise sends them to log in. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (auth.status === "anonymous") {
      const here = `${window.location.pathname}${window.location.search}`;
      router.replace(`${routes.login}?next=${encodeURIComponent(here)}`);
    }
  }, [auth.status, router]);

  if (auth.status === "authenticated") return <>{children}</>;

  if (auth.status === "offline") {
    return (
      <div className="grid min-h-dvh place-items-center bg-canvas px-4">
        <div className="max-w-md text-center">
          <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-danger-50 text-danger">
            <ServerOff className="size-7" aria-hidden="true" />
          </span>
          <h1 className="mt-5 font-display text-2xl font-bold text-ink">IDK Clips is not reachable</h1>
          <p className="mt-2 text-sm text-muted">{auth.error}</p>
          <p className="mt-2 text-sm text-subtle">
            Running it yourself? Start it with <code className="rounded bg-mist px-1.5 py-0.5 font-mono text-ink">scripts\windows\start.cmd</code> or{" "}
            <code className="rounded bg-mist px-1.5 py-0.5 font-mono text-ink">scripts/linux/start.sh</code>, then try again.
          </p>
          <Button className="mt-6" icon={<RefreshCw className="size-4" aria-hidden="true" />} onClick={() => void auth.refresh()}>
            Try again
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="grid min-h-dvh place-items-center bg-canvas" aria-busy="true">
      <div className="flex flex-col items-center gap-4 text-sm text-subtle">
        <LogoMark className="size-10 animate-pulse-soft" />
        <span className="inline-flex items-center gap-2">
          <Spinner /> Loading your workspace…
        </span>
      </div>
    </div>
  );
}
