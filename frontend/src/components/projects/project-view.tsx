"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import {
  ArrowLeft,
  AudioLines,
  CirclePlay,
  Clapperboard,
  ExternalLink,
  Film,
  Plus,
  RotateCcw,
  Settings2,
  Trash2,
  WandSparkles,
} from "lucide-react";
import { AddClipDialog } from "@/components/clips/add-clip-dialog";
import { ClipList } from "@/components/clips/clip-list";
import { DEFAULT_OPTIONS, ProcessingOptionsFields } from "@/components/projects/import-form";
import { JobProgress } from "@/components/projects/job-progress";
import { ProjectStatusBadge, isJobActive, isProjectBusy } from "@/components/projects/status";
import { TranscriptPanel } from "@/components/projects/transcript-panel";
import { UploadIntoProject } from "@/components/projects/upload-into-project";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { Alert, EmptyState } from "@/components/ui/empty-state";
import { Field, Input, SegmentedControl } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/progress";
import { useToast } from "@/components/ui/toast";
import { ApiError, errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { Clip, ClipList as ClipListData, ProcessingOptions, Project } from "@/lib/api/types";
import { formatBytes, formatDuration } from "@/lib/format";
import { mediaUrls, useMedia } from "@/lib/hooks/use-media";
import { usePolling } from "@/lib/hooks/use-polling";
import { routes } from "@/lib/routes";

const projectInterval = (p: Project) => (isJobActive(p.active_job) || isProjectBusy(p.status) ? 1_500 : 20_000);
const clipsInterval = (list: ClipListData) => (list.items.some((c) => isJobActive(c.active_job)) ? 1_500 : null);

function ProjectSettingsDialog({ project, open, onClose, onSaved }: { project: Project; open: boolean; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const configFetcher = useCallback((signal: AbortSignal) => api.config(signal), []);
  const { data: config } = usePolling(configFetcher, null);
  const [name, setName] = useState(project.name);
  const [options, setOptions] = useState<ProcessingOptions>({
    ...DEFAULT_OPTIONS,
    language: project.language,
    whisper_model: project.whisper_model,
    clip_count: project.clip_count,
    min_clip_seconds: project.min_clip_seconds,
    max_clip_seconds: project.max_clip_seconds,
    auto_process: project.auto_process,
    aspect_ratio: project.aspect_ratio,
  });
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      const { language, whisper_model, clip_count, min_clip_seconds, max_clip_seconds, aspect_ratio } = options;
      await api.updateProject(project.id, {
        name: name.trim() || project.name,
        language,
        whisper_model: whisper_model ?? undefined,
        clip_count,
        min_clip_seconds,
        max_clip_seconds,
        aspect_ratio,
      });
      toast.success("Project settings saved. Processing options apply the next time you process the video.");
      onSaved();
      onClose();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      wide
      title="Project settings"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={save} loading={saving}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <Field label="Name" htmlFor="project-name">
          <Input id="project-name" maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        {config ? <ProcessingOptionsFields config={config} value={options} onChange={setOptions} /> : <Skeleton className="h-40" />}
      </div>
    </Dialog>
  );
}

export function ProjectView({ projectId }: { projectId: string }) {
  const router = useRouter();
  const toast = useToast();
  const fetcher = useCallback((signal: AbortSignal) => api.project(projectId, signal), [projectId]);
  const { data: project, error, refresh } = usePolling(fetcher, projectInterval, projectId);
  const clipsFetcher = useCallback((signal: AbortSignal) => api.projectClips(projectId, signal), [projectId]);
  const clips = usePolling(clipsFetcher, clipsInterval, `${projectId}:${project?.status}:${project?.clips.total}:${project?.clips.ready}`);
  const media = useMedia(project);

  const videoRef = useRef<HTMLVideoElement>(null);
  const stopAtRef = useRef<number | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [tab, setTab] = useState<"clips" | "transcript">("clips");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);

  const reload = useCallback(() => {
    refresh();
    clips.refresh();
  }, [refresh, clips]);

  const seek = useCallback((seconds: number, play = false) => {
    const video = videoRef.current;
    if (!video) return;
    stopAtRef.current = null;
    video.currentTime = seconds;
    if (play) void video.play();
  }, []);

  const playClip = useCallback((clip: Clip) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = clip.start_seconds;
    stopAtRef.current = clip.end_seconds;
    void video.play();
    video.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  async function run(action: string, task: () => Promise<unknown>, message: string) {
    setBusy(action);
    try {
      await task();
      toast.info(message);
      reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function deleteProject() {
    setBusy("delete");
    try {
      await api.deleteProject(projectId);
      toast.success("Project and all of its files were deleted.");
      router.push(routes.projects);
    } catch (err) {
      toast.error(errorMessage(err));
      setBusy(null);
    }
  }

  if (error instanceof ApiError && error.status === 404) {
    return (
      <EmptyState
        title="Project not found"
        description="It may have been deleted, or it belongs to another account."
        action={<ButtonLink href={routes.projects}>Back to projects</ButtonLink>}
      />
    );
  }
  if (!project) return error ? <Alert>{errorMessage(error)}</Alert> : <Skeleton className="h-[480px]" />;

  const job = isJobActive(project.active_job) ? project.active_job : null;
  const working = Boolean(job) || isProjectBusy(project.status);
  const duration = project.duration_seconds ?? 0;
  const clipItems = clips.data?.items ?? [];

  const meta = [
    project.duration_seconds ? formatDuration(project.duration_seconds) : null,
    project.width && project.height ? `${project.width}×${project.height}` : null,
    project.media_size_bytes ? formatBytes(project.media_size_bytes) : null,
    `Exports ${project.aspect_ratio}`,
    project.language === "auto" ? "Auto-detect language" : project.language.toUpperCase(),
    `Whisper ${project.whisper_model}`,
    project.ai_model ? `AI: ${project.ai_model}` : null,
  ].filter(Boolean);

  return (
    <>
      <Link href={routes.projects} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden="true" /> Projects
      </Link>
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="truncate font-display text-[28px] font-bold tracking-tight text-ink">{project.name}</h1>
            <ProjectStatusBadge status={project.status} />
          </div>
          <p className="mt-1.5 text-sm text-subtle">{meta.join(" · ")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => setSettingsOpen(true)} icon={<Settings2 className="size-3.5" aria-hidden="true" />}>
            Settings
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(true)} icon={<Trash2 className="size-3.5" aria-hidden="true" />}>
            Delete
          </Button>
        </div>
      </div>

      {project.error_message && !working ? (
        <Alert className="mb-6" title="Something went wrong">
          {project.error_message}
        </Alert>
      ) : null}

      {project.source_type === "youtube" && project.source_url ? (
        <div className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-surface px-4 py-3 text-sm">
          <CirclePlay className="size-4 text-brand" aria-hidden="true" />
          <span className="text-ink-soft">
            Source on YouTube: <span className="font-medium text-ink">{project.source_meta.title ?? "YouTube video"}</span>
            {project.source_meta.author_name ? <span className="text-subtle"> · {project.source_meta.author_name}</span> : null}
          </span>
          <a href={project.source_url} target="_blank" rel="noreferrer noopener" className="ml-auto inline-flex items-center gap-1 font-medium text-brand hover:text-brand-700">
            Open <ExternalLink className="size-3.5" aria-hidden="true" />
          </a>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0">
          {mediaUrls.projectVideo(project, media) ? (
            <video
              ref={videoRef}
              src={mediaUrls.projectVideo(project, media) ?? undefined}
              poster={mediaUrls.projectThumbnail(project, media) ?? undefined}
              controls
              playsInline
              preload="metadata"
              className="aspect-video w-full rounded-3xl border border-line bg-ink"
              onTimeUpdate={(event) => {
                const time = event.currentTarget.currentTime;
                setCurrentTime(time);
                if (stopAtRef.current !== null && time >= stopAtRef.current) {
                  event.currentTarget.pause();
                  stopAtRef.current = null;
                }
              }}
            />
          ) : (
            <div className="grid aspect-video w-full place-items-center rounded-3xl border border-dashed border-line-strong bg-surface p-6 text-center text-sm text-subtle">
              <span className="max-w-md">
                <Film className="mx-auto mb-3 size-7 text-subtle/70" aria-hidden="true" />
                {project.has_media && (media.kind === "elsewhere" || media.kind === "error")
                  ? media.message
                  : project.has_media
                    ? "Loading the video…"
                    : project.source_meta.source_removed_at
                      ? "The source video was removed by your retention setting. The transcript and exported clips are kept."
                      : project.status === "importing"
                        ? "The video is being imported…"
                        : "No video uploaded yet."}
              </span>
            </div>
          )}
        </div>

        <Card>
          <CardHeader icon={<WandSparkles className="size-4" />} title="Processing" />
          <CardBody className="space-y-4">
            {job ? (
              <JobProgress job={job} onChange={reload} />
            ) : project.status === "awaiting_upload" || (project.status === "failed" && !project.has_media && project.source_type !== "url") ? (
              <>
                <p className="text-sm text-muted">
                  {project.source_type === "youtube"
                    ? "Add the file you downloaded from YouTube Studio (or Google Takeout) to start."
                    : "Upload the video for this project to start."}
                </p>
                <UploadIntoProject projectId={project.id} onUploaded={reload} />
              </>
            ) : !project.has_media ? (
              <p className="text-sm text-muted">The video could not be imported. Delete this project and try another link or upload the file.</p>
            ) : !project.has_transcript ? (
              <>
                <p className="text-sm text-muted">Transcribe the speech, then let the AI suggest {project.clip_count} clips.</p>
                <Button
                  variant="primary"
                  className="w-full"
                  loading={busy === "process"}
                  onClick={() => run("process", () => api.processProject(project.id, {}), "Processing started.")}
                  icon={<AudioLines className="size-4" aria-hidden="true" />}
                >
                  Transcribe & find clips
                </Button>
              </>
            ) : (
              <>
                <p className="text-sm text-muted">
                  {project.clips.total
                    ? `${project.clips.total} clips · ${project.clips.ready} exported.`
                    : "The transcript is ready. Let the AI suggest clips."}
                </p>
                <div className="grid gap-2">
                  <Button
                    variant={project.clips.total ? "secondary" : "primary"}
                    loading={busy === "detect"}
                    onClick={() => run("detect", () => api.processProject(project.id, { transcribe: false }), "Looking for clips…")}
                    icon={<WandSparkles className="size-4" aria-hidden="true" />}
                  >
                    {project.clips.total ? "Find clips again" : "Find clips with AI"}
                  </Button>
                  <Button
                    variant="ghost"
                    loading={busy === "retranscribe"}
                    onClick={() => run("retranscribe", () => api.processProject(project.id, { transcribe: true }), "Transcribing again…")}
                    icon={<RotateCcw className="size-4" aria-hidden="true" />}
                  >
                    Transcribe again & find clips
                  </Button>
                </div>
                <p className="text-xs text-subtle">Clips you edited or exported are kept when you search again.</p>
              </>
            )}
          </CardBody>
        </Card>
      </div>

      <div className="mt-8">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="w-full max-w-xs">
            <SegmentedControl
              label="Project sections"
              value={tab}
              onChange={setTab}
              options={[
                { value: "clips", label: `Clips (${clipItems.length})`, icon: <Clapperboard className="size-3.5" aria-hidden="true" /> },
                { value: "transcript", label: "Transcript", icon: <AudioLines className="size-3.5" aria-hidden="true" /> },
              ]}
            />
          </div>
          {tab === "clips" && project.has_media ? (
            <Button size="sm" onClick={() => setAddOpen(true)} icon={<Plus className="size-3.5" aria-hidden="true" />}>
              Add clip manually
            </Button>
          ) : null}
        </div>
        {tab === "clips" ? (
          clips.loading && !clips.data ? (
            <Skeleton className="h-40" />
          ) : (
            <ClipList
              clips={clipItems}
              onPlay={playClip}
              onChanged={reload}
              emptyAction={
                project.has_transcript && !working ? (
                  <Button variant="primary" onClick={() => run("detect", () => api.processProject(project.id, { transcribe: false }), "Looking for clips…")}>
                    Find clips with AI
                  </Button>
                ) : null
              }
            />
          )
        ) : project.has_transcript ? (
          <TranscriptPanel projectId={project.id} version={project.updated_at} currentTime={currentTime} onSeek={(t) => seek(t, true)} />
        ) : (
          <EmptyState title="No transcript yet" description={working ? "The transcript will appear here when processing finishes." : "Process the video to create a transcript."} />
        )}
      </div>

      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        onConfirm={deleteProject}
        busy={busy === "delete"}
        title="Delete this project?"
        description={
          project.media_host === "worker"
            ? "The transcript and clips are deleted now. Your worker deletes the video and exported files the next time it is online. This cannot be undone."
            : "The video, transcript, clips and exported files will be permanently deleted. This cannot be undone."
        }
        confirmLabel="Delete project"
      />
      {settingsOpen ? <ProjectSettingsDialog project={project} open={settingsOpen} onClose={() => setSettingsOpen(false)} onSaved={reload} /> : null}
      {addOpen ? (
        <AddClipDialog
          open={addOpen}
          onClose={() => setAddOpen(false)}
          projectId={project.id}
          start={currentTime}
          duration={duration}
          onCreated={reload}
        />
      ) : null}
    </>
  );
}
