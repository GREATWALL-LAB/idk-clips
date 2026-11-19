"use client";

import { Cpu, RefreshCw } from "lucide-react";
import { Button, ButtonLink } from "@/components/ui/button";
import { Spinner } from "@/components/ui/progress";
import type { LocalWorkerState } from "@/lib/hooks/use-local-worker";
import { routes } from "@/lib/routes";

/**
 * Hybrid mode: videos go straight from this browser to the user's worker on the same
 * computer. Explains what to do when no such worker is available.
 */
export function WorkerNeeded({ state }: { state: LocalWorkerState }) {
  if (state.loading) {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-line bg-canvas p-4 text-sm text-muted">
        <Spinner /> Looking for your worker on this computer…
      </div>
    );
  }
  const online = state.workers.filter((w) => w.online);
  const title =
    state.workers.length === 0
      ? "Connect your computer first"
      : online.length === 0
        ? "Your worker is offline"
        : "Your worker runs on another computer";
  const body =
    state.workers.length === 0
      ? "In online mode your videos are processed on your own computer, not on our servers. Connect it once with a one-time code; it takes about a minute."
      : online.length === 0
        ? `Start the worker on ${state.workers.map((w) => `“${w.name}”`).join(", ")} (scripts\\windows\\worker.cmd run or scripts/linux/worker.sh run), then check again.`
        : `“${online[0].name}” is online, but not on the computer you are using now. Videos are handed to the worker directly, so open this page in a browser on that computer.`;
  return (
    <div className="rounded-2xl border border-brand/20 bg-brand-50 p-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-ink">
        <Cpu className="size-4 text-brand" aria-hidden="true" /> {title}
      </p>
      <p className="mt-1 text-[13px] leading-relaxed text-ink-soft">{body}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {state.workers.length === 0 ? (
          <ButtonLink href={routes.workers} size="sm" variant="primary">
            Connect a worker
          </ButtonLink>
        ) : (
          <ButtonLink href={routes.workers} size="sm">
            Manage workers
          </ButtonLink>
        )}
        <Button size="sm" variant="ghost" onClick={state.refresh} icon={<RefreshCw className="size-3.5" aria-hidden="true" />}>
          Check again
        </Button>
      </div>
    </div>
  );
}
