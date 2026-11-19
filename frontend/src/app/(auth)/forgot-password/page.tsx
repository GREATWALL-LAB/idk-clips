"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/empty-state";
import { Field, Input } from "@/components/ui/form";
import { ApiError, errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import { routes } from "@/lib/routes";

const MIN_PASSWORD = 10;

/**
 * Password reset in two steps: ask for a code by email, then enter it with a new
 * password. The server checks the code with Supabase Auth and ends every session.
 */
export default function ForgotPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [wait, setWait] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (wait <= 0) return;
    const timer = window.setTimeout(() => setWait((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [wait]);

  async function requestCode(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const sent = await api.requestPasswordReset(email.trim());
      setWait(sent.resend_after_seconds);
      setNotice(`If ${email.trim()} belongs to a verified account, a reset code is on its way. It is valid for ${sent.code_ttl_minutes} minutes.`);
      setStep("code");
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) setWait(60);
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD;
  const mismatch = confirm.length > 0 && confirm !== password;

  async function resetPassword(event: FormEvent) {
    event.preventDefault();
    if (tooShort || mismatch) return;
    setBusy(true);
    setError(null);
    try {
      await api.confirmPasswordReset(email.trim(), code, password);
      router.replace(`${routes.login}?reset=1`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <span className="grid size-11 place-items-center rounded-2xl bg-brand-50 text-brand">
          <KeyRound className="size-5" aria-hidden="true" />
        </span>
        <h1 className="mt-4 font-display text-2xl font-bold text-ink">Reset your password</h1>
        <p className="mt-1 text-sm text-muted">
          {step === "email" ? "We will email you a code to confirm it is you." : "Enter the code from the email and choose a new password."}
        </p>
      </div>
      {notice && !error ? <Alert tone="info">{notice}</Alert> : null}
      {error ? <Alert>{error}</Alert> : null}

      {step === "email" ? (
        <form onSubmit={requestCode} className="space-y-5" noValidate>
          <Field label="Email" htmlFor="email">
            <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Button type="submit" variant="primary" className="w-full" loading={busy} disabled={!email.includes("@") || wait > 0}>
            {wait > 0 ? `Try again in ${wait}s` : "Email me a code"}
          </Button>
        </form>
      ) : (
        <form onSubmit={resetPassword} className="space-y-5" noValidate>
          <Field label="Reset code" htmlFor="code">
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
          <Field label="New password" htmlFor="password" hint={`At least ${MIN_PASSWORD} characters.`} error={tooShort ? `Use at least ${MIN_PASSWORD} characters.` : null}>
            <Input id="password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Field label="Confirm new password" htmlFor="confirm" error={mismatch ? "The passwords do not match." : null}>
            <Input id="confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          <Button type="submit" variant="primary" className="w-full" loading={busy} disabled={!/^[0-9]{6,10}$/.test(code) || !password || tooShort || mismatch}>
            Set new password
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={() => requestCode()} disabled={wait > 0 || busy}>
            {wait > 0 ? `Send a new code in ${wait}s` : "Send a new code"}
          </Button>
        </form>
      )}
      <p className="text-center text-sm text-muted">
        <Link href={routes.login} className="font-medium text-brand hover:text-brand-700">
          Back to log in
        </Link>
      </p>
    </div>
  );
}
