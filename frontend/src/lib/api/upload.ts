import { apiUrl, ApiError, NETWORK_ERROR_MESSAGE } from "@/lib/api/client";
import { uploadToWorker } from "@/lib/api/bridge";
import type { Project } from "@/lib/api/types";
import { CSRF_HEADER } from "@/lib/config";

export type UploadProgress = { loaded: number; total: number; bytesPerSecond: number };

export type UploadHandle = { promise: Promise<unknown>; abort: () => void };

/**
 * Upload a video to the API server as the raw request body (local and server mode).
 * XMLHttpRequest is used because, unlike fetch, it reports real upload progress.
 */
export function uploadProjectMedia(
  projectId: string,
  file: File,
  onProgress: (progress: UploadProgress) => void,
): UploadHandle & { promise: Promise<Project> } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<Project>((resolve, reject) => {
    const started = performance.now();
    xhr.open("PUT", apiUrl(`/projects/${projectId}/media?filename=${encodeURIComponent(file.name)}`));
    xhr.withCredentials = true;
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    for (const [name, value] of Object.entries(CSRF_HEADER)) xhr.setRequestHeader(name, value);
    xhr.responseType = "json";

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const seconds = Math.max((performance.now() - started) / 1000, 0.001);
      onProgress({ loaded: event.loaded, total: event.total, bytesPerSecond: event.loaded / seconds });
    };
    xhr.onload = () => {
      const body = xhr.response as { error?: { code?: string; message?: string; request_id?: string } } | Project;
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as Project);
        return;
      }
      const error = (body as { error?: { code?: string; message?: string; request_id?: string } })?.error;
      reject(new ApiError(xhr.status, error?.code ?? "upload_failed", error?.message ?? `Upload failed with status ${xhr.status}.`, error?.request_id));
    };
    xhr.onerror = () => reject(new ApiError(0, "network_error", NETWORK_ERROR_MESSAGE));
    xhr.onabort = () => reject(new ApiError(0, "aborted", "The upload was cancelled."));
    xhr.send(file);
  });
  return { promise, abort: () => xhr.abort() };
}

/**
 * Upload a project's video to wherever this instance keeps files: the API server, or
 * (hybrid mode) the user's own worker on this computer. The server never sees the
 * bytes in the second case.
 */
export function uploadVideo(
  projectId: string,
  file: File,
  onProgress: (progress: UploadProgress) => void,
  workerId: string | null,
): UploadHandle {
  return workerId ? uploadToWorker(workerId, projectId, file, onProgress) : uploadProjectMedia(projectId, file, onProgress);
}
