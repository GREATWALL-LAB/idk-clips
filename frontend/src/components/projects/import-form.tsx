"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { CirclePlay, ExternalLink, Link2, Search, Upload, WandSparkles } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { RatioPicker } from "@/components/editor/ratio-picker";
import { UploadDropzone, validateVideoFile } from "@/components/projects/upload-dropzone";
import { WorkerNeeded } from "@/components/projects/worker-needed";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Alert } from "@/components/ui/empty-state";
import { Field, Input, RangeInput, SegmentedControl, Select, Switch } from "@/components/ui/form";
import { ProgressBar, Skeleton } from "@/components/ui/progress";
import { useToast } from "@/components/ui/toast";
import { ApiError, errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { ClientConfig, ProcessingOptions, Project, YouTubeVideo } from "@/lib/api/types";
import { uploadVideo, type UploadHandle, type UploadProgress } from "@/lib/api/upload";
import { formatBytes } from "@/lib/format";
import { useLocalWorker } from "@/lib/hooks/use-local-worker";
import { usePolling } from "@/lib/hooks/use-polling";
import { routes } from "@/lib/routes";

type Mode = "upload" | "youtube" | "link";

function stripExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return (dot > 0 ? name.slice(0, dot) : name).replace(/[_-]+/g, " ").trim().slice(0, 200);
}

/** Processing options shared by "new project" and the project settings dialog. */
export function ProcessingOptionsFields({
  config,
  value,
  onChange,
}: {
  config: ClientConfig;
  value: ProcessingOptions;
  onChange: (value: ProcessingOptions) => void;
}) {
  const set = <K extends keyof ProcessingOptions>(key: K, v: ProcessingOptions[K]) => onChange({ ...value, [key]: v });
  const english = value.language === "en";
  const models = config.whisper_models.filter((m) => m.multilingual || english || value.language === "auto");
  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <div className="space-y-1.5 sm:col-span-2">
        <p className="text-[13px] font-medium text-ink">Export shape</p>
        <RatioPicker value={value.aspect_ratio} onChange={(ratio) => set("aspect_ratio", ratio)} label="Default aspect ratio for clips" />
        <p className="text-xs text-subtle">The default for every clip. You can change it for any single clip in the editor, before exporting.</p>
      </div>
      <Field label="Spoken language" htmlFor="language" hint="English is the default. Choose Auto-detect for other languages.">
        <Select
          id="language"
          value={value.language}
          onChange={(e) => {
            const language = e.target.value;
            const current = config.whisper_models.find((m) => m.id === value.whisper_model);
            const keepModel = !current || current.multilingual || language === "en";
            onChange({ ...value, language, whisper_model: keepModel ? value.whisper_model : config.default_whisper_model.replace(".en", "") });
          }}
        >
          <option value="en">English</option>
          <option value="auto">Auto-detect</option>
          {config.languages
            .filter((l) => l.code !== "en")
            .map((l) => (
              <option key={l.code} value={l.code}>
                {l.name}
              </option>
            ))}
        </Select>
      </Field>
      <Field label="Speech model" htmlFor="model" hint={config.whisper_models.find((m) => m.id === (value.whisper_model ?? config.default_whisper_model))?.note}>
        <Select id="model" value={value.whisper_model ?? config.default_whisper_model} onChange={(e) => set("whisper_model", e.target.value)}>
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label} · {m.size_mb >= 1000 ? `${(m.size_mb / 1000).toFixed(1)} GB` : `${m.size_mb} MB`}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={`Number of clips: ${value.clip_count}`} htmlFor="clip-count" hint="The AI suggests up to this many. Fewer are returned if the video has fewer good moments.">
        <RangeInput id="clip-count" min={5} max={10} step={1} value={value.clip_count} onChange={(e) => set("clip_count", Number(e.target.value))} />
      </Field>
      <Field label="Clip length" htmlFor="min-length" hint="Short-form clips usually work best between 20 and 60 seconds.">
        <div className="flex items-center gap-2">
          <Select id="min-length" aria-label="Minimum clip length" value={value.min_clip_seconds} onChange={(e) => set("min_clip_seconds", Number(e.target.value))}>
            {[10, 15, 20, 30, 45].map((s) => (
              <option key={s} value={s} disabled={s >= value.max_clip_seconds}>
                {s}s minimum
              </option>
            ))}
          </Select>
          <Select aria-label="Maximum clip length" value={value.max_clip_seconds} onChange={(e) => set("max_clip_seconds", Number(e.target.value))}>
            {[30, 45, 60, 90, 120, 180].map((s) => (
              <option key={s} value={s} disabled={s <= value.min_clip_seconds}>
                {s}s maximum
              </option>
            ))}
          </Select>
        </div>
      </Field>
      <div className="sm:col-span-2">
        <Switch
          id="auto-process"
          checked={value.auto_process}
          onChange={(v) => set("auto_process", v)}
          label="Start processing right after the upload"
          description="Transcribe the video and find clips automatically."
        />
      </div>
    </div>
  );
}

export const DEFAULT_OPTIONS: ProcessingOptions = {
  language: "en",
  whisper_model: null,
  clip_count: 8,
  min_clip_seconds: 20,
  max_clip_seconds: 60,
  auto_process: true,
  aspect_ratio: "9:16",
};

function YouTubeCard({ video }: { video: YouTubeVideo }) {
  return (
    <div className="flex gap-4 rounded-2xl border border-line bg-canvas p-3">
      {video.thumbnail_url ? (
        // eslint-disable-next-line @next/next/no-img-element -- official YouTube thumbnail (i.ytimg.com)
        <img src={video.thumbnail_url} alt="" className="aspect-video w-36 shrink-0 rounded-xl object-cover" />
      ) : (
        <span className="grid aspect-video w-36 shrink-0 place-items-center rounded-xl bg-mist text-subtle">
          <CirclePlay className="size-6" aria-hidden="true" />
        </span>
      )}
      <div className="min-w-0 py-1">
        <p className="line-clamp-2 text-sm font-semibold text-ink">{video.title ?? "YouTube video"}</p>
        {video.author_name ? <p className="mt-0.5 text-xs text-subtle">{video.author_name}</p> : null}
        <a href={video.url} target="_blank" rel="noreferrer noopener" className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-brand hover:text-brand-700">
          Open on YouTube <ExternalLink className="size-3" aria-hidden="true" />
        </a>
      </div>
    </div>
  );
}

export function ImportForm() {
  const router = useRouter();
  const toast = useToast();
  const { meta } = useAuth();
  const hybrid = meta?.mode === "hybrid";
  const worker = useLocalWorker(hybrid);
  const configFetcher = useCallback((signal: AbortSignal) => api.config(signal), []);
  const { data: config, error: configError } = usePolling(configFetcher, null);
  const [mode, setMode] = useState<Mode>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [video, setVideo] = useState<YouTubeVideo | null>(null);
  const [lookingUp, setLookingUp] = useState(false);
  const [name, setName] = useState("");
  const [rights, setRights] = useState(false);
  const [options, setOptions] = useState<ProcessingOptions>(DEFAULT_OPTIONS);
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const uploadRef = useRef<UploadHandle | null>(null);

  useEffect(() => () => uploadRef.current?.abort(), []);

  function pickFile(picked: File | null) {
    setError(null);
    if (!picked) {
      setFile(null);
      setFileError(null);
      return;
    }
    const problem = config ? validateVideoFile(picked, config.allowed_extensions, config.max_upload_mb) : null;
    setFileError(problem);
    setFile(problem ? null : picked);
    if (!problem && !name && mode === "upload") setName(stripExtension(picked.name));
  }

  async function lookUp() {
    setError(null);
    setLookingUp(true);
    try {
      const found = await api.youtubeLookup(youtubeUrl.trim());
      setVideo(found);
      if (!name && found.title) setName(found.title.slice(0, 200));
    } catch (err) {
      setVideo(null);
      setError(errorMessage(err));
    } finally {
      setLookingUp(false);
    }
  }

  async function sendFile(project: Project) {
    const handle = uploadVideo(project.id, file as File, setProgress, hybrid ? worker.local?.id ?? null : null);
    uploadRef.current = handle;
    await handle.promise;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!config) return;
    setError(null);
    setSubmitting(true);
    const body = { ...options, whisper_model: options.whisper_model ?? config.default_whisper_model };
    if (mode === "link") {
      try {
        const project = await api.importUrl({ ...body, url: url.trim(), name: name.trim() || undefined });
        toast.success("Import started.");
        router.push(routes.project(project.id));
      } catch (err) {
        setError(errorMessage(err));
        setSubmitting(false);
      }
      return;
    }
    if (!file) return;
    let projectId: string | null = null;
    try {
      const project =
        mode === "youtube"
          ? await api.createFromYouTube({ ...body, url: youtubeUrl.trim(), name: name.trim() || undefined })
          : await api.createProject({ ...body, name: name.trim() || stripExtension(file.name) || "Untitled video" });
      projectId = project.id;
      await sendFile(project);
      toast.success(options.auto_process ? "Upload complete. Processing has started." : "Upload complete.");
      router.push(routes.project(project.id));
    } catch (err) {
      // Remove the empty project so a failed or cancelled upload leaves nothing behind.
      if (projectId) await api.deleteProject(projectId).catch(() => undefined);
      setError(err instanceof ApiError && err.code === "aborted" ? "Upload cancelled." : errorMessage(err));
      setProgress(null);
      setSubmitting(false);
    } finally {
      uploadRef.current = null;
    }
  }

  if (configError) return <Alert>{errorMessage(configError)}</Alert>;
  if (!config) return <Skeleton className="h-96" />;

  const needsLocalWorker = hybrid && mode !== "link";
  const workerReady = !needsLocalWorker || Boolean(worker.local);
  const uploading = progress !== null;
  const sourceReady = mode === "link" ? url.trim().length > 8 : mode === "youtube" ? Boolean(video && file) : Boolean(file);
  const canSubmit = rights && !submitting && workerReady && sourceReady;
  const remaining = progress && progress.bytesPerSecond > 0 ? (progress.total - progress.loaded) / progress.bytesPerSecond : null;
  const destination = hybrid && worker.local ? `your worker “${worker.local.name}”` : "this IDK Clips server";

  const sourceOptions: Array<{ value: Mode; label: string; icon: React.ReactNode }> = [
    { value: "upload", label: "Video file", icon: <Upload className="size-3.5" aria-hidden="true" /> },
    { value: "youtube", label: "YouTube", icon: <CirclePlay className="size-3.5" aria-hidden="true" /> },
  ];
  if (config.url_import_enabled) sourceOptions.push({ value: "link", label: "Direct link", icon: <Link2 className="size-3.5" aria-hidden="true" /> });

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <Card>
        <CardHeader icon={<Upload className="size-4" />} title="Video source" description="Use a video you own or have permission to use." />
        <CardBody className="space-y-5">
          <SegmentedControl<Mode>
            label="Video source"
            value={mode}
            onChange={(m) => {
              setMode(m);
              setError(null);
            }}
            options={sourceOptions}
          />

          {mode === "youtube" ? (
            <div className="space-y-4">
              <Field label="YouTube link" htmlFor="youtube-url" hint="A watch, Shorts or youtu.be link. Only public details are looked up, through YouTube's official oEmbed service.">
                <div className="flex gap-2">
                  <Input
                    id="youtube-url"
                    type="url"
                    inputMode="url"
                    placeholder="https://www.youtube.com/watch?v=…"
                    value={youtubeUrl}
                    onChange={(e) => {
                      setYoutubeUrl(e.target.value);
                      setVideo(null);
                    }}
                  />
                  <Button onClick={lookUp} loading={lookingUp} disabled={youtubeUrl.trim().length < 10} icon={<Search className="size-4" aria-hidden="true" />}>
                    Look up
                  </Button>
                </div>
              </Field>
              {video ? <YouTubeCard video={video} /> : null}
              {video?.notice ? <Alert tone="warning">{video.notice}</Alert> : null}
              <Alert tone="info" title="Add your own copy of the video">
                IDK Clips never downloads from YouTube: YouTube&apos;s terms only allow downloads through YouTube&apos;s own features, and we
                will not bypass its protections. If this is your video, download the original from <strong>YouTube Studio → Content → ⋮ →
                Download</strong> (or Google Takeout) and add it below. The project keeps the YouTube link for reference.
              </Alert>
              {video ? (
                <>
                  <UploadDropzone file={file} onFile={pickFile} allowed={config.allowed_extensions} maxMb={config.max_upload_mb} disabled={submitting} />
                  {fileError ? <Alert>{fileError}</Alert> : null}
                </>
              ) : null}
            </div>
          ) : mode === "upload" ? (
            <>
              <UploadDropzone file={file} onFile={pickFile} allowed={config.allowed_extensions} maxMb={config.max_upload_mb} disabled={submitting} />
              {fileError ? <Alert>{fileError}</Alert> : null}
            </>
          ) : (
            <div className="space-y-3">
              <Field label="Direct link to a video file" htmlFor="url" hint="For example https://example.com/talk.mp4 from your own server or a public-domain archive.">
                <Input id="url" type="url" inputMode="url" placeholder="https://" value={url} onChange={(e) => setUrl(e.target.value)} />
              </Field>
              <p className="text-xs text-subtle">
                Video platforms such as YouTube, TikTok and Instagram are refused here; use the YouTube option for your own YouTube videos.
              </p>
            </div>
          )}

          {needsLocalWorker && !worker.local ? <WorkerNeeded state={worker} /> : null}
          {needsLocalWorker && worker.local ? (
            <p className="text-xs text-subtle">
              The file goes straight from this browser to <span className="font-medium text-ink">{worker.local.name}</span> on this computer.
              It is never uploaded to the IDK Clips website.
            </p>
          ) : null}

          <Field label="Project name" htmlFor="name">
            <Input id="name" maxLength={200} placeholder="My video" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
        </CardBody>
      </Card>

      <Card>
        <CardHeader icon={<WandSparkles className="size-4" />} title="Processing options" description="You can change these later and run processing again." />
        <CardBody>
          <ProcessingOptionsFields config={config} value={options} onChange={setOptions} />
        </CardBody>
      </Card>

      <label className="flex items-start gap-3 rounded-2xl border border-line bg-surface p-4 text-sm text-ink-soft">
        <input type="checkbox" className="mt-0.5 size-4 accent-brand" checked={rights} onChange={(e) => setRights(e.target.checked)} />
        <span>I own this video or have permission to use it, and I will respect its license when publishing clips.</span>
      </label>

      {error ? <Alert>{error}</Alert> : null}

      {uploading && progress ? (
        <Card>
          <CardBody className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium text-ink">
                Sending {file?.name} to {destination}
              </span>
              <span className="font-mono text-xs text-muted">{Math.round((progress.loaded / progress.total) * 100)}%</span>
            </div>
            <ProgressBar value={progress.loaded / progress.total} label="Upload progress" />
            <div className="flex items-center justify-between text-xs text-subtle">
              <span>
                {formatBytes(progress.loaded)} of {formatBytes(progress.total)} · {formatBytes(progress.bytesPerSecond)}/s
                {remaining !== null && remaining > 1 ? ` · about ${Math.ceil(remaining)} s left` : ""}
              </span>
              <Button size="sm" variant="ghost" onClick={() => uploadRef.current?.abort()}>
                Cancel upload
              </Button>
            </div>
          </CardBody>
        </Card>
      ) : null}

      <div className="flex justify-end">
        <Button
          type="submit"
          variant="primary"
          size="lg"
          loading={submitting}
          disabled={!canSubmit}
          icon={mode === "link" ? <Link2 className="size-4" aria-hidden="true" /> : <Upload className="size-4" aria-hidden="true" />}
        >
          {mode === "link" ? "Import video" : options.auto_process ? "Upload & process" : "Upload"}
        </Button>
      </div>
    </form>
  );
}
