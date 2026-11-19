"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError } from "@/lib/api/client";
import { clearReadAccess } from "@/lib/api/bridge";
import { api } from "@/lib/api/endpoints";
import type { Meta, User } from "@/lib/api/types";

type AuthState =
  | { status: "loading"; user: null; error: null }
  | { status: "authenticated"; user: User; error: null }
  | { status: "anonymous"; user: null; error: null }
  | { status: "offline"; user: null; error: string };

type AuthContextValue = AuthState & {
  /** How this instance runs (local, server or hybrid). Null until the API answered. */
  meta: Meta | null;
  refresh: () => Promise<User | null>;
  setUser: (user: User) => void;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/** Accounts that still have to confirm their age or verify their email count as logged out. */
const NOT_YET_ALLOWED = new Set(["age_confirmation_required", "email_not_verified"]);

function stateFor(error: unknown): AuthState {
  if (error instanceof ApiError && error.status === 401) return { status: "anonymous", user: null, error: null };
  if (error instanceof ApiError && error.status === 403 && NOT_YET_ALLOWED.has(error.code)) {
    return { status: "anonymous", user: null, error: null };
  }
  return { status: "offline", user: null, error: error instanceof Error ? error.message : "Backend unavailable" };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading", user: null, error: null });
  const [meta, setMeta] = useState<Meta | null>(null);

  const load = useCallback(async (): Promise<User | null> => {
    try {
      const info = await api.meta();
      setMeta(info);
      // Local mode has one implicit user: /auth/me answers without a sign-in.
      const user = await api.me();
      setState({ status: "authenticated", user, error: null });
      return user;
    } catch (error) {
      setState(stateFor(error));
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const info = await api.meta();
        if (cancelled) return;
        setMeta(info);
        const user = await api.me();
        if (!cancelled) setState({ status: "authenticated", user, error: null });
      } catch (error) {
        if (!cancelled) setState(stateFor(error));
      }
    })();
    // Any API call that gets 401 (expired session) signs the UI out.
    const onUnauthorized = () => setState({ status: "anonymous", user: null, error: null });
    window.addEventListener("openclip:unauthorized", onUnauthorized);
    return () => {
      cancelled = true;
      window.removeEventListener("openclip:unauthorized", onUnauthorized);
    };
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      clearReadAccess();
      setState({ status: "anonymous", user: null, error: null });
    }
  }, []);

  const setUser = useCallback((user: User) => setState({ status: "authenticated", user, error: null }), []);

  const value = useMemo<AuthContextValue>(() => ({ ...state, meta, refresh: load, setUser, signOut }), [state, meta, load, setUser, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Like useAuth, but returns null outside an AuthProvider (static pages, tests). */
export function useOptionalAuth(): AuthContextValue | null {
  return useContext(AuthContext);
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}

/** Convenience: the run mode, defaulting to "server" while unknown. */
export function useMode() {
  const { meta } = useAuth();
  return {
    mode: meta?.mode ?? null,
    local: meta?.mode === "local",
    hybrid: meta?.mode === "hybrid",
    accounts: meta ? meta.accounts : true,
  };
}
