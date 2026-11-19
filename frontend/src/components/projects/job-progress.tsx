"use client";

import { useState } from "react";
import { CircleStop } from "lucide-react";
import { JOB_LABELS } from "@/components/projects/status";
import { Button } from "@/components/ui/button";
import { ProgressBar, Spinner } from "@/components/ui/progress";
import { useToast } from "@/components/ui/toast";
import { errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { Job } from "@/lib/api/types";
import { percent } from "@/lib/format";

/** Live job progress (values come from the backend's real progress reports). */
export function JobProgress({ job, onChange, compact = false }: { job: Job; onChange?: () => void; compact?: boolean }) {
  const toast = useToast();
  const [cancelling, setCancelling] = useState(false);
  const queued = job.status === "queued";

  async function cancel() {
    setCancelling(true);
    try {
      await api.cancelJob(job.id);
      toast.info("Cancelling…");
      onChange?.();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setCancelling(false);
    }
  }

  return (
    <div className="space-y-2.5" aria-live="polite">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <Spinner className="shrink-0" label={JOB_LABELS[job.type]} />
          <span className="truncate font-medium text-ink">{JOB_LABELS[job.type]}</span>
          <span className="truncate text-subtle">· {queued ? "Waiting for the worker" : job.stage || "Working"}</span>
        </div>
        <span className="shrink-0 font-mono text-xs text-muted">{queued ? "queued" : percent(job.progress)}</span>
      </div>
      <ProgressBar value={job.progress} label={`${JOB_LABELS[job.type]} progress`} />
      {!compact ? (
        <div className="flex justify-end">
          <Button size="sm" variant="ghost" onClick={cancel} loading={cancelling} disabled={job.cancel_requested} icon={<CircleStop className="size-3.5" aria-hidden="true" />}>
            {job.cancel_requested ? "Cancelling…" : "Cancel"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
