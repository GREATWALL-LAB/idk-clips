"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import { cn } from "@/lib/cn";

type Toast = { id: number; tone: "success" | "error" | "info"; message: string };
type ToastApi = { success: (m: string) => void; error: (m: string) => void; info: (m: string) => void };

const ToastContext = createContext<ToastApi | null>(null);
let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => setToasts((all) => all.filter((t) => t.id !== id)), []);
  const push = useCallback(
    (tone: Toast["tone"], message: string) => {
      const id = nextId++;
      setToasts((all) => [...all.slice(-3), { id, tone, message }]);
      setTimeout(() => dismiss(id), tone === "error" ? 8000 : 4500);
    },
    [dismiss],
  );
  const api = useMemo<ToastApi>(
    () => ({
      success: (m) => push("success", m),
      error: (m) => push("error", m),
      info: (m) => push("info", m),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role={toast.tone === "error" ? "alert" : "status"}
            className={cn(
              "pointer-events-auto flex animate-fade-up items-start gap-3 rounded-2xl border bg-surface p-3.5 text-sm shadow-lift",
              toast.tone === "error" ? "border-danger/25" : toast.tone === "success" ? "border-success/25" : "border-line",
            )}
          >
            {toast.tone === "error" ? (
              <CircleAlert className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden="true" />
            ) : toast.tone === "success" ? (
              <CircleCheck className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
            ) : (
              <Info className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" />
            )}
            <p className="flex-1 text-ink">{toast.message}</p>
            <button type="button" onClick={() => dismiss(toast.id)} className="text-subtle hover:text-ink" aria-label="Dismiss">
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside <ToastProvider>");
  return context;
}
