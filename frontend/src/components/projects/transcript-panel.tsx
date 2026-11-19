"use client";

import { useCallback, useMemo, useState } from "react";
import { Download, Search, TriangleAlert } from "lucide-react";
import { Alert } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/progress";
import { apiUrl, errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import { usePolling } from "@/lib/hooks/use-polling";

export function TranscriptPanel({
  projectId,
  version,
  currentTime,
  onSeek,
}: {
  projectId: string;
  version: string;
  currentTime: number;
  onSeek: (seconds: number) => void;
}) {
  const fetcher = useCallback((signal: AbortSignal) => api.transcript(projectId, signal), [projectId]);
  const { data, error, loading } = usePolling(fetcher, null, version);
  const [query, setQuery] = useState("");

  const segments = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.segments ?? []).filter((s) => !q || s.text.toLowerCase().includes(q));
  }, [data, query]);

  if (loading && !data) return <Skeleton className="h-80" />;
  if (error && !data) return <Alert>{errorMessage(error)}</Alert>;
  if (!data) return null;

  const download = (format: string) => apiUrl(`/projects/${projectId}/transcript/download?format=${format}`);

  return (
    <div className="space-y-4">
      {data.warnings.map((warning) => (
        <Alert key={warning} tone="warning">
          <span className="inline-flex items-start gap-2">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {warning}
          </span>
        </Alert>
      ))}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-subtle">
          {data.word_count.toLocaleString()} words · language <span className="text-ink-soft">{data.language}</span>
          {data.language_probability != null ? ` (${Math.round(data.language_probability * 100)}%)` : ""} · model{" "}
          <span className="text-ink-soft">{data.model}</span> on {data.device.toUpperCase()}
        </p>
        <div className="flex gap-1.5">
          {["txt", "srt", "vtt"].map((format) => (
            <a
              key={format}
              href={download(format)}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line px-2.5 text-xs font-medium text-ink-soft transition-colors hover:bg-mist hover:text-ink"
            >
              <Download className="size-3.5" aria-hidden="true" />
              {format.toUpperCase()}
            </a>
          ))}
        </div>
      </div>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle" aria-hidden="true" />
        <Input aria-label="Search the transcript" placeholder="Search the transcript" className="pl-9" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      {segments.length === 0 ? (
        <p className="py-6 text-center text-sm text-subtle">{data.segments.length ? "No matches." : "No speech was detected."}</p>
      ) : (
        <ol className="max-h-[560px] space-y-1 overflow-y-auto pr-1">
          {segments.map((segment) => {
            const active = currentTime >= segment.start && currentTime < segment.end;
            return (
              <li key={segment.id}>
                <button
                  type="button"
                  onClick={() => onSeek(segment.start)}
                  className={cn(
                    "flex w-full gap-3 rounded-xl px-3 py-2 text-left text-sm transition-colors",
                    active ? "bg-brand-50 text-ink" : "text-ink-soft hover:bg-mist",
                  )}
                  aria-current={active ? "true" : undefined}
                >
                  <span className={cn("w-12 shrink-0 pt-px font-mono text-xs", active ? "text-brand" : "text-subtle")}>
                    {formatDuration(segment.start)}
                  </span>
                  <span className="leading-relaxed">{segment.text}</span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
