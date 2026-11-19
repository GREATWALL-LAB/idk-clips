"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type PollingState<T> = {
  data: T | undefined;
  error: unknown;
  loading: boolean;
  lastUpdated: number | null;
  refresh: () => void;
};

/** A fixed interval, `null` for "fetch once", or a function of the latest data (adaptive polling). */
export type PollInterval<T> = number | null | ((data: T) => number | null);

/**
 * Run `fetcher` now and then again after each interval while the tab is visible.
 * Requests are aborted on unmount. Pass a stable `interval` (a module-level function
 * or a number) to avoid restarting the loop on every render.
 */
export function usePolling<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  interval: PollInterval<T>,
  key: unknown = null,
): PollingState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [tick, setTick] = useState(0);
  const fetcherRef = useRef(fetcher);
  const intervalRef = useRef(interval);

  useEffect(() => {
    fetcherRef.current = fetcher;
    intervalRef.current = interval;
  }, [fetcher, interval]);

  const refresh = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    let latest: T | undefined;

    const nextDelay = (): number | null => {
      const current = intervalRef.current;
      if (typeof current === "function") return latest === undefined ? 10_000 : current(latest);
      return current;
    };

    const run = async () => {
      try {
        const result = await fetcherRef.current(controller.signal);
        if (stopped) return;
        latest = result;
        setData(result);
        setError(null);
        setLastUpdated(Date.now());
      } catch (err) {
        if (stopped || controller.signal.aborted) return;
        setError(err);
      } finally {
        if (!stopped) setLoading(false);
      }
      const delay = nextDelay();
      if (!stopped && delay !== null) timer = setTimeout(schedule, delay);
    };

    const schedule = () => {
      if (stopped) return;
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        timer = setTimeout(schedule, 5_000); // check again later instead of polling a hidden tab
        return;
      }
      void run();
    };

    void run();
    return () => {
      stopped = true;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [key, tick]);

  return { data, error, loading, lastUpdated, refresh };
}
