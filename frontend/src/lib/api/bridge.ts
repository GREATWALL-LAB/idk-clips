/**
 * Talking to the user's own worker (hybrid mode).
 *
 * The IDK Clips server never stores video in hybrid mode. The browser sends the file
 * straight to the worker's local bridge on this computer (http://127.0.0.1:<port>),
 * and plays or downloads results from there. Every request carries a short-lived
 * transfer token that the signed-in user gets from the server, and the worker checks
 * that token with the server before it reads or writes anything.
 *
 * Browsers treat 127.0.0.1 as a secure, local address, so an https:// website may
 * talk to it. Some browsers first ask the user for permission ("access other apps and
 * services on this device"); that prompt is expected.
 */
import { ApiError } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { Clip, Project, TransferToken } from "@/lib/api/types";

export const BRIDGE_HOST = "127.0.0.1";

export function bridgeOrigin(port: number): string {
  return `http://${BRIDGE_HOST}:${port}`;
}

export type WorkerAccess = { origin: string; token: string; expiresAt: number };

const READ_MARGIN_MS = 60_000;
const readCache = new Map<string, Promise<WorkerAccess>>();

function toAccess(token: TransferToken): WorkerAccess {
  return { origin: bridgeOrigin(token.bridge_port), token: token.token, expiresAt: new Date(token.expires_at).getTime() };
}

/** A read token for one worker, reused until shortly before it expires. */
export function readAccess(workerId: string, now: () => number = Date.now): Promise<WorkerAccess> {
  const cached = readCache.get(workerId);
  if (cached) {
    return cached.then((access) => {
      if (access.expiresAt - READ_MARGIN_MS > now()) return access;
      readCache.delete(workerId);
      return readAccess(workerId, now);
    });
  }
  const request = api.transferToken(workerId, { scope: "read" }).then(toAccess);
  readCache.set(workerId, request);
  request.catch(() => readCache.delete(workerId));
  return request;
}

export function clearReadAccess(): void {
  readCache.clear();
}

/** Is this worker's bridge running on the computer this browser runs on? */
export async function probeBridge(port: number, workerId: string, timeoutMs = 2_500): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${bridgeOrigin(port)}/bridge/v1/hello`, { signal: controller.signal, cache: "no-store" });
    if (!response.ok) return false;
    const body = (await response.json()) as { worker_id?: string };
    return body.worker_id === workerId;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

function withToken(access: WorkerAccess, path: string, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams({ token: access.token, ...extra });
  return `${access.origin}/bridge/v1${path}?${params.toString()}`;
}

export const bridgeUrls = {
  projectMedia: (access: WorkerAccess, project: Pick<Project, "id">) => withToken(access, `/projects/${project.id}/media`),
  projectThumbnail: (access: WorkerAccess, project: Pick<Project, "id">) => withToken(access, `/projects/${project.id}/thumbnail`),
  clipFile: (access: WorkerAccess, clip: Pick<Clip, "id" | "project_id" | "title">, download = false) =>
    withToken(access, `/projects/${clip.project_id}/clips/${clip.id}/file`, download ? { download: "true", name: clip.title } : {}),
  clipThumbnail: (access: WorkerAccess, clip: Pick<Clip, "id" | "project_id">) =>
    withToken(access, `/projects/${clip.project_id}/clips/${clip.id}/thumbnail`),
};

export type UploadProgress = { loaded: number; total: number; bytesPerSecond: number };
export type UploadHandle = { promise: Promise<void>; abort: () => void };

/** Send a video to the worker's bridge with real upload progress (XMLHttpRequest). */
export function uploadToWorker(
  workerId: string,
  projectId: string,
  file: File,
  onProgress: (progress: UploadProgress) => void,
): UploadHandle {
  let xhr: XMLHttpRequest | null = null;
  let aborted = false;
  const promise = (async () => {
    const token = await api.transferToken(workerId, { scope: "upload", project_id: projectId });
    if (aborted) throw new ApiError(0, "aborted", "The upload was cancelled.");
    await new Promise<void>((resolve, reject) => {
      const request = new XMLHttpRequest();
      xhr = request;
      const started = performance.now();
      request.open("PUT", `${bridgeOrigin(token.bridge_port)}/bridge/v1/projects/${projectId}/media?filename=${encodeURIComponent(file.name)}`);
      request.setRequestHeader("Authorization", `Bearer ${token.token}`);
      request.setRequestHeader("Content-Type", file.type || "application/octet-stream");
      request.responseType = "json";
      request.upload.onprogress = (event) => {
        if (!event.lengthComputable) return;
        const seconds = Math.max((performance.now() - started) / 1000, 0.001);
        onProgress({ loaded: event.loaded, total: event.total, bytesPerSecond: event.loaded / seconds });
      };
      request.onload = () => {
        if (request.status >= 200 && request.status < 300) return resolve();
        const error = (request.response as { error?: { code?: string; message?: string } } | null)?.error;
        reject(new ApiError(request.status, error?.code ?? "upload_failed", error?.message ?? `The worker answered with status ${request.status}.`));
      };
      request.onerror = () =>
        reject(new ApiError(0, "worker_unreachable", "Your worker could not be reached on this computer. Check that it is running (python -m app.agent run)."));
      request.onabort = () => reject(new ApiError(0, "aborted", "The upload was cancelled."));
      request.send(file);
    });
  })();
  return {
    promise,
    abort: () => {
      aborted = true;
      (xhr as XMLHttpRequest | null)?.abort();
    },
  };
}
