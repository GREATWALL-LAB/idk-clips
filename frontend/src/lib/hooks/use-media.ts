"use client";

import { useEffect, useState } from "react";
import { apiUrl, errorMessage } from "@/lib/api/client";
import { bridgeUrls, probeBridge, readAccess, type WorkerAccess } from "@/lib/api/bridge";
import type { Clip, MediaHost, Project } from "@/lib/api/types";

export type MediaState =
  | { kind: "server" }
  | { kind: "checking" }
  | { kind: "worker"; access: WorkerAccess }
  | { kind: "elsewhere"; message: string }
  | { kind: "error"; message: string };

const reachability = new Map<string, Promise<boolean>>();

export const ELSEWHERE_MESSAGE =
  "These files are stored on your worker computer. Open IDK Clips in a browser on that computer, with the worker running, to play or download them.";

/**
 * How this browser can reach a project's files: through the API (local/server mode)
 * or through the paired worker's local bridge (hybrid mode, same computer only).
 */
export function useMedia(item: { media_host: MediaHost; worker_id: string | null } | null | undefined): MediaState {
  const workerId = item?.media_host === "worker" ? item.worker_id : null;
  const [state, setState] = useState<{ workerId: string | null; value: MediaState }>({ workerId: null, value: { kind: "checking" } });

  useEffect(() => {
    if (!workerId) return;
    let cancelled = false;
    readAccess(workerId)
      .then(async (access) => {
        const port = Number(new URL(access.origin).port);
        let probe = reachability.get(workerId);
        if (!probe) {
          probe = probeBridge(port, workerId);
          reachability.set(workerId, probe);
          probe.then((ok) => !ok && setTimeout(() => reachability.delete(workerId), 15_000));
        }
        const ok = await probe;
        if (cancelled) return;
        setState({ workerId, value: ok ? { kind: "worker", access } : { kind: "elsewhere", message: ELSEWHERE_MESSAGE } });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ workerId, value: { kind: "error", message: errorMessage(error) } });
      });
    return () => {
      cancelled = true;
    };
  }, [workerId]);

  if (!item) return { kind: "checking" };
  if (item.media_host !== "worker") return { kind: "server" };
  if (!workerId) return { kind: "elsewhere", message: ELSEWHERE_MESSAGE };
  return state.workerId === workerId ? state.value : { kind: "checking" };
}

/** Media URLs for whichever place holds the files (null when unavailable right now). */
export const mediaUrls = {
  projectVideo(project: Project, state: MediaState): string | null {
    if (!project.has_media) return null;
    if (state.kind === "server") return project.media_url ? apiUrl(project.media_url) : null;
    return state.kind === "worker" ? bridgeUrls.projectMedia(state.access, project) : null;
  },
  projectThumbnail(project: Project, state: MediaState): string | null {
    if (state.kind === "server") return project.thumbnail_url ? apiUrl(project.thumbnail_url) : null;
    if (state.kind === "worker" && project.thumbnail_url) return bridgeUrls.projectThumbnail(state.access, project);
    return null;
  },
  clipVideo(clip: Clip, state: MediaState): string | null {
    if (!clip.preview_url) return null;
    const version = `v=${encodeURIComponent(clip.rendered_at ?? "")}`;
    if (state.kind === "server") return `${apiUrl(clip.preview_url)}?${version}`;
    return state.kind === "worker" ? `${bridgeUrls.clipFile(state.access, clip)}&${version}` : null;
  },
  clipDownload(clip: Clip, state: MediaState): string | null {
    if (!clip.download_url) return null;
    if (state.kind === "server") return apiUrl(clip.download_url);
    return state.kind === "worker" ? bridgeUrls.clipFile(state.access, clip, true) : null;
  },
  clipThumbnail(clip: Clip, state: MediaState): string | null {
    if (!clip.thumbnail_url) return null;
    if (state.kind === "server") return apiUrl(clip.thumbnail_url);
    return state.kind === "worker" ? bridgeUrls.clipThumbnail(state.access, clip) : null;
  },
};
