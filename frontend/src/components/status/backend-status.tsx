"use client";

import { useCallback } from "react";
import { StatusDot } from "@/components/ui/badge";
import { errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { HealthResponse } from "@/lib/api/types";
import { usePolling } from "@/lib/hooks/use-polling";
import { cn } from "@/lib/cn";

type HealthWithLatency = HealthResponse & { latencyMs: number };

/** Polls GET /api/v1/health and returns live connection state. */
export function useBackendHealth(intervalMs = 10_000) {
  const fetcher = useCallback(async (signal: AbortSignal): Promise<HealthWithLatency> => {
    const started = performance.now();
    const health = await api.health(signal);
    return { ...health, latencyMs: Math.round(performance.now() - started) };
  }, []);
  return usePolling(fetcher, intervalMs);
}

/** Compact pill: "Backend online · v0.1.0" or "Backend offline". */
export function BackendStatusPill({ className }: { className?: string }) {
  const { data, error, loading, refresh } = useBackendHealth();
  const online = Boolean(data) && !error;
  const label = loading && !data ? "Checking backend…" : online ? "Backend online" : "Backend offline";
  const tone = loading && !data ? "neutral" : online ? "success" : "danger";
  const title = online
    ? `Connected · ${data?.latencyMs} ms · click to re-check`
    : error
      ? errorMessage(error)
      : "Checking the backend connection";

  return (
    <button
      type="button"
      onClick={refresh}
      title={title}
      className={cn(
        "inline-flex w-full items-center gap-2 rounded-xl border border-line bg-canvas px-3 py-2 text-left text-xs text-ink-soft transition-colors hover:bg-mist",
        className,
      )}
      aria-live="polite"
    >
      <StatusDot tone={tone} pulse={online} />
      <span className="font-medium">{label}</span>
      {online && data ? <span className="ml-auto font-mono text-subtle">v{data.version}</span> : null}
    </button>
  );
}
