"use client";

import Link from "next/link";
import { useCallback } from "react";
import { Cpu } from "lucide-react";
import { Badge, StatusDot } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/progress";
import { api } from "@/lib/api/endpoints";
import { usePolling } from "@/lib/hooks/use-polling";
import { routes } from "@/lib/routes";

/** Dashboard card for hybrid mode: are the user's own computers connected? */
export function WorkerSummaryCard() {
  const fetcher = useCallback((signal: AbortSignal) => api.workers(signal), []);
  const { data, loading } = usePolling(fetcher, 15_000);
  const online = data?.filter((w) => w.online) ?? [];
  return (
    <Card>
      <CardHeader
        icon={<Cpu className="size-4" />}
        title="Your workers"
        description="Your videos are processed on these computers."
        action={
          <Link href={routes.workers} className="text-sm font-semibold text-brand hover:text-brand-700">
            Manage
          </Link>
        }
      />
      <CardBody className="space-y-3 text-sm">
        {loading && !data ? (
          <Skeleton className="h-12" />
        ) : !data || data.length === 0 ? (
          <>
            <p className="text-muted">No computer is connected yet. Connect one to start processing.</p>
            <ButtonLink href={routes.workers} variant="primary" size="sm">
              Connect a worker
            </ButtonLink>
          </>
        ) : (
          <ul className="space-y-2">
            {data.map((worker) => (
              <li key={worker.id} className="flex items-center justify-between gap-2">
                <span className="truncate font-medium text-ink">{worker.name}</span>
                <Badge tone={worker.online ? "success" : "neutral"}>
                  <StatusDot tone={worker.online ? "success" : "neutral"} pulse={worker.online} />
                  {worker.online ? (worker.active_jobs ? `Working (${worker.active_jobs})` : "Online") : "Offline"}
                </Badge>
              </li>
            ))}
          </ul>
        )}
        {data && data.length > 0 && online.length === 0 ? (
          <p className="text-xs text-subtle">Jobs wait safely in the queue until one of your workers is online.</p>
        ) : null}
      </CardBody>
    </Card>
  );
}
