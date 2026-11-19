"use client";

import Link from "next/link";
import { useState } from "react";
import { Download, Pencil, Play, Sparkles } from "lucide-react";
import { ClipStatusBadge } from "@/components/projects/status";
import { Badge } from "@/components/ui/badge";
import { ButtonAnchor, ButtonLink } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import type { Clip } from "@/lib/api/types";
import { ratioValue } from "@/lib/aspect";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import { mediaUrls, useMedia, type MediaState } from "@/lib/hooks/use-media";
import { routes } from "@/lib/routes";

export function ClipPreviewDialog({ clip, media, open, onClose }: { clip: Clip; media: MediaState; open: boolean; onClose: () => void }) {
  const src = mediaUrls.clipVideo(clip, media);
  const download = clip.status === "ready" ? mediaUrls.clipDownload(clip, media) : null;
  const ratio = ratioValue(clip.aspect_ratio);
  // Square and landscape clips get the wide dialog and fill its width; tall clips are
  // limited by the screen height. Either way the player keeps the clip's real shape.
  const wide = ratio >= 1;
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={clip.title}
      description={clip.project_name ?? undefined}
      wide={wide}
      footer={
        download ? (
          <ButtonAnchor href={download} variant="primary" className="w-full sm:w-auto" icon={<Download className="size-4" aria-hidden="true" />}>
            Download MP4 · {clip.aspect_ratio}
          </ButtonAnchor>
        ) : undefined
      }
    >
      {src ? (
        <video
          key={clip.rendered_at ?? clip.id}
          src={src}
          controls
          autoPlay
          playsInline
          className={cn("mx-auto block max-w-full rounded-2xl bg-ink", wide ? "max-h-[65vh] w-full" : "max-h-[65vh]")}
          // Wide clips: as wide as the dialog, but never taller than 65% of the screen.
          style={{ aspectRatio: String(ratio), ...(wide ? { maxWidth: `min(100%, calc(65vh * ${ratio}))` } : {}) }}
          data-testid="clip-preview-video"
        />
      ) : media.kind === "elsewhere" || media.kind === "error" ? (
        <p className="text-sm text-muted">{media.message}</p>
      ) : (
        <p className="text-sm text-muted">This clip has not been exported yet.</p>
      )}
    </Dialog>
  );
}

export function ClipCard({ clip }: { clip: Clip }) {
  const [previewing, setPreviewing] = useState(false);
  const media = useMedia(clip);
  const thumbnail = mediaUrls.clipThumbnail(clip, media);
  const download = mediaUrls.clipDownload(clip, media);
  const playable = Boolean(mediaUrls.clipVideo(clip, media));
  return (
    <article className="group surface-card flex flex-col overflow-hidden">
      <button
        type="button"
        onClick={() => playable && setPreviewing(true)}
        disabled={!playable}
        className="relative aspect-[9/16] max-h-80 w-full overflow-hidden bg-mist disabled:cursor-default"
        aria-label={playable ? `Play ${clip.title}` : `${clip.title} (not exported yet)`}
      >
        {thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element -- private media, not optimizable by next/image
          <img src={thumbnail} alt="" loading="lazy" className="size-full object-contain transition-transform duration-500 group-hover:scale-[1.03]" />
        ) : (
          <div className="grid size-full place-items-center p-4 text-center">
            <Sparkles className="size-6 text-brand/60" aria-hidden="true" />
          </div>
        )}
        {playable ? (
          <span className="absolute inset-0 grid place-items-center bg-ink/0 transition-colors group-hover:bg-ink/25">
            <span className="grid size-12 scale-90 place-items-center rounded-full bg-white text-ink opacity-0 shadow-lg transition-all group-hover:scale-100 group-hover:opacity-100">
              <Play className="ml-0.5 size-5" aria-hidden="true" />
            </span>
          </span>
        ) : null}
        <span className="absolute left-2 top-2 rounded-md bg-ink/80 px-1.5 py-0.5 font-mono text-[11px] text-white">{clip.aspect_ratio}</span>
        <span className="absolute bottom-2 right-2 rounded-md bg-ink/80 px-1.5 py-0.5 font-mono text-[11px] text-white">
          {formatDuration(clip.duration_seconds)}
        </span>
      </button>
      <div className="flex flex-1 flex-col gap-2.5 p-3.5">
        <div>
          <h3 className="line-clamp-2 text-sm font-semibold text-ink">{clip.title}</h3>
          {clip.project_name ? <p className="mt-0.5 truncate text-xs text-subtle">{clip.project_name}</p> : null}
        </div>
        <div className="flex flex-wrap gap-1.5">
          <ClipStatusBadge status={clip.status} />
          {clip.media_host === "worker" && media.kind === "elsewhere" ? <Badge>On your worker</Badge> : null}
        </div>
        <div className="mt-auto flex gap-2">
          <ButtonLink href={routes.clip(clip.project_id, clip.id)} size="sm" className="flex-1" icon={<Pencil className="size-3.5" aria-hidden="true" />}>
            Edit
          </ButtonLink>
          {download ? (
            <a
              href={download}
              className="inline-flex h-8 items-center justify-center gap-1.5 rounded-xl border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink transition-colors hover:bg-canvas"
              aria-label={`Download ${clip.title}`}
            >
              <Download className="size-3.5" aria-hidden="true" />
            </a>
          ) : null}
        </div>
      </div>
      <ClipPreviewDialog clip={clip} media={media} open={previewing} onClose={() => setPreviewing(false)} />
    </article>
  );
}

export function ClipGridLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="text-sm font-semibold text-brand hover:text-brand-700">
      {children}
    </Link>
  );
}
