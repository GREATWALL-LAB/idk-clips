import { Badge, StatusDot, type Tone } from "@/components/ui/badge";
import type { Clip, Job, ProjectStatus } from "@/lib/api/types";

const PROJECT_STATUS: Record<ProjectStatus, { label: string; tone: Tone; busy?: boolean }> = {
  awaiting_upload: { label: "Waiting for upload", tone: "neutral" },
  importing: { label: "Importing", tone: "info", busy: true },
  uploaded: { label: "Ready to process", tone: "neutral" },
  queued: { label: "Queued", tone: "info", busy: true },
  transcribing: { label: "Transcribing", tone: "info", busy: true },
  transcribed: { label: "Transcribed", tone: "brand" },
  analyzing: { label: "Finding clips", tone: "info", busy: true },
  ready: { label: "Clips ready", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
};

export function isProjectBusy(status: ProjectStatus): boolean {
  return Boolean(PROJECT_STATUS[status]?.busy);
}

export function ProjectStatusBadge({ status }: { status: ProjectStatus }) {
  const meta = PROJECT_STATUS[status] ?? { label: status, tone: "neutral" as Tone };
  return (
    <Badge tone={meta.tone}>
      <StatusDot tone={meta.tone} pulse={meta.busy} />
      {meta.label}
    </Badge>
  );
}

const CLIP_STATUS: Record<Clip["status"], { label: string; tone: Tone }> = {
  suggested: { label: "Not exported", tone: "neutral" },
  rendering: { label: "Exporting", tone: "info" },
  ready: { label: "Exported", tone: "success" },
  failed: { label: "Export failed", tone: "danger" },
};

export function ClipStatusBadge({ status }: { status: Clip["status"] }) {
  const meta = CLIP_STATUS[status];
  return (
    <Badge tone={meta.tone}>
      <StatusDot tone={meta.tone} pulse={status === "rendering"} />
      {meta.label}
    </Badge>
  );
}

export const JOB_LABELS: Record<Job["type"], string> = {
  import_url: "Importing video",
  transcribe: "Transcribing",
  process: "Processing",
  detect_clips: "Finding clips",
  render_clip: "Exporting clip",
  purge_files: "Deleting files",
};

export function isJobActive(job: Job | null | undefined): job is Job {
  return Boolean(job && (job.status === "queued" || job.status === "running"));
}
