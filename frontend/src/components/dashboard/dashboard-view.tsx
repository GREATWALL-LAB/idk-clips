"use client";

import Link from "next/link";
import { useCallback } from "react";
import { BrainCircuit, Clapperboard, FolderOpen, HardDrive, Loader, Plus, Upload, WandSparkles } from "lucide-react";
import { ClipCard, ClipGridLink } from "@/components/clips/clip-card";
import { PageHeader } from "@/components/layout/app-shell";
import { JobProgress } from "@/components/projects/job-progress";
import { ProjectCard } from "@/components/projects/project-card";
import { SystemStatusPanel } from "@/components/status/system-status-panel";
import { ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Alert, EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/progress";
import { errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { Dashboard } from "@/lib/api/types";
import { formatBytes } from "@/lib/format";
import { usePolling } from "@/lib/hooks/use-polling";
import { AISummaryCard } from "@/components/settings/ai-summary-card";
import { useMode } from "@/components/auth/auth-provider";
import { WorkerSummaryCard } from "@/components/workers/worker-summary-card";
import { routes } from "@/lib/routes";

function Stat({ icon, label, value, hint }: { icon: React.ReactNode; label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="surface-card p-4 sm:p-5">
      <div className="flex items-center gap-2 text-xs font-medium text-muted">
        <span className="text-brand">{icon}</span>
        {label}
      </div>
      <p className="mt-2 font-display text-3xl font-bold tracking-tight text-ink">{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-subtle">{hint}</p> : null}
    </div>
  );
}

const dashboardInterval = (data: Dashboard) => (data.active_jobs.length ? 2_000 : 15_000);

export function DashboardView() {
  const fetcher = useCallback((signal: AbortSignal) => api.dashboard(signal), []);
  const first = usePolling(fetcher, dashboardInterval);
  const data = first.data;
  const refresh = first.refresh;
  const { hybrid } = useMode();

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Import a long video, let AI find the strongest moments, and export clips in the shape you need."
        actions={
          <ButtonLink href={routes.newProject} variant="primary" icon={<Plus className="size-4" aria-hidden="true" />}>
            New project
          </ButtonLink>
        }
      />

      {first.error && !data ? <Alert className="mb-6">{errorMessage(first.error)}</Alert> : null}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {data ? (
          <>
            <Stat icon={<FolderOpen className="size-3.5" aria-hidden="true" />} label="Projects" value={data.stats.projects} />
            <Stat icon={<Loader className="size-3.5" aria-hidden="true" />} label="Processing" value={data.stats.processing} />
            <Stat icon={<Clapperboard className="size-3.5" aria-hidden="true" />} label="Clips exported" value={data.stats.clips_ready} />
            <Stat
              icon={<HardDrive className="size-3.5" aria-hidden="true" />}
              label="Storage used"
              value={formatBytes(data.stats.storage_used_bytes)}
              hint={data.stats.storage_quota_bytes ? `of ${formatBytes(data.stats.storage_quota_bytes)}` : undefined}
            />
          </>
        ) : (
          Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[98px]" />)
        )}
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_360px]">
        <div className="min-w-0 space-y-6">
          {data && data.active_jobs.length > 0 ? (
            <Card>
              <CardHeader icon={<Loader className="size-4" />} title="Processing queue" description={hybrid ? "Live progress reported by your worker." : "Live progress from the background worker."} />
              <CardBody className="space-y-5">
                {data.active_jobs.map((job) => (
                  <div key={job.id} className="space-y-2">
                    {job.project_id ? (
                      <Link href={routes.project(job.project_id)} className="text-sm font-medium text-ink hover:text-brand-700">
                        {job.project_name ?? "Project"}
                      </Link>
                    ) : null}
                    <JobProgress job={job} onChange={refresh} />
                  </div>
                ))}
              </CardBody>
            </Card>
          ) : null}

          {data && data.stats.projects === 0 ? (
            <EmptyState
              icon={<WandSparkles className="size-5" aria-hidden="true" />}
              title="Create your first project"
              description="Upload a talk, podcast, lecture or interview. IDK Clips transcribes it, suggests 5–10 clips and exports them as MP4s in 9:16, 4:5, 1:1 or 16:9."
              action={
                <ButtonLink href={routes.newProject} variant="primary" icon={<Upload className="size-4" aria-hidden="true" />}>
                  Upload a video
                </ButtonLink>
              }
            />
          ) : null}

          {data && data.recent_projects.length > 0 ? (
            <section aria-labelledby="recent-projects">
              <div className="mb-3 flex items-center justify-between">
                <h2 id="recent-projects" className="text-[15px] font-semibold text-ink">
                  Recent projects
                </h2>
                <ClipGridLink href={routes.projects}>View all</ClipGridLink>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-3">
                {data.recent_projects.map((project) => (
                  <ProjectCard key={project.id} project={project} />
                ))}
              </div>
            </section>
          ) : null}

          {data && data.recent_clips.length > 0 ? (
            <section aria-labelledby="recent-clips">
              <div className="mb-3 flex items-center justify-between">
                <h2 id="recent-clips" className="text-[15px] font-semibold text-ink">
                  Latest exports
                </h2>
                <ClipGridLink href={routes.clips}>All clips</ClipGridLink>
              </div>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 2xl:grid-cols-4">
                {data.recent_clips.map((clip) => (
                  <ClipCard key={clip.id} clip={clip} />
                ))}
              </div>
            </section>
          ) : null}
        </div>

        <div className="space-y-6">
          {hybrid ? (
            <WorkerSummaryCard />
          ) : (
            <>
              <AISummaryCard />
              <SystemStatusPanel />
            </>
          )}
          <Card>
            <CardHeader icon={<BrainCircuit className="size-4" />} title="How it works" />
            <CardBody>
              <ol className="space-y-2.5 text-sm text-muted">
                <li><span className="font-medium text-ink">1. Import</span> a video you have the rights to use.</li>
                <li><span className="font-medium text-ink">2. Transcribe</span> speech with faster-whisper{hybrid ? " on your worker" : ""}.</li>
                <li><span className="font-medium text-ink">3. Detect</span> the best moments with your AI model.</li>
                <li><span className="font-medium text-ink">4. Edit & export</span> captioned MP4 clips in four shapes.</li>
              </ol>
            </CardBody>
          </Card>
        </div>
      </div>
    </>
  );
}
