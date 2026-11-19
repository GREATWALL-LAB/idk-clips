/** Formatting helpers shared by the UI. */

export function formatDuration(totalSeconds: number | null | undefined): string {
  if (totalSeconds == null || !Number.isFinite(totalSeconds)) return "–";
  const seconds = Math.max(0, Math.round(totalSeconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}

/** 83.456 -> "1:23.4" (for precise clip boundaries). */
export function formatTimestamp(totalSeconds: number): string {
  const safe = Math.max(0, totalSeconds);
  const m = Math.floor(safe / 60);
  const s = safe - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "–";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatRelative(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86_400) return `${Math.floor(diff / 3600)} h ago`;
  if (diff < 7 * 86_400) return `${Math.floor(diff / 86_400)} d ago`;
  return new Date(iso).toLocaleDateString();
}

/** Parse "83.5", "1:23.5" or "1:02:03.5" into seconds. Returns null when invalid. */
export function parseTimestamp(text: string): number | null {
  const parts = text.trim().split(":");
  if (parts.length === 0 || parts.length > 3 || parts.some((p) => p === "" || !/^\d+(\.\d+)?$/.test(p))) return null;
  return parts.reduce((total, part) => total * 60 + Number(part), 0);
}

export function percent(fraction: number): string {
  return `${Math.round(Math.max(0, Math.min(1, fraction)) * 100)}%`;
}
