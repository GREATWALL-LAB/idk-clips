"use client";

import { useEffect, useState } from "react";
import { Check, Copy, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert } from "@/components/ui/empty-state";
import { Spinner } from "@/components/ui/progress";
import { errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { PairingCode } from "@/lib/api/types";

function CommandLine({ label, text }: { label: string; text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-subtle">{label}</p>
      <div className="flex items-start gap-2 rounded-xl bg-ink p-3">
        <code className="min-w-0 flex-1 break-all font-mono text-[12.5px] leading-relaxed text-white">{text}</code>
        <button
          type="button"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(text);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            } catch {
              setCopied(false);
            }
          }}
          className="grid size-7 shrink-0 place-items-center rounded-lg text-white/70 hover:bg-white/10 hover:text-white"
          aria-label={`Copy: ${label}`}
        >
          {copied ? <Check className="size-4 text-lime" aria-hidden="true" /> : <Copy className="size-4" aria-hidden="true" />}
        </button>
      </div>
    </div>
  );
}

export function secondsLeft(expiresAt: string, now: number): number {
  return Math.max(0, Math.floor((new Date(expiresAt).getTime() - now) / 1000));
}

/** Creates a one-time pairing code and shows the exact command to run on the user's computer. */
export function PairingDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  // The dialog is mounted when it opens, so the first code is requested right away.
  const [code, setCode] = useState<PairingCode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(() => Date.now());

  function request() {
    api
      .createPairingCode()
      .then((created) => {
        setCode(created);
        setNow(Date.now());
      })
      .catch((err: unknown) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }

  function create() {
    setLoading(true);
    setError(null);
    request();
  }

  useEffect(() => {
    request();
  }, []);

  useEffect(() => {
    if (!code) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [code]);

  const left = code ? secondsLeft(code.expires_at, now) : 0;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      wide
      title="Connect a worker"
      description="A worker is IDK Clips running on your own computer. It does the video processing for your account, so your videos never have to be uploaded to our servers."
      footer={
        <Button variant="primary" onClick={onClose}>
          Done
        </Button>
      }
    >
      <ol className="space-y-5 text-sm text-ink-soft">
        <li>
          <p className="font-semibold text-ink">1. Install IDK Clips on that computer</p>
          <p className="mt-1">
            Follow the installation guide in the documentation (Python, FFmpeg and optionally Ollama). Run the requirements check with{" "}
            <code className="rounded bg-mist px-1.5 py-0.5 font-mono text-[12px] text-ink">worker doctor</code>.
          </p>
        </li>
        <li>
          <p className="font-semibold text-ink">2. Pair it with this one-time code</p>
          {loading && !code ? (
            <p className="mt-2 flex items-center gap-2 text-subtle">
              <Spinner /> Creating a code…
            </p>
          ) : error ? (
            <Alert className="mt-2">{error}</Alert>
          ) : code ? (
            <div className="mt-3 space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <span className="rounded-2xl bg-lime px-4 py-2 font-mono text-2xl font-bold tracking-[0.18em] text-ink" aria-label={`Pairing code ${code.code}`}>
                  {code.code}
                </span>
                <span className="text-xs text-subtle" aria-live="polite">
                  {left > 0 ? `Valid for ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")} · works once` : "This code has expired."}
                </span>
                {left === 0 ? (
                  <Button size="sm" onClick={create} icon={<RefreshCw className="size-3.5" aria-hidden="true" />}>
                    New code
                  </Button>
                ) : null}
              </div>
              <CommandLine label="Windows (from the IDK Clips folder)" text={`scripts\\windows\\worker.cmd ${code.command}`} />
              <CommandLine label="Linux or macOS" text={`scripts/linux/worker.sh ${code.command}`} />
            </div>
          ) : null}
        </li>
        <li>
          <p className="font-semibold text-ink">3. Start it</p>
          <p className="mt-1">
            Run <code className="rounded bg-mist px-1.5 py-0.5 font-mono text-[12px] text-ink">worker run</code> and keep it open while you work. It connects
            out to this website; no ports need to be opened. You can disconnect it here at any time.
          </p>
        </li>
      </ol>
    </Dialog>
  );
}
