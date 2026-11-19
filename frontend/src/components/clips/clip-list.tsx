"use client";

import { useState } from "react";
import { Download, Film, Pencil, Play, Trash2, WandSparkles } from "lucide-react";
import { ClipStatusBadge, isJobActive } from "@/components/projects/status";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { ProgressBar } from "@/components/ui/progress";
import { useToast } from "@/components/ui/toast";
import { errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { Clip } from "@/lib/api/types";
import { formatDuration, formatTimestamp, percent } from "@/lib/format";
import { mediaUrls, useMedia } from "@/lib/hooks/use-media";
import { routes } from "@/lib/routes";

const SCORE_HELP = "AI interest score: a rough estimate from the transcript. It does not predict views or engagement.";

function ClipRow({ clip, onPlay, onChanged }: { clip: Clip; onPlay: (clip: Clip) => void; onChanged: () => void }) {
  const toast = useToast();
  const [exporting, setExporting] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const job = isJobActive(clip.active_job) ? clip.active_job : null;
  const media = useMedia(clip);
  const download = mediaUrls.clipDownload(clip, media);

  async function exportClip() {
    setExporting(true);
    try {
      await api.renderClip(clip.id);
      toast.info(`Exporting “${clip.title}”…`);
      onChanged();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setExporting(false);
    }
  }

  async function remove() {
    setDeleting(true);
    try {
      await api.deleteClip(clip.id);
      toast.success("Clip deleted.");
      setConfirm(false);
      onChanged();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <li className="surface-card p-4 transition-colors hover:border-line-strong">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-ink font-mono text-sm font-semibold text-lime">
          {clip.rank + 1}
        </span>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[15px] font-semibold text-ink">{clip.title}</h3>
            {clip.source === "manual" ? <Badge>Manual</Badge> : null}
            <Badge>{clip.aspect_ratio}</Badge>
            {clip.score != null ? (
              <Badge tone="brand">
                <span title={SCORE_HELP}>AI score {clip.score}</span>
                <span className="sr-only">. {SCORE_HELP}</span>
              </Badge>
            ) : null}
            <ClipStatusBadge status={clip.status} />
          </div>
          <p className="font-mono text-xs text-muted">
            {formatTimestamp(clip.start_seconds)} – {formatTimestamp(clip.end_seconds)} · {formatDuration(clip.duration_seconds)}
          </p>
          {clip.description ? <p className="text-sm text-ink-soft">{clip.description}</p> : null}
          {clip.reason ? <p className="text-[13px] italic text-subtle">Why: {clip.reason}</p> : null}
          {clip.error_message && clip.status === "failed" ? <p className="text-xs text-danger">{clip.error_message}</p> : null}
          {job ? (
            <div className="space-y-1.5 pt-1">
              <div className="flex justify-between text-xs text-muted">
                <span>{job.status === "queued" ? job.stage ?? "Waiting in queue" : job.stage}</span>
                <span className="font-mono">{percent(job.progress)}</span>
              </div>
              <ProgressBar value={job.progress} label={`Export progress for ${clip.title}`} />
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2 sm:w-auto sm:flex-col sm:items-stretch">
          <Button size="sm" onClick={() => onPlay(clip)} icon={<Play className="size-3.5" aria-hidden="true" />}>
            Play
          </Button>
          <ButtonLink size="sm" href={routes.clip(clip.project_id, clip.id)} icon={<Pencil className="size-3.5" aria-hidden="true" />}>
            Edit
          </ButtonLink>
          <Button size="sm" variant="primary" onClick={exportClip} loading={exporting} disabled={Boolean(job)} icon={<Film className="size-3.5" aria-hidden="true" />}>
            {clip.status === "ready" ? "Re-export" : "Export"}
          </Button>
          {download && clip.status === "ready" ? (
            <a
              href={download}
              className="inline-flex h-8 items-center justify-center gap-1.5 rounded-xl border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink transition-colors hover:bg-canvas"
            >
              <Download className="size-3.5" aria-hidden="true" /> Download
            </a>
          ) : null}
          <Button size="sm" variant="ghost" onClick={() => setConfirm(true)} disabled={Boolean(job)} icon={<Trash2 className="size-3.5" aria-hidden="true" />}>
            Delete
          </Button>
        </div>
      </div>
      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        onConfirm={remove}
        busy={deleting}
        title="Delete this clip?"
        description={`“${clip.title}” and its exported file will be removed. The source video is not affected.`}
      />
    </li>
  );
}

export function ClipList({
  clips,
  onPlay,
  onChanged,
  emptyAction,
}: {
  clips: Clip[];
  onPlay: (clip: Clip) => void;
  onChanged: () => void;
  emptyAction?: React.ReactNode;
}) {
  if (clips.length === 0) {
    return (
      <div className="flex flex-col items-center rounded-3xl border border-dashed border-line-strong bg-surface px-6 py-10 text-center">
        <WandSparkles className="size-6 text-brand" aria-hidden="true" />
        <p className="mt-3 text-sm font-medium text-ink">No clips yet</p>
        <p className="mt-1 max-w-sm text-sm text-muted">Let the AI find the best moments, or add a clip manually from the video above.</p>
        {emptyAction ? <div className="mt-5">{emptyAction}</div> : null}
      </div>
    );
  }
  return (
    <ul className="space-y-3">
      {clips.map((clip) => (
        <ClipRow key={clip.id} clip={clip} onPlay={onPlay} onChanged={onChanged} />
      ))}
    </ul>
  );
}
