/** TypeScript mirrors of the backend's public API schemas (backend/app/schemas, backend/app/api/v1). */

export type HealthResponse = {
  status: "ok";
  service: string;
  version: string;
  environment: string;
  time: string;
  uptime_seconds: number;
};

export type Mode = "local" | "server" | "hybrid";

/** GET /meta: how this instance runs (public, no secrets). */
export type Meta = {
  name: string;
  version: string;
  mode: Mode;
  accounts: boolean;
  registration_open: boolean;
  has_users: boolean;
  processing: "this_computer" | "this_server" | "your_worker";
  youtube_reference_enabled: boolean;
  url_import_enabled: boolean;
};

export type ComponentState = "ok" | "unavailable" | "misconfigured" | "not_configured";

export type ComponentStatus = {
  key: string;
  name: string;
  status: ComponentState;
  required: boolean;
  version: string | null;
  source: string | null;
  detail: string | null;
  hint: string | null;
};

export type SystemStatusResponse = {
  status: "ok" | "degraded";
  components: ComponentStatus[];
  checked_at: string;
};

// ------------------------------------------------------------------ auth
export type User = {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
  email_verified: boolean;
  age_confirmed: boolean;
};

export type RegisterResult = {
  user: User;
  /** True: no session yet; the emailed code must be entered first. */
  verification_required: boolean;
  code_sent: boolean;
  resend_after_seconds: number;
  code_ttl_minutes: number;
};

export type CodeSent = { resend_after_seconds: number; code_ttl_minutes: number };

export type AuthStatus = {
  has_users: boolean;
  registration_open: boolean;
  email_verification: boolean;
  mode: Mode;
  accounts: boolean;
};

export type Account = {
  user: User;
  retention_days: number;
  storage_used_bytes: number;
  projects: number;
  can_delete_account: boolean;
};

// ---------------------------------------------------------------- config
export type ClientConfig = {
  max_upload_mb: number;
  max_video_minutes: number;
  allowed_extensions: string[];
  url_import_enabled: boolean;
  storage_quota_mb: number | null;
  default_whisper_model: string;
  languages: Array<{ code: string; name: string }>;
  whisper_models: Array<{ id: string; label: string; size_mb: number; multilingual: boolean; note: string }>;
};

// ------------------------------------------------------------------ jobs
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export type Job = {
  id: string;
  project_id: string | null;
  clip_id: string | null;
  type: "import_url" | "transcribe" | "process" | "detect_clips" | "render_clip" | "purge_files";
  status: JobStatus;
  stage: string | null;
  progress: number;
  message: string | null;
  error_message: string | null;
  cancel_requested: boolean;
  worker_id?: string | null;
  attempts?: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

// -------------------------------------------------------------- projects
export type AspectRatio = "9:16" | "4:5" | "1:1" | "16:9";

export type ProjectStatus =
  | "awaiting_upload"
  | "importing"
  | "uploaded"
  | "queued"
  | "transcribing"
  | "transcribed"
  | "analyzing"
  | "ready"
  | "failed";

/** Where a project's files live: on the API server, or on the owner's paired worker (hybrid mode). */
export type MediaHost = "server" | "worker";

export type SourceMeta = {
  video_id?: string;
  url?: string;
  title?: string;
  author_name?: string;
  author_url?: string;
  thumbnail_url?: string;
  source_removed_at?: string;
};

export type Project = {
  id: string;
  name: string;
  status: ProjectStatus;
  source_type: "upload" | "url" | "youtube";
  source_url: string | null;
  source_meta: SourceMeta;
  worker_id: string | null;
  media_host: MediaHost;
  original_filename: string | null;
  media_size_bytes: number | null;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  language: string;
  whisper_model: string;
  clip_count: number;
  aspect_ratio: AspectRatio;
  min_clip_seconds: number;
  max_clip_seconds: number;
  auto_process: boolean;
  ai_provider: string | null;
  ai_model: string | null;
  error_message: string | null;
  has_media: boolean;
  media_url: string | null;
  thumbnail_url: string | null;
  has_transcript: boolean;
  clips: { total: number; ready: number };
  active_job: Job | null;
  created_at: string;
  updated_at: string;
};

export type ProjectList = { items: Project[]; total: number };

export type ProcessingOptions = {
  language: string;
  whisper_model?: string | null;
  clip_count: number;
  min_clip_seconds: number;
  max_clip_seconds: number;
  auto_process: boolean;
  aspect_ratio: AspectRatio;
};

export type YouTubeVideo = {
  video_id: string;
  url: string;
  title: string | null;
  author_name: string | null;
  author_url: string | null;
  thumbnail_url: string | null;
  notice: string | null;
  how_to_get_the_file: string;
};

// ------------------------------------------------------------ transcript
export type Word = { start: number; end: number; text: string; probability: number | null };
export type Segment = { id: number; start: number; end: number; text: string; words: Word[] };

export type Transcript = {
  project_id: string;
  language: string;
  language_probability: number | null;
  model: string;
  device: string;
  duration: number;
  word_count: number;
  warnings: string[];
  segments: Segment[];
  created_at: string;
};

// ----------------------------------------------------------------- clips
export type ClipLayout = "crop" | "fit";

export type CaptionStyle = {
  font: "Montserrat" | "Anton" | "Poppins";
  font_size: number;
  text_color: string;
  highlight_color: string;
  outline_color: string;
  outline_width: number;
  background: boolean;
  background_color: string;
  position: "bottom" | "middle" | "top";
  uppercase: boolean;
  highlight_words: boolean;
  words_per_line: number;
};

export type Clip = {
  id: string;
  project_id: string;
  project_name: string | null;
  rank: number;
  title: string;
  description: string;
  reason: string;
  score: number | null;
  source: "ai" | "manual";
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  suggested_start: number | null;
  suggested_end: number | null;
  status: "suggested" | "rendering" | "ready" | "failed";
  layout: ClipLayout;
  crop_position: number;
  auto_frame: boolean;
  aspect_ratio: AspectRatio;
  aspect_ratio_overridden: boolean;
  worker_id: string | null;
  media_host: MediaHost;
  captions_enabled: boolean;
  caption_style: CaptionStyle;
  has_caption_edits: boolean;
  output_size_bytes: number | null;
  rendered_at: string | null;
  error_message: string | null;
  preview_url: string | null;
  download_url: string | null;
  thumbnail_url: string | null;
  active_job: Job | null;
  created_at: string;
  updated_at: string;
};

export type ClipList = { items: Clip[]; total: number };
export type CaptionLine = { start: number; end: number; text: string };
export type ClipCaptions = { clip_id: string; edited: boolean; lines: CaptionLine[] };

export type ClipUpdate = Partial<{
  title: string;
  description: string;
  start_seconds: number;
  end_seconds: number;
  layout: ClipLayout;
  crop_position: number;
  auto_frame: boolean;
  aspect_ratio: AspectRatio;
  captions_enabled: boolean;
  caption_style: CaptionStyle;
  caption_lines: CaptionLine[];
}>;

// ------------------------------------------------------------- dashboard
export type Dashboard = {
  stats: {
    projects: number;
    processing: number;
    clips_ready: number;
    storage_used_bytes: number;
    storage_quota_bytes: number | null;
  };
  recent_projects: Project[];
  active_jobs: Array<Job & { project_name: string | null }>;
  recent_clips: Clip[];
};

// --------------------------------------------------------------- workers
export type WorkerCapabilities = {
  components?: Array<{ key: string; name: string; status: ComponentState; version: string | null; detail: string | null }>;
  ollama_models?: string[];
  ai_provider?: string | null;
  gpu?: string | null;
};

export type Worker = {
  id: string;
  name: string;
  platform: string;
  app_version: string;
  bridge_port: number;
  online: boolean;
  last_seen_at: string | null;
  created_at: string;
  capabilities: WorkerCapabilities;
  preferred_model: string | null;
  active_jobs: number;
};

export type PairingCode = { code: string; expires_at: string; server_url: string; command: string };

export type TransferToken = { token: string; scope: "read" | "upload"; expires_at: string; worker_id: string; bridge_port: number };

// -------------------------------------------------------------- settings
export type AIProvider = "ollama" | "external";

export type AISettings = {
  provider: AIProvider;
  ollama_base_url: string;
  ollama_model: string | null;
  external_configured: boolean;
  external_name: string;
  external_model: string | null;
  external_base_url_host: string | null;
  /** computer: this installation's setup (local mode). account: the user's own choice. */
  scope: "computer" | "account";
  /** Only in local mode: online, the endpoint is part of the server's configuration. */
  can_change_endpoint: boolean;
};

export type OllamaModel = { name: string; size_bytes: number | null; parameter_size: string | null; family: string | null };

export type AIStatus = {
  provider: AIProvider;
  ollama: {
    reachable: boolean;
    version: string | null;
    models: OllamaModel[];
    selected_model: string | null;
    selected_model_available: boolean;
    message: string | null;
  };
  external: { configured: boolean; name: string; model: string | null };
};
