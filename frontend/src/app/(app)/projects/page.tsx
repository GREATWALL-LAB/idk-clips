"use client";

import { useCallback, useMemo, useState } from "react";
import { FolderOpen, Plus, Search } from "lucide-react";
import { PageHeader } from "@/components/layout/app-shell";
import { ProjectCard } from "@/components/projects/project-card";
import { isProjectBusy } from "@/components/projects/status";
import { ButtonLink } from "@/components/ui/button";
import { Alert, EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/progress";
import { errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { ProjectList } from "@/lib/api/types";
import { usePolling } from "@/lib/hooks/use-polling";

const projectsInterval = (data: ProjectList) => (data.items.some((p) => isProjectBusy(p.status)) ? 2_500 : 20_000);

export default function ProjectsPage() {
  const fetcher = useCallback((signal: AbortSignal) => api.projects(signal), []);
  const { data, error, loading } = usePolling(fetcher, projectsInterval);
  const [query, setQuery] = useState("");
  const items = useMemo(
    () => (data?.items ?? []).filter((p) => p.name.toLowerCase().includes(query.trim().toLowerCase())),
    [data, query],
  );

  return (
    <>
      <PageHeader
        title="Projects"
        description="Every video you import becomes a project with its transcript and clips."
        actions={
          <ButtonLink href="/projects/new/" variant="primary" icon={<Plus className="size-4" aria-hidden="true" />}>
            New project
          </ButtonLink>
        }
      />
      {error && !data ? <Alert className="mb-6">{errorMessage(error)}</Alert> : null}
      {data && data.total > 0 ? (
        <div className="relative mb-5 max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle" aria-hidden="true" />
          <Input aria-label="Search projects" placeholder="Search projects" className="pl-9" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
      ) : null}
      {loading && !data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      ) : data && data.total === 0 ? (
        <EmptyState
          icon={<FolderOpen className="size-5" aria-hidden="true" />}
          title="No projects yet"
          description="Upload your first video to get started."
          action={
            <ButtonLink href="/projects/new/" variant="primary" icon={<Plus className="size-4" aria-hidden="true" />}>
              New project
            </ButtonLink>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
          {data && items.length === 0 ? <p className="text-sm text-subtle">No projects match “{query}”.</p> : null}
        </div>
      )}
    </>
  );
}
