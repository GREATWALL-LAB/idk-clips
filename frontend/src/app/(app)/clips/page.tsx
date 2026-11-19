"use client";

import { useCallback, useState } from "react";
import { Clapperboard } from "lucide-react";
import { ClipCard } from "@/components/clips/clip-card";
import { PageHeader } from "@/components/layout/app-shell";
import { isJobActive } from "@/components/projects/status";
import { ButtonLink } from "@/components/ui/button";
import { Alert, EmptyState } from "@/components/ui/empty-state";
import { SegmentedControl } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/progress";
import { errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { ClipList } from "@/lib/api/types";
import { usePolling } from "@/lib/hooks/use-polling";

type Filter = "all" | "ready" | "suggested" | "failed";
const clipsInterval = (list: ClipList) => (list.items.some((c) => isJobActive(c.active_job) || c.status === "rendering") ? 2_000 : 30_000);

export default function ClipsPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const fetcher = useCallback((signal: AbortSignal) => api.clips(filter === "all" ? null : filter, signal), [filter]);
  const { data, error, loading } = usePolling(fetcher, clipsInterval, filter);

  return (
    <>
      <PageHeader title="Clips" description="Every clip from all of your projects. Exported clips can be previewed and downloaded." />
      <div className="mb-6 max-w-xl">
        <SegmentedControl<Filter>
          label="Filter clips"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "All" },
            { value: "ready", label: "Exported" },
            { value: "suggested", label: "Not exported" },
            { value: "failed", label: "Failed" },
          ]}
        />
      </div>
      {error && !data ? <Alert>{errorMessage(error)}</Alert> : null}
      {loading && !data ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="aspect-[9/16] max-h-80" />
          ))}
        </div>
      ) : data && data.items.length === 0 ? (
        <EmptyState
          icon={<Clapperboard className="size-5" aria-hidden="true" />}
          title={filter === "all" ? "No clips yet" : "Nothing here"}
          description={filter === "all" ? "Process a project to get AI clip suggestions, then export them." : "No clips match this filter."}
          action={filter === "all" ? <ButtonLink href="/projects/new/" variant="primary">New project</ButtonLink> : null}
        />
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
          {data?.items.map((clip) => (
            <ClipCard key={clip.id} clip={clip} />
          ))}
        </div>
      )}
    </>
  );
}
