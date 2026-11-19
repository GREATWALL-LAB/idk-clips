"use client";

import { useCallback } from "react";
import { Activity, CircleAlert, CircleCheck, RefreshCw, TriangleAlert } from "lucide-react";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { ComponentState } from "@/lib/api/types";
import { usePolling } from "@/lib/hooks/use-polling";
import { useBackendHealth } from "@/components/status/backend-status";

const stateTone: Record<ComponentState, Tone> = {
  ok: "success",
  unavailable: "danger",
  misconfigured: "warning",
  not_configured: "neutral",
};

const stateLabel: Record<ComponentState, string> = {
  ok: "Ready",
  unavailable: "Not found",
  misconfigured: "Check setup",
  not_configured: "Not configured",
};

function StateIcon({ state }: { state: ComponentState }) {
  if (state === "ok") return <CircleCheck className="size-4 text-success" aria-hidden="true" />;
  if (state === "misconfigured")
    return <TriangleAlert className="size-4 text-warning" aria-hidden="true" />;
  return <CircleAlert className="size-4 text-danger" aria-hidden="true" />;
}

/** Backend connection plus FFmpeg / Ollama availability, with fix-it hints. */
export function SystemStatusPanel() {
  const health = useBackendHealth(10_000);
  const fetcher = useCallback((signal: AbortSignal) => api.systemStatus(signal), []);
  const status = usePolling(fetcher, 15_000, health.data ? "online" : "offline");

  const backendOnline = Boolean(health.data) && !health.error;

  return (
    <Card>
      <CardHeader
        icon={<Activity className="size-4" />}
        title="System status"
        description="What IDK Clips needs on this machine."
        action={
          <Button
            size="sm"
            variant="ghost"
            icon={<RefreshCw className="size-3.5" aria-hidden="true" />}
            onClick={() => {
              health.refresh();
              status.refresh();
            }}
          >
            Re-check
          </Button>
        }
      />
      <CardBody>
        <ul className="divide-y divide-line" aria-live="polite">
          <li className="flex items-start gap-3 py-3 first:pt-0">
            <span className="mt-0.5">
              <StateIcon state={backendOnline ? "ok" : "unavailable"} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-ink">Backend API</span>
                <Badge tone={backendOnline ? "success" : "danger"}>
                  {health.loading && !health.data ? "Checking…" : backendOnline ? "Online" : "Offline"}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-muted">
                {backendOnline && health.data
                  ? `Version ${health.data.version} · ${health.data.environment} · ${health.data.latencyMs} ms`
                  : health.error
                    ? errorMessage(health.error)
                    : "Connecting…"}
              </p>
              {!backendOnline && health.error ? (
                <p className="mt-1 text-xs text-subtle">
                  Start it with <code className="font-mono text-ink-soft">scripts\windows\start-backend.cmd</code>.
                </p>
              ) : null}
            </div>
          </li>

          {backendOnline && status.data
            ? status.data.components.map((component) => (
                <li key={component.key} className="flex items-start gap-3 py-3 last:pb-0">
                  <span className="mt-0.5">
                    <StateIcon state={component.status} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-ink">{component.name}</span>
                      <Badge tone={stateTone[component.status]}>{stateLabel[component.status]}</Badge>
                      {!component.required ? <Badge>Optional</Badge> : null}
                    </div>
                    <p className="mt-1 text-xs text-muted">
                      {component.status === "ok"
                        ? [component.version && `Version ${component.version}`, component.source, component.detail]
                            .filter(Boolean)
                            .join(" · ")
                        : component.detail}
                    </p>
                    {component.hint ? <p className="mt-1 text-xs text-subtle">{component.hint}</p> : null}
                  </div>
                </li>
              ))
            : null}

          {backendOnline && status.error ? (
            <li className="py-3 text-xs text-danger">{errorMessage(status.error)}</li>
          ) : null}
        </ul>
      </CardBody>
    </Card>
  );
}
