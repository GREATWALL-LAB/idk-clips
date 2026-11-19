"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Upload } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { UploadDropzone, validateVideoFile } from "@/components/projects/upload-dropzone";
import { WorkerNeeded } from "@/components/projects/worker-needed";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/empty-state";
import { ProgressBar } from "@/components/ui/progress";
import { ApiError, errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import { uploadVideo, type UploadHandle, type UploadProgress } from "@/lib/api/upload";
import { formatBytes } from "@/lib/format";
import { useLocalWorker } from "@/lib/hooks/use-local-worker";
import { usePolling } from "@/lib/hooks/use-polling";

/** Upload (or retry the upload of) the video for an existing project. */
export function UploadIntoProject({ projectId, onUploaded }: { projectId: string; onUploaded: () => void }) {
  const { meta } = useAuth();
  const hybrid = meta?.mode === "hybrid";
  const worker = useLocalWorker(hybrid);
  const configFetcher = useCallback((signal: AbortSignal) => api.config(signal), []);
  const { data: config } = usePolling(configFetcher, null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const handleRef = useRef<UploadHandle | null>(null);

  useEffect(() => () => handleRef.current?.abort(), []);

  async function start() {
    if (!file) return;
    setError(null);
    const handle = uploadVideo(projectId, file, setProgress, hybrid ? worker.local?.id ?? null : null);
    handleRef.current = handle;
    try {
      await handle.promise;
      onUploaded();
    } catch (err) {
      setError(err instanceof ApiError && err.code === "aborted" ? "Upload cancelled." : errorMessage(err));
    } finally {
      handleRef.current = null;
      setProgress(null);
    }
  }

  if (!config) return null;
  if (hybrid && !worker.local) return <WorkerNeeded state={worker} />;
  return (
    <div className="space-y-3">
      <UploadDropzone
        file={file}
        allowed={config.allowed_extensions}
        maxMb={config.max_upload_mb}
        disabled={progress !== null}
        onFile={(picked) => {
          const problem = picked ? validateVideoFile(picked, config.allowed_extensions, config.max_upload_mb) : null;
          setError(problem);
          setFile(problem ? null : picked);
        }}
      />
      {error ? <Alert>{error}</Alert> : null}
      {progress ? (
        <div className="space-y-2">
          <ProgressBar value={progress.loaded / progress.total} label="Upload progress" />
          <div className="flex items-center justify-between text-xs text-subtle">
            <span>
              {formatBytes(progress.loaded)} of {formatBytes(progress.total)}
            </span>
            <Button size="sm" variant="ghost" onClick={() => handleRef.current?.abort()}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <Button variant="primary" className="w-full" disabled={!file} onClick={start} icon={<Upload className="size-4" aria-hidden="true" />}>
          {hybrid && worker.local ? `Send to ${worker.local.name}` : "Upload video"}
        </Button>
      )}
    </div>
  );
}
