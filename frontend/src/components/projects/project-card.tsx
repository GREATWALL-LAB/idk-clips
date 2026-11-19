"use client";

import Link from "next/link";
import { Clapperboard, Clock, Film } from "lucide-react";
import { ProjectStatusBadge, isJobActive } from "@/components/projects/status";
import { ProgressBar } from "@/components/ui/progress";
import type { Project } from "@/lib/api/types";
import { formatDuration, formatRelative } from "@/lib/format";
import { mediaUrls, useMedia } from "@/lib/hooks/use-media";
import { routes } from "@/lib/routes";

export function ProjectCard({ project }: { project: Project }) {
  const job = isJobActive(project.active_job) ? project.active_job : null;
  const media = useMedia(project);
  const thumbnail = mediaUrls.projectThumbnail(project, media);
  return (
    <Link
      href={routes.project(project.id)}
      className="group surface-card flex flex-col overflow-hidden transition-[border-color,transform] duration-300 hover:-translate-y-0.5 hover:border-line-strong"
    >
      <div className="relative aspect-video overflow-hidden bg-mist">
        {thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element -- private media, not optimizable by next/image
          <img
            src={thumbnail}
            alt=""
            className="size-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
            loading="lazy"
          />
        ) : (
          <div className="grid size-full place-items-center text-subtle/70">
            <Film className="size-8" aria-hidden="true" />
          </div>
        )}
        {project.duration_seconds ? (
          <span className="absolute bottom-2 right-2 rounded-md bg-ink/80 px-1.5 py-0.5 font-mono text-[11px] text-white">
            {formatDuration(project.duration_seconds)}
          </span>
        ) : null}
      </div>
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="line-clamp-2 text-sm font-semibold text-ink">{project.name}</h3>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ProjectStatusBadge status={project.status} />
          <span className="rounded-full border border-line px-2 py-0.5 font-mono text-[11px] text-subtle">{project.aspect_ratio}</span>
        </div>
        {job ? <ProgressBar value={job.progress} label={`${project.name} progress`} /> : null}
        <div className="mt-auto flex items-center justify-between text-xs text-subtle">
          <span className="inline-flex items-center gap-1">
            <Clapperboard className="size-3.5" aria-hidden="true" />
            {project.clips.total} clips · {project.clips.ready} exported
          </span>
          <span className="inline-flex items-center gap-1">
            <Clock className="size-3.5" aria-hidden="true" />
            {formatRelative(project.created_at)}
          </span>
        </div>
      </div>
    </Link>
  );
}
