"use client";

import Link from "next/link";
import { useState } from "react";
import { ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";

const DECLINED_KEY = "idk-clips:age-declined";

/** True when this browser already answered No (kept for the browser session). */
export function ageDeclined(): boolean {
  try {
    return window.sessionStorage.getItem(DECLINED_KEY) === "1";
  } catch {
    return false;
  }
}

function rememberDeclined(): void {
  try {
    window.sessionStorage.setItem(DECLINED_KEY, "1");
  } catch {
    // Storage can be unavailable (private mode); the server refuses the account anyway.
  }
}

/** Shown instead of the form after a No: no account and no access. */
export function AgeBlocked() {
  return (
    <div className="space-y-4 text-center" role="alert">
      <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-danger-50 text-danger">
        <ShieldAlert className="size-6" aria-hidden="true" />
      </span>
      <h1 className="font-display text-2xl font-bold text-ink">You must be 18 or older</h1>
      <p className="text-sm text-muted">IDK Clips accounts are only for people who are 18 years of age or older, so we cannot create or open an account for you.</p>
      <Link href={routes.home} className="inline-block text-sm font-medium text-brand hover:text-brand-700">
        Back to the homepage
      </Link>
    </div>
  );
}

/**
 * "Are you 18 years of age or older?" with explicit Yes and No answers. Nothing is
 * pre-selected and nothing is assumed: the caller gets `true` only for an actual Yes.
 * The server checks the answer too; this screen is not the only safeguard.
 */
export function AgeGate({ onConfirm, title = "Before you start" }: { onConfirm: () => void; title?: string }) {
  const [declined, setDeclined] = useState(false);
  if (declined) return <AgeBlocked />;
  return (
    <div className="space-y-6" data-testid="age-gate">
      <div>
        <h1 className="font-display text-2xl font-bold text-ink">{title}</h1>
        <p id="age-question" className="mt-3 text-lg font-semibold text-ink">
          Are you 18 years of age or older?
        </p>
        <p className="mt-1 text-sm text-muted">You need to be at least 18 to create or use an IDK Clips account. We only store your answer and when you gave it.</p>
      </div>
      <div className="grid grid-cols-2 gap-3" role="group" aria-labelledby="age-question">
        <Button variant="primary" className="w-full" onClick={onConfirm}>
          Yes, I am 18 or older
        </Button>
        <Button
          variant="secondary"
          className="w-full"
          onClick={() => {
            rememberDeclined();
            setDeclined(true);
          }}
        >
          No
        </Button>
      </div>
    </div>
  );
}
