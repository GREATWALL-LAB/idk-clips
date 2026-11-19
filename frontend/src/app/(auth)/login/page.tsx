"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { LogIn } from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/empty-state";
import { Field, Input } from "@/components/ui/form";
import { ApiError, errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import { API_URL } from "@/lib/config";
import { routes } from "@/lib/routes";
import { safeNextPath } from "@/lib/safe-redirect";
import { AgeGate } from "@/components/auth/age-gate";

const COOKIE_BLOCKED =
  "Logged in, but your browser did not keep the session cookie. The app and the API must be on the same site " +
  `(${API_URL || "this address"}), for example http://localhost:3000 with an API on http://localhost:8000.`;

function LoginForm() {
  const auth = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNextPath(params.get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [registrationOpen, setRegistrationOpen] = useState(false);
  // Older accounts that never answered the 18+ question are asked once, here.
  const [askAge, setAskAge] = useState(false);

  useEffect(() => {
    // Local mode has no accounts: everyone on this computer goes straight in.
    if (auth.status === "authenticated" || auth.meta?.accounts === false) router.replace(next);
  }, [auth.status, auth.meta, next, router]);

  useEffect(() => {
    api
      .authStatus()
      .then((status) => setRegistrationOpen(status.registration_open))
      .catch(() => undefined);
  }, []);

  async function logIn(ageConfirmed: boolean) {
    setSubmitting(true);
    setError(null);
    try {
      await api.login(email, password, ageConfirmed);
      try {
        auth.setUser(await api.me());
      } catch (verifyError) {
        if (verifyError instanceof ApiError && verifyError.status === 401) {
          setError(COOKIE_BLOCKED);
          return;
        }
        throw verifyError;
      }
      router.replace(next);
    } catch (err) {
      if (err instanceof ApiError && err.code === "age_confirmation_required") {
        setAskAge(true);
        return;
      }
      if (err instanceof ApiError && err.code === "email_not_verified") {
        router.push(`${routes.verify(email.trim())}&sent=1`);
        return;
      }
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await logIn(false);
  }

  if (askAge) {
    return (
      <AgeGate
        title="One more question"
        onConfirm={() => {
          setAskAge(false);
          void logIn(true);
        }}
      />
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      <div>
        <h1 className="font-display text-2xl font-bold text-ink">Log in</h1>
        <p className="mt-1 text-sm text-muted">Welcome back to IDK Clips.</p>
      </div>
      {params.get("reset") === "1" && !error ? <Alert tone="success">Password changed. Log in with your new password.</Alert> : null}
      {error ? <Alert>{error}</Alert> : null}
      <Field label="Email" htmlFor="email">
        <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field
        label="Password"
        htmlFor="password"
        hint={
          <Link href={routes.forgotPassword} className="font-medium text-brand hover:text-brand-700">
            Forgot password?
          </Link>
        }
      >
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      <Button type="submit" variant="primary" className="w-full" loading={submitting} icon={<LogIn className="size-4" aria-hidden="true" />}>
        Log in
      </Button>
      {registrationOpen ? (
        <p className="text-center text-sm text-muted">
          No account yet?{" "}
          <Link href="/register/" className="font-medium text-brand hover:text-brand-700">
            Create account
          </Link>
        </p>
      ) : null}
    </form>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
