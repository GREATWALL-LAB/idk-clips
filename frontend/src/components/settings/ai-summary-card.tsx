"use client";

import Link from "next/link";
import { useCallback } from "react";
import { Cpu } from "lucide-react";
import { Badge, StatusDot } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/progress";
import { api } from "@/lib/api/endpoints";
import { usePolling } from "@/lib/hooks/use-polling";

/** Compact view of the AI configuration with a link to Settings. */
export function AISummaryCard() {
  const fetcher = useCallback((signal: AbortSignal) => api.aiStatus(signal), []);
  const { data, loading } = usePolling(fetcher, 30_000);
  const ollama = data?.ollama;
  const external = data?.provider === "external";

  return (
    <Card>
      <CardHeader
        icon={<Cpu className="size-4" />}
        title="AI configuration"
        action={
          <Link href="/settings/" className="text-sm font-semibold text-brand hover:text-brand-700">
            Settings
          </Link>
        }
      />
      <CardBody className="space-y-2 text-sm">
        {loading && !data ? (
          <Skeleton className="h-12" />
        ) : data ? (
          <>
            <div className="flex items-center justify-between gap-2">
              <span className="text-muted">Provider</span>
              <span className="font-medium text-ink">{external ? data.external.name : "Ollama (local)"}</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-muted">Model</span>
              <span className="truncate font-mono text-xs text-ink">
                {external ? data.external.model ?? "–" : ollama?.selected_model ?? "none installed"}
              </span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-muted">Status</span>
              {external ? (
                <Badge tone={data.external.configured ? "success" : "danger"}>
                  <StatusDot tone={data.external.configured ? "success" : "danger"} />
                  {data.external.configured ? "Configured" : "Not configured"}
                </Badge>
              ) : (
                <Badge tone={ollama?.reachable && ollama.selected_model_available ? "success" : "danger"}>
                  <StatusDot tone={ollama?.reachable && ollama.selected_model_available ? "success" : "danger"} />
                  {!ollama?.reachable ? "Ollama offline" : ollama.selected_model_available ? "Ready" : "No model"}
                </Badge>
              )}
            </div>
            {!external && ollama?.message ? <p className="pt-1 text-xs text-subtle">{ollama.message}</p> : null}
          </>
        ) : (
          <p className="text-subtle">AI status unavailable.</p>
        )}
      </CardBody>
    </Card>
  );
}
