import type { Meta } from "@/lib/api/types";
import { routes } from "@/lib/routes";

export type HeaderAction = {
  key: "login" | "register" | "dashboard";
  href: string;
  label: string;
  variant: "primary" | "secondary";
};

type AuthStatusName = "loading" | "authenticated" | "anonymous" | "offline";

/**
 * The account buttons in the public site header.
 *
 * - Signed in: one "Dashboard" button.
 * - Local mode (no accounts, this computer only): one "Open app" button.
 * - Otherwise "Log in" and, while the server accepts sign-ups, "Create account".
 *   Before the API has answered (or when it cannot be reached) both are shown, so the
 *   static page never hides the way in.
 */
export function headerActions(status: AuthStatusName | null, meta: Meta | null): HeaderAction[] {
  if (meta?.accounts === false) {
    return [{ key: "dashboard", href: routes.dashboard, label: "Open app", variant: "primary" }];
  }
  if (status === "authenticated") {
    return [{ key: "dashboard", href: routes.dashboard, label: "Dashboard", variant: "primary" }];
  }
  const actions: HeaderAction[] = [{ key: "login", href: routes.login, label: "Log in", variant: "secondary" }];
  if (meta?.registration_open !== false) {
    actions.push({ key: "register", href: routes.register, label: "Create account", variant: "primary" });
  }
  return actions;
}
