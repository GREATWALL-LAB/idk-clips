"use client";

import { useCallback, useEffect, useState } from "react";
import { probeBridge } from "@/lib/api/bridge";
import { errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { Worker } from "@/lib/api/types";

export type LocalWorkerState = {
  loading: boolean;
  workers: Worker[];
  /** An online worker whose bridge answers on this computer (where uploads go). */
  local: Worker | null;
  error: string | null;
  refresh: () => void;
};

/** Hybrid mode: find the user's worker that runs on the same computer as this browser. */
export function useLocalWorker(enabled: boolean): LocalWorkerState {
  const [state, setState] = useState<Omit<LocalWorkerState, "refresh">>({ loading: enabled, workers: [], local: null, error: null });
  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    (async () => {
      try {
        const workers = await api.workers();
        let local: Worker | null = null;
        for (const worker of workers.filter((w) => w.online)) {
          if (await probeBridge(worker.bridge_port, worker.id)) {
            local = worker;
            break;
          }
        }
        if (!cancelled) setState({ loading: false, workers, local, error: null });
      } catch (error) {
        if (!cancelled) setState({ loading: false, workers: [], local: null, error: errorMessage(error) });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [enabled, tick]);

  return { ...state, loading: enabled && state.loading, refresh };
}
