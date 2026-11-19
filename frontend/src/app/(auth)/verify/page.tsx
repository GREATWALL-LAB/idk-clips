"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { MailCheck } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/empty-state";
import { Field, Input } from "@/components/ui/form";
import { ApiError, errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import { routes } from "@/lib/routes";

const RESEND_SECONDS = 60;

function retryAfter(error: unknown): number | null {
  if (error instanceof ApiError && error.status === 429) {
    const match = /(\d+)\s*seconds?/.exec(error.message);
    return match ? Number(match[1]) : RESEND_SECONDS;
  }
  return null;
}

/**
 * Enter the one-time code from the verification email. The server checks the code with
 * Supabase Auth; nothing here decides whether an address is verified.
 */
function VerifyForm() {
  const auth = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const email = (params.get("email") ?? "").trim().toLowerCase();
  const [code, setCode] = useState("");
  const [wait, setWait] = useState(params.get("sent") === "1" ? RESEND_SECONDS : 0);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(params.get("sent") === "1" ? `We sent a code to ${email}.` : null);

  useEffect(() => {
    if (wait <= 0) return;
    const timer = window.setTimeout(() => setWait((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [wait]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      auth.setUser(await api.verifyEmail(email, code));
      router.replace(routes.dashboard);
    } catch (err) {
      setError(errorMessage(err));
      if (err instanceof ApiError && (err.code === "too_many_attempts" || err.code === "code_expired")) setCode("");
    } finally {
      setSubmitting(false);
    }
  }

  async function resend() {
    setResending(true);
    setError(null);
    try {
      const sent = await api.resendCode(email);
      setWait(sent.resend_after_seconds || RESEND_SECONDS);
      setNotice(`If ${email} has an account waiting for verification, a new code is on its way. It is valid for ${sent.code_ttl_minutes} minutes.`);
    } catch (err) {
      const seconds = retryAfter(err);
      if (seconds) setWait(seconds);
      setError(errorMessage(err));
    } finally {
      setResending(false);
    }
  }

  if (!email) {
    return (
      <div className="space-y-4 text-center">
        <h1 className="font-display text-2xl font-bold text-ink">Verify your email</h1>
        <p className="text-sm text-muted">Open the link from the sign-up page, or log in again to get a new code.</p>
        <Link href={routes.login} className="inline-block text-sm font-medium text-brand hover:text-brand-700">
          Go to log in
        </Link>
      </div>
    );
  }

  const valid = /^[0-9]{6,10}$/.test(code);
  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      <div>
        <span className="grid size-11 place-items-center rounded-2xl bg-brand-50 text-brand">
          <MailCheck className="size-5" aria-hidden="true" />
        </span>
        <h1 className="mt-4 font-display text-2xl font-bold text-ink">Check your email</h1>
        <p className="mt-1 text-sm text-muted">
          Enter the code we sent to <span className="font-medium text-ink">{email}</span>. Your account works once the address is verified.
        </p>
      </div>
      {notice && !error ? <Alert tone="info">{notice}</Alert> : null}
      {error ? <Alert>{error}</Alert> : null}
      <Field label="Verification code" htmlFor="code" hint="The code is valid for a limited time. Check your spam folder if you do not see the email.">
        <Input
          id="code"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={10}
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          className="text-center font-mono text-lg tracking-[0.3em]"
        />
      </Field>
      <Button type="submit" variant="primary" className="w-full" loading={submitting} disabled={!valid}>
        Verify and continue
      </Button>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <Button type="button" variant="ghost" size="sm" onClick={resend} loading={resending} disabled={wait > 0}>
          {wait > 0 ? `Send a new code in ${wait}s` : "Send a new code"}
        </Button>
        <Link href={routes.login} className="font-medium text-brand hover:text-brand-700">
          Back to log in
        </Link>
      </div>
    </form>
  );
}

export default function VerifyPage() {
  return (
    <Suspense>
      <VerifyForm />
    </Suspense>
  );
}
