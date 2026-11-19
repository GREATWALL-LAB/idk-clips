"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Captions,
  Crop,
  Download,
  Film,
  Maximize,
  Pause,
  Play,
  Proportions,
  Repeat,
  RotateCcw,
  Save,
  Scissors,
  Trash2,
  Type,
} from "lucide-react";
import { CaptionOverlay } from "@/components/editor/caption-overlay";
import { generatedCues, linesFromCues, type Cue } from "@/components/editor/captions";
import { RatioPicker } from "@/components/editor/ratio-picker";
import { Timeline } from "@/components/editor/timeline";
import { JobProgress } from "@/components/projects/job-progress";
import { ClipStatusBadge, isJobActive } from "@/components/projects/status";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonAnchor, ButtonLink } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Alert, EmptyState } from "@/components/ui/empty-state";
import { Field, Input, RangeInput, SegmentedControl, Select, Switch, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/progress";
import { useToast } from "@/components/ui/toast";
import { ApiError, errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { AspectRatio, CaptionLine, CaptionStyle, Clip, ClipLayout, ClipUpdate, Project, Segment } from "@/lib/api/types";
import { cropAxis, cropObjectPosition, fitFrame, ratioInfo, ratioValue } from "@/lib/aspect";
import { cn } from "@/lib/cn";
import { formatBytes, formatTimestamp, parseTimestamp } from "@/lib/format";
import { mediaUrls, useMedia } from "@/lib/hooks/use-media";
import { usePolling } from "@/lib/hooks/use-polling";
import { routes } from "@/lib/routes";

type Draft = {
  title: string;
  description: string;
  start: number;
  end: number;
  aspect_ratio: AspectRatio;
  layout: ClipLayout;
  crop_position: number;
  auto_frame: boolean;
  captions_enabled: boolean;
  style: CaptionStyle;
  editedLines: CaptionLine[] | null;
};

type Baseline = { clip: Clip; edited: CaptionLine[] | null };
type Tab = "timing" | "layout" | "captions" | "text";

const PREVIEW_MAX_WIDTH = 520;
const PREVIEW_MAX_HEIGHT = 560;

const liveInterval = (clip: Clip) => (isJobActive(clip.active_job) || clip.status === "rendering" ? 1_000 : null);

function draftFrom(clip: Clip, edited: CaptionLine[] | null): Draft {
  return {
    title: clip.title,
    description: clip.description,
    start: clip.start_seconds,
    end: clip.end_seconds,
    aspect_ratio: clip.aspect_ratio,
    layout: clip.layout === "fit" ? "fit" : "crop",
    crop_position: clip.crop_position,
    auto_frame: clip.auto_frame,
    captions_enabled: clip.captions_enabled,
    style: clip.caption_style,
    editedLines: edited,
  };
}

export function buildUpdate(baseline: Baseline, draft: Draft): ClipUpdate {
  const c = baseline.clip;
  const body: ClipUpdate = {};
  if (draft.title.trim() && draft.title.trim() !== c.title) body.title = draft.title.trim();
  if (draft.description !== c.description) body.description = draft.description;
  if (Math.abs(draft.start - c.start_seconds) > 0.0005) body.start_seconds = draft.start;
  if (Math.abs(draft.end - c.end_seconds) > 0.0005) body.end_seconds = draft.end;
  if (draft.aspect_ratio !== c.aspect_ratio) body.aspect_ratio = draft.aspect_ratio;
  if (draft.layout !== c.layout) body.layout = draft.layout;
  // A manual position switches automatic framing off on the server; only send one of them.
  if (draft.auto_frame !== c.auto_frame && draft.auto_frame) body.auto_frame = true;
  else if (Math.abs(draft.crop_position - c.crop_position) > 0.0005 || draft.auto_frame !== c.auto_frame) body.crop_position = draft.crop_position;
  if (draft.captions_enabled !== c.captions_enabled) body.captions_enabled = draft.captions_enabled;
  if (JSON.stringify(draft.style) !== JSON.stringify(c.caption_style)) body.caption_style = draft.style;
  if (JSON.stringify(draft.editedLines) !== JSON.stringify(baseline.edited)) body.caption_lines = draft.editedLines ?? [];
  return body;
}

function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ width: 300, height: 533 });
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, size] as const;
}

function TimeField({ label, value, onCommit }: { label: string; value: number; onCommit: (v: number) => void }) {
  const [text, setText] = useState(formatTimestamp(value));
  const [focused, setFocused] = useState(false);
  const shown = focused ? text : formatTimestamp(value);
  return (
    <Field label={label} htmlFor={`time-${label}`}>
      <Input
        id={`time-${label}`}
        className="font-mono"
        value={shown}
        onFocus={() => {
          setText(formatTimestamp(value));
          setFocused(true);
        }}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          setFocused(false);
          const parsed = parseTimestamp(text);
          if (parsed !== null) onCommit(parsed);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
      />
    </Field>
  );
}

function ClipEditor({ initialClip, project, segments, initialEdited }: { initialClip: Clip; project: Project; segments: Segment[]; initialEdited: CaptionLine[] | null }) {
  const toast = useToast();
  const [baseline, setBaseline] = useState<Baseline>({ clip: initialClip, edited: initialEdited });
  const [draft, setDraft] = useState<Draft>(() => draftFrom(initialClip, initialEdited));
  const [tab, setTab] = useState<Tab>("timing");
  const [snap, setSnap] = useState(true);
  const [loop, setLoop] = useState(true);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [time, setTime] = useState(initialClip.start_seconds);
  const [playing, setPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [frameRef, frameSize] = useElementSize<HTMLDivElement>();
  const media = useMedia(project);

  const liveFetcher = useCallback((signal: AbortSignal) => api.clip(initialClip.id, signal), [initialClip.id]);
  const live = usePolling(liveFetcher, liveInterval);
  const serverClip = live.data ?? baseline.clip;
  const job = isJobActive(serverClip.active_job) ? serverClip.active_job : null;

  const duration = project.duration_seconds ?? draft.end;
  const update = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));
  const setStyle = (patch: Partial<CaptionStyle>) => setDraft((d) => ({ ...d, style: { ...d.style, ...patch } }));

  const allWords = useMemo(() => segments.flatMap((s) => s.words.map((w) => ({ start: w.start, end: w.end, text: w.text }))), [segments]);
  const generated = useMemo(() => generatedCues(segments, draft.start, draft.end, draft.style.words_per_line), [segments, draft.start, draft.end, draft.style.words_per_line]);
  const cues: Cue[] = draft.editedLines ?? generated;
  const body = useMemo(() => buildUpdate(baseline, draft), [baseline, draft]);
  const dirty = Object.keys(body).length > 0;

  const ratio = ratioInfo(draft.aspect_ratio);
  const frame = fitFrame(draft.aspect_ratio, PREVIEW_MAX_WIDTH, PREVIEW_MAX_HEIGHT);
  // Square and landscape previews are as wide as the whole editor panel at "lg", so they sit
  // above the controls until there is room for both (xl). The controls column never gets
  // narrower than its buttons and inputs need; the preview shrinks instead (it keeps its ratio).
  const wideFrame = ratioValue(draft.aspect_ratio) >= 1;
  const axis = cropAxis(project.width, project.height, draft.aspect_ratio);

  // Blurred-background preview for the "fit" layout (drawn from the playing video).
  useEffect(() => {
    if (draft.layout !== "fit") return;
    let frameId = 0;
    const draw = () => {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      const context = canvas?.getContext("2d");
      if (video && canvas && context && video.readyState >= 2 && video.videoWidth) {
        const scale = Math.max(canvas.width / video.videoWidth, canvas.height / video.videoHeight);
        const w = video.videoWidth * scale;
        const h = video.videoHeight * scale;
        context.drawImage(video, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
      }
      frameId = requestAnimationFrame(draw);
    };
    frameId = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frameId);
  }, [draft.layout]);

  function seek(seconds: number) {
    const video = videoRef.current;
    if (video) video.currentTime = seconds;
    setTime(seconds);
  }

  function playFromStart() {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = draft.start;
    void video.play();
  }

  function togglePlay() {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      if (video.currentTime < draft.start || video.currentTime >= draft.end) video.currentTime = draft.start;
      void video.play();
    } else video.pause();
  }

  async function save(): Promise<boolean> {
    if (!dirty) return true;
    setSaving(true);
    try {
      const updated = await api.updateClip(initialClip.id, body);
      const captions = await api.clipCaptions(initialClip.id);
      const edited = captions.edited ? captions.lines : null;
      setBaseline({ clip: updated, edited });
      setDraft(draftFrom(updated, edited));
      live.refresh();
      toast.success("Changes saved.");
      return true;
    } catch (error) {
      toast.error(errorMessage(error));
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function exportClip() {
    setExporting(true);
    try {
      if (!(await save())) return;
      await api.renderClip(initialClip.id);
      toast.info(project.media_host === "worker" ? "Export sent to your worker." : "Export started. You can keep editing other clips while it renders.");
      live.refresh();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setExporting(false);
    }
  }

  function editLine(index: number, text: string) {
    setDraft((d) => {
      const lines = (d.editedLines ?? linesFromCues(generated)).map((line, i) => (i === index ? { ...line, text } : line));
      return { ...d, editedLines: lines };
    });
  }

  function removeLine(index: number) {
    setDraft((d) => ({ ...d, editedLines: (d.editedLines ?? linesFromCues(generated)).filter((_, i) => i !== index) }));
  }

  const relative = Math.max(0, time - draft.start);
  const sourceUrl = mediaUrls.projectVideo(project, media);
  const exportedUrl = mediaUrls.clipVideo(serverClip, media);
  const downloadUrl = mediaUrls.clipDownload(serverClip, media);
  const lines = draft.editedLines ?? linesFromCues(generated);
  const exportedRatio = serverClip.aspect_ratio;

  return (
    <>
      <Link href={routes.project(project.id)} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden="true" /> {project.name}
      </Link>
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0 flex-1">
          <label htmlFor="clip-title" className="sr-only">
            Clip title
          </label>
          <input
            id="clip-title"
            value={draft.title}
            maxLength={200}
            onChange={(e) => update({ title: e.target.value })}
            className="w-full rounded-lg bg-transparent font-display text-[28px] font-bold tracking-tight text-ink outline-none focus:bg-surface focus:px-2 focus:ring-2 focus:ring-brand/20"
          />
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <ClipStatusBadge status={serverClip.status} />
            <Badge tone="lime">
              {draft.aspect_ratio} · {ratio.width}×{ratio.height}
            </Badge>
            {serverClip.score != null ? <Badge tone="brand">AI score {serverClip.score} (estimate)</Badge> : null}
            {dirty ? <Badge tone="warning">Unsaved changes</Badge> : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => void save()} loading={saving} disabled={!dirty || Boolean(job)} icon={<Save className="size-4" aria-hidden="true" />}>
            Save
          </Button>
          <Button variant="primary" onClick={exportClip} loading={exporting} disabled={Boolean(job)} icon={<Film className="size-4" aria-hidden="true" />}>
            {serverClip.status === "ready" && !dirty ? "Export again" : "Export MP4"}
          </Button>
        </div>
      </div>

      <div
        className={cn(
          "grid grid-cols-1 gap-6",
          wideFrame ? "xl:grid-cols-[minmax(0,auto)_minmax(360px,1fr)]" : "lg:grid-cols-[minmax(0,auto)_minmax(340px,1fr)]",
        )}
        data-testid="editor-layout"
      >
        {/* Preview */}
        <div className="flex min-w-0 flex-col items-center gap-3">
          <div
            ref={frameRef}
            className="relative max-w-full overflow-hidden rounded-[22px] border-[5px] border-ink bg-ink shadow-lift transition-[width] duration-300"
            style={{ width: frame.width, aspectRatio: String(ratioValue(draft.aspect_ratio)) }}
            data-testid="preview-frame"
          >
            {draft.layout === "fit" ? (
              <canvas
                ref={canvasRef}
                width={96}
                height={Math.round(96 / ratioValue(draft.aspect_ratio))}
                className="absolute inset-0 size-full scale-110 opacity-80 blur-xl"
                aria-hidden="true"
              />
            ) : null}
            {sourceUrl ? (
              <video
                ref={videoRef}
                src={sourceUrl}
                playsInline
                preload="auto"
                className="absolute inset-0 size-full"
                style={{
                  objectFit: draft.layout === "crop" ? "cover" : "contain",
                  objectPosition: draft.layout === "crop" ? cropObjectPosition(axis, draft.crop_position) : "50% 50%",
                }}
                onLoadedMetadata={(e) => {
                  e.currentTarget.currentTime = draft.start;
                }}
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
                onTimeUpdate={(e) => {
                  const t = e.currentTarget.currentTime;
                  setTime(t);
                  if (t >= draft.end) {
                    if (loop && !e.currentTarget.paused) e.currentTarget.currentTime = draft.start;
                    else e.currentTarget.pause();
                  }
                }}
              />
            ) : (
              <div className="absolute inset-0 grid place-items-center p-6 text-center text-xs text-white/80">
                {media.kind === "elsewhere" || media.kind === "error" ? media.message : "Loading the video…"}
              </div>
            )}
            {draft.captions_enabled ? <CaptionOverlay cues={cues} time={relative} style={draft.style} frameWidth={frameSize.width} frameHeight={frameSize.height} /> : null}
          </div>
          <div className="flex w-full items-center justify-between gap-2" style={{ maxWidth: frame.width }}>
            <Button size="sm" onClick={togglePlay} disabled={!sourceUrl} icon={playing ? <Pause className="size-3.5" aria-hidden="true" /> : <Play className="size-3.5" aria-hidden="true" />}>
              {playing ? "Pause" : "Play"}
            </Button>
            <span className="font-mono text-xs text-muted">
              {formatTimestamp(Math.min(relative, draft.end - draft.start))} / {formatTimestamp(draft.end - draft.start)}
            </span>
            <button
              type="button"
              onClick={() => setLoop(!loop)}
              aria-pressed={loop}
              className={cn("grid size-8 place-items-center rounded-lg transition-colors", loop ? "bg-brand-50 text-brand" : "text-subtle hover:bg-mist")}
              title="Loop the clip"
              aria-label="Loop the clip"
            >
              <Repeat className="size-4" aria-hidden="true" />
            </button>
          </div>
          <p className="text-center text-xs text-subtle" style={{ maxWidth: frame.width }}>
            Live preview in {draft.aspect_ratio}. The MP4 is rendered by FFmpeg with the same framing and captions.
          </p>
        </div>

        {/* Controls */}
        <div className="min-w-0 space-y-5">
          <SegmentedControl<Tab>
            label="Editor sections"
            value={tab}
            onChange={setTab}
            options={[
              { value: "timing", label: "Timing", icon: <Scissors className="size-3.5" aria-hidden="true" /> },
              { value: "layout", label: "Format", icon: <Proportions className="size-3.5" aria-hidden="true" /> },
              { value: "captions", label: "Style", icon: <Captions className="size-3.5" aria-hidden="true" /> },
              { value: "text", label: "Text", icon: <Type className="size-3.5" aria-hidden="true" /> },
            ]}
          />

          {tab === "timing" ? (
            <Card>
              <CardBody className="space-y-5">
                <Timeline
                  duration={duration}
                  start={draft.start}
                  end={draft.end}
                  currentTime={time}
                  words={allWords}
                  snap={snap}
                  onChange={(start, end) => update({ start, end })}
                  onSeek={seek}
                />
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <TimeField label="Start" value={draft.start} onCommit={(v) => v < draft.end - 3 && v >= 0 && update({ start: v })} />
                    <div className="flex flex-wrap gap-1.5">
                      {[-1, -0.1, 0.1, 1].map((d) => (
                        <Button key={d} size="sm" variant="ghost" onClick={() => update({ start: Math.max(0, Math.min(draft.start + d, draft.end - 3)) })}>
                          {d > 0 ? `+${d}` : d}s
                        </Button>
                      ))}
                      <Button size="sm" variant="ghost" onClick={() => time < draft.end - 3 && update({ start: time })}>
                        Set to playhead
                      </Button>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <TimeField label="End" value={draft.end} onCommit={(v) => v > draft.start + 3 && v <= duration && update({ end: v })} />
                    <div className="flex flex-wrap gap-1.5">
                      {[-1, -0.1, 0.1, 1].map((d) => (
                        <Button key={d} size="sm" variant="ghost" onClick={() => update({ end: Math.min(duration, Math.max(draft.end + d, draft.start + 3)) })}>
                          {d > 0 ? `+${d}` : d}s
                        </Button>
                      ))}
                      <Button size="sm" variant="ghost" onClick={() => time > draft.start + 3 && update({ end: Math.min(time, duration) })}>
                        Set to playhead
                      </Button>
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <Button size="sm" onClick={playFromStart} disabled={!sourceUrl} icon={<Play className="size-3.5" aria-hidden="true" />}>
                    Play from start
                  </Button>
                  {serverClip.suggested_start != null && serverClip.suggested_end != null ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => update({ start: serverClip.suggested_start ?? draft.start, end: serverClip.suggested_end ?? draft.end })}
                      icon={<RotateCcw className="size-3.5" aria-hidden="true" />}
                    >
                      Reset to AI suggestion
                    </Button>
                  ) : null}
                  <div className="ml-auto w-56">
                    <Switch id="snap" checked={snap} onChange={setSnap} label="Snap to words" />
                  </div>
                </div>
                <Field label="Description" htmlFor="clip-description">
                  <Textarea id="clip-description" maxLength={1000} value={draft.description} onChange={(e) => update({ description: e.target.value })} />
                </Field>
                {serverClip.reason ? <p className="text-sm italic text-subtle">Why the AI picked it: {serverClip.reason}</p> : null}
              </CardBody>
            </Card>
          ) : null}

          {tab === "layout" ? (
            <Card>
              <CardBody className="space-y-6">
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-[13px] font-medium text-ink">Aspect ratio</p>
                    {draft.aspect_ratio !== project.aspect_ratio ? (
                      <button type="button" className="text-xs font-medium text-brand hover:text-brand-700" onClick={() => update({ aspect_ratio: project.aspect_ratio })}>
                        Use the project default ({project.aspect_ratio})
                      </button>
                    ) : (
                      <span className="text-xs text-subtle">Project default</span>
                    )}
                  </div>
                  <RatioPicker value={draft.aspect_ratio} onChange={(aspect_ratio) => update({ aspect_ratio })} label="Aspect ratio for this clip" />
                  <p className="text-xs text-subtle">
                    Exports at {ratio.width}×{ratio.height} for {ratio.use}. The source is {project.width ?? "?"}×{project.height ?? "?"}.
                  </p>
                </div>

                <SegmentedControl<ClipLayout>
                  label="Framing"
                  value={draft.layout}
                  onChange={(layout) => update({ layout })}
                  options={[
                    { value: "crop", label: "Fill (crop)", icon: <Crop className="size-3.5" aria-hidden="true" /> },
                    { value: "fit", label: "Fit (whole picture)", icon: <Maximize className="size-3.5" aria-hidden="true" /> },
                  ]}
                />
                <p className="text-sm text-muted">
                  {draft.layout === "crop"
                    ? axis === null
                      ? "The source already has this shape, so nothing is cropped."
                      : `Fills the frame by trimming the ${axis === "x" ? "left and right" : "top and bottom"}. Nothing is stretched.`
                    : "Shows the whole picture, scaled without distortion, over a blurred copy that fills the rest of the frame."}
                </p>
                {draft.layout === "crop" && axis !== null ? (
                  <div className="space-y-4">
                    <Switch
                      id="auto-frame"
                      checked={draft.auto_frame}
                      onChange={(auto_frame) => update({ auto_frame })}
                      label="Find the main subject automatically"
                      description="When exporting, frames are sampled to keep the speaker or the most active area in view."
                    />
                    <Field
                      label={`Manual framing: ${Math.round(draft.crop_position * 100)}% from the ${axis === "x" ? "left" : "top"}`}
                      htmlFor="crop-position"
                      hint={draft.auto_frame ? "Moving the slider switches automatic framing off." : undefined}
                    >
                      <RangeInput
                        id="crop-position"
                        min={0}
                        max={1}
                        step={0.01}
                        value={draft.crop_position}
                        onChange={(e) => update({ crop_position: Number(e.target.value), auto_frame: false })}
                      />
                    </Field>
                  </div>
                ) : null}
              </CardBody>
            </Card>
          ) : null}

          {tab === "captions" ? (
            <Card>
              <CardBody className="space-y-5">
                <Switch id="captions-enabled" checked={draft.captions_enabled} onChange={(v) => update({ captions_enabled: v })} label="Burn in captions" description="Captions use the real transcript (or your edited text)." />
                <div className={cn("grid gap-5 sm:grid-cols-2", !draft.captions_enabled && "pointer-events-none opacity-40")}>
                  <Field label="Font" htmlFor="font">
                    <Select id="font" value={draft.style.font} onChange={(e) => setStyle({ font: e.target.value as CaptionStyle["font"] })}>
                      <option value="Montserrat">Montserrat Bold</option>
                      <option value="Poppins">Poppins Bold</option>
                      <option value="Anton">Anton</option>
                    </Select>
                  </Field>
                  <Field label={`Size: ${draft.style.font_size}px`} htmlFor="font-size">
                    <RangeInput id="font-size" min={24} max={160} value={draft.style.font_size} onChange={(e) => setStyle({ font_size: Number(e.target.value) })} />
                  </Field>
                  <Field label="Position" htmlFor="position">
                    <SegmentedControl
                      label="Caption position"
                      value={draft.style.position}
                      onChange={(position) => setStyle({ position })}
                      options={[
                        { value: "top", label: "Top" },
                        { value: "middle", label: "Middle" },
                        { value: "bottom", label: "Bottom" },
                      ]}
                    />
                  </Field>
                  <Field label={`Words per caption: ${draft.style.words_per_line}`} htmlFor="words-per-line" hint={draft.editedLines ? "Not used while the text is edited." : undefined}>
                    <RangeInput id="words-per-line" min={1} max={10} value={draft.style.words_per_line} onChange={(e) => setStyle({ words_per_line: Number(e.target.value) })} />
                  </Field>
                  <div className="grid grid-cols-3 gap-3 sm:col-span-2">
                    {(
                      [
                        ["text_color", "Text"],
                        ["highlight_color", "Highlight"],
                        ["outline_color", draft.style.background ? "Box" : "Outline"],
                      ] as const
                    ).map(([key, label]) => (
                      <Field key={key} label={label} htmlFor={key}>
                        <input
                          id={key}
                          type="color"
                          value={key === "outline_color" && draft.style.background ? draft.style.background_color : draft.style[key]}
                          onChange={(e) =>
                            setStyle(key === "outline_color" && draft.style.background ? { background_color: e.target.value.toUpperCase() } : { [key]: e.target.value.toUpperCase() })
                          }
                          className="h-10 w-full cursor-pointer rounded-xl border border-line-strong bg-surface p-1"
                        />
                      </Field>
                    ))}
                  </div>
                  {!draft.style.background ? (
                    <Field label={`Outline: ${draft.style.outline_width}px`} htmlFor="outline">
                      <RangeInput id="outline" min={0} max={20} value={draft.style.outline_width} onChange={(e) => setStyle({ outline_width: Number(e.target.value) })} />
                    </Field>
                  ) : (
                    <div />
                  )}
                  <div className="space-y-4 sm:col-span-2">
                    <Switch id="background" checked={draft.style.background} onChange={(v) => setStyle({ background: v })} label="Background box" description="A solid box behind the text instead of an outline." />
                    <Switch id="uppercase" checked={draft.style.uppercase} onChange={(v) => setStyle({ uppercase: v })} label="Uppercase" />
                    <Switch id="highlight" checked={draft.style.highlight_words} onChange={(v) => setStyle({ highlight_words: v })} label="Highlight the spoken word" description="Uses the word timings from the transcript." />
                  </div>
                </div>
              </CardBody>
            </Card>
          ) : null}

          {tab === "text" ? (
            <Card>
              <CardBody className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm text-muted">
                    {draft.editedLines
                      ? "You edited the caption text. Edited captions are shown without word highlighting."
                      : "Captions come from the transcript. Fix any word below; your edits only change the captions."}
                  </p>
                  {draft.editedLines ? (
                    <Button size="sm" variant="ghost" onClick={() => update({ editedLines: null })} icon={<RotateCcw className="size-3.5" aria-hidden="true" />}>
                      Reset to transcript
                    </Button>
                  ) : null}
                </div>
                {lines.length === 0 ? (
                  <EmptyState title="No speech in this range" description="There are no transcript words between the start and end of this clip." />
                ) : (
                  <ol className="max-h-[480px] space-y-2 overflow-y-auto pr-1">
                    {lines.map((line, index) => (
                      <li key={`${line.start}-${index}`} className="flex items-center gap-2">
                        <button type="button" onClick={() => seek(draft.start + line.start)} className="w-16 shrink-0 text-left font-mono text-xs text-subtle hover:text-brand">
                          {formatTimestamp(line.start)}
                        </button>
                        <Input aria-label={`Caption at ${formatTimestamp(line.start)}`} maxLength={300} value={line.text} onChange={(e) => editLine(index, e.target.value)} />
                        <button
                          type="button"
                          onClick={() => removeLine(index)}
                          className="grid size-9 shrink-0 place-items-center rounded-lg text-subtle hover:bg-danger-50 hover:text-danger"
                          aria-label={`Remove caption at ${formatTimestamp(line.start)}`}
                        >
                          <Trash2 className="size-4" aria-hidden="true" />
                        </button>
                      </li>
                    ))}
                  </ol>
                )}
              </CardBody>
            </Card>
          ) : null}

          {/* Export status */}
          <Card>
            <CardBody className="space-y-4">
              <h2 className="text-[15px] font-semibold text-ink">Export</h2>
              {job ? (
                <JobProgress job={job} onChange={live.refresh} />
              ) : serverClip.status === "failed" ? (
                <Alert title="The export failed">
                  {serverClip.error_message ?? "The export failed."} You can change the settings and export again.
                </Alert>
              ) : serverClip.preview_url ? (
                exportedUrl ? (
                  // Sized by the card (container query), not by the screen: the card can be
                  // narrow on a wide screen when it sits next to the preview.
                  <div className="@container" data-testid="export-result">
                  <div className={cn("flex min-w-0 flex-col gap-4", ratioValue(exportedRatio) < 1 && "@sm:flex-row @sm:items-start")}>
                    <video
                      key={exportedUrl}
                      src={exportedUrl}
                      controls
                      playsInline
                      className={cn("max-w-full rounded-2xl bg-ink", ratioValue(exportedRatio) < 1 ? "max-h-80 self-center @sm:self-start" : "w-full")}
                      style={{ aspectRatio: String(ratioValue(exportedRatio)) }}
                    />
                    <div className="min-w-0 flex-1 space-y-3 text-sm">
                      <p className="text-ink-soft">
                        {serverClip.status === "ready" && !dirty ? "This is the exported file." : "This export is out of date. Export again to apply your changes."}
                      </p>
                      <p className="text-subtle">
                        {formatBytes(serverClip.output_size_bytes)} · MP4 (H.264 + AAC) · {exportedRatio}
                      </p>
                      {downloadUrl ? (
                        <ButtonAnchor href={downloadUrl} variant="primary" className="w-full @xs:w-auto" icon={<Download className="size-4" aria-hidden="true" />}>
                          Download MP4
                        </ButtonAnchor>
                      ) : null}
                    </div>
                  </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted">{media.kind === "elsewhere" || media.kind === "error" ? media.message : "Loading the exported file…"}</p>
                )
              ) : (
                <p className="text-sm text-muted">Not exported yet. Click “Export MP4” to render this clip in {draft.aspect_ratio} with FFmpeg.</p>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </>
  );
}

export function ClipEditorLoader({ projectId, clipId }: { projectId: string; clipId: string }) {
  const clipFetcher = useCallback((signal: AbortSignal) => api.clip(clipId, signal), [clipId]);
  const projectFetcher = useCallback((signal: AbortSignal) => api.project(projectId, signal), [projectId]);
  const transcriptFetcher = useCallback(
    (signal: AbortSignal) =>
      api.transcript(projectId, signal).catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }),
    [projectId],
  );
  const captionsFetcher = useCallback((signal: AbortSignal) => api.clipCaptions(clipId, signal), [clipId]);
  const clip = usePolling(clipFetcher, null, clipId);
  const project = usePolling(projectFetcher, null, projectId);
  const transcript = usePolling(transcriptFetcher, null, projectId);
  const captions = usePolling(captionsFetcher, null, clipId);

  const notFound = [clip.error, project.error].some((e) => e instanceof ApiError && e.status === 404) || (clip.data && clip.data.project_id !== projectId);
  if (notFound) {
    return <EmptyState title="Clip not found" description="It may have been deleted." action={<ButtonLink href={routes.project(projectId)}>Back to the project</ButtonLink>} />;
  }
  const error = clip.error || project.error || transcript.error || captions.error;
  if (error) return <Alert>{errorMessage(error)}</Alert>;
  if (!clip.data || !project.data || transcript.data === undefined || !captions.data) return <Skeleton className="h-[600px]" />;

  return (
    <ClipEditor
      key={clip.data.id}
      initialClip={clip.data}
      project={project.data}
      segments={transcript.data?.segments ?? []}
      initialEdited={captions.data.edited ? captions.data.lines : null}
    />
  );
}
