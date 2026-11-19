"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { UserPlus } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/empty-state";
import { Field, Input } from "@/components/ui/form";
import { Spinner } from "@/components/ui/progress";
import { errorMessage } from "@/lib/api/client";
import { AgeBlocked, AgeGate, ageDeclined } from "@/components/auth/age-gate";
import { api } from "@/lib/api/endpoints";
import { routes } from "@/lib/routes";
import type { AuthStatus } from "@/lib/api/types";

const MIN_PASSWORD = 10;

export default function RegisterPage() {
  const auth = useAuth();
  const router = useRouter();
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The 18+ answer: null until the person answers. A No (this session) blocks sign-up.
  const [ageConfirmed, setAgeConfirmed] = useState(false);
  const [declined] = useState(() => typeof window !== "undefined" && ageDeclined());

  useEffect(() => {
    if (auth.status === "authenticated" || auth.meta?.accounts === false) router.replace("/dashboard/");
  }, [auth.status, auth.meta, router]);

  useEffect(() => {
    api.authStatus().then(setStatus).catch((err) => setError(errorMessage(err)));
  }, []);

  const mismatch = confirm.length > 0 && confirm !== password;
  const tooShort = password.length > 0 && password.length < MIN_PASSWORD;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (mismatch || tooShort) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.register(email, password, name, ageConfirmed);
      if (result.verification_required) {
        // No session yet: the emailed code proves the address first.
        router.push(`${routes.verify(result.user.email)}${result.code_sent ? "&sent=1" : ""}`);
        return;
      }
      auth.setUser(await api.me());
      // New accounts land on the dashboard's first-run steps (first project, worker pairing).
      router.replace("/dashboard/");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (!status && !error) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    );
  }

  if (status && !status.registration_open) {
    return (
      <div className="space-y-4 text-center">
        <h1 className="text-xl font-semibold text-ink">Sign-ups are closed</h1>
        <p className="text-sm text-muted">
          {status.email_verification
            ? "New accounts cannot be created right now because email verification is not set up on this server yet."
            : "This server is not accepting new accounts at the moment."}
        </p>
        <Link href="/login/" className="inline-block text-sm font-medium text-brand hover:text-brand-700">
          Back to log in
        </Link>
      </div>
    );
  }

  if (declined) return <AgeBlocked />;
  if (!ageConfirmed) return <AgeGate title="Create your account" onConfirm={() => setAgeConfirmed(true)} />;

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      <div>
        <h1 className="font-display text-2xl font-bold text-ink">Create your account</h1>
        <p className="mt-1 text-sm text-muted">
          Free, with no subscription. Your projects and clips are private to your account.
          {status?.email_verification ? " We will email you a code to confirm your address." : ""}
        </p>
      </div>
      {error ? <Alert>{error}</Alert> : null}
      <Field label="Name" htmlFor="name">
        <Input id="name" autoComplete="name" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Email" htmlFor="email">
        <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label="Password" htmlFor="password" hint={`At least ${MIN_PASSWORD} characters.`} error={tooShort ? `Use at least ${MIN_PASSWORD} characters.` : null}>
        <Input id="password" type="password" autoComplete="new-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <Field label="Confirm password" htmlFor="confirm" error={mismatch ? "The passwords do not match." : null}>
        <Input id="confirm" type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </Field>
      <Button type="submit" variant="primary" className="w-full" loading={submitting} disabled={mismatch || tooShort || !email || !password} icon={<UserPlus className="size-4" aria-hidden="true" />}>
        Create account
      </Button>
      <p className="text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login/" className="font-medium text-brand hover:text-brand-700">
          Log in
        </Link>
      </p>
    </form>
  );
}
