"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { BookOpen, Clapperboard, Cpu, FolderOpen, LayoutDashboard, LogOut, Menu, Monitor, Plus, Settings, X } from "lucide-react";
import { useAuth, useMode } from "@/components/auth/auth-provider";
import { Logo } from "@/components/brand/logo";
import { BackendStatusPill } from "@/components/status/backend-status";
import { ButtonLink } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

type NavItem = { href: string; match: string; label: string; icon: typeof LayoutDashboard; hybridOnly?: boolean };

const NAV: NavItem[] = [
  { href: routes.dashboard, match: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: routes.projects, match: "/projects", label: "Projects", icon: FolderOpen },
  { href: routes.clips, match: "/clips", label: "Clips", icon: Clapperboard },
  { href: routes.workers, match: "/workers", label: "Workers", icon: Cpu, hybridOnly: true },
  { href: routes.settings, match: "/settings", label: "Settings", icon: Settings },
];

function isActive(pathname: string, match: string) {
  return pathname === match || pathname.startsWith(`${match}/`);
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { hybrid } = useMode();
  return (
    <nav aria-label="Main" className="flex flex-col gap-1">
      {NAV.filter((item) => !item.hybridOnly || hybrid).map(({ href, match, label, icon: Icon }) => {
        const active = isActive(pathname, match);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
              active ? "bg-brand-50 text-brand-700" : "text-ink-soft hover:bg-mist hover:text-ink",
            )}
          >
            <Icon className={cn("size-[18px]", active ? "text-brand" : "text-subtle group-hover:text-ink")} aria-hidden="true" />
            {label}
          </Link>
        );
      })}
      <Link
        href={routes.docs}
        onClick={onNavigate}
        className="group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-ink-soft transition-colors hover:bg-mist hover:text-ink"
      >
        <BookOpen className="size-[18px] text-subtle group-hover:text-ink" aria-hidden="true" />
        Documentation
      </Link>
    </nav>
  );
}

function ModeNote() {
  const { mode } = useMode();
  if (!mode) return null;
  const text =
    mode === "local"
      ? { title: "Local mode", body: "Everything runs and stays on this computer." }
      : mode === "hybrid"
        ? { title: "Online", body: "Videos are processed on your own connected computer." }
        : { title: "Server", body: "Videos are processed on this IDK Clips server." };
  return (
    <div className="rounded-xl border border-line bg-canvas px-3 py-2.5">
      <p className="flex items-center gap-1.5 text-xs font-semibold text-ink">
        <Monitor className="size-3.5 text-brand" aria-hidden="true" /> {text.title}
      </p>
      <p className="mt-0.5 text-xs text-subtle">{text.body}</p>
    </div>
  );
}

function UserMenu() {
  const auth = useAuth();
  const { local } = useMode();
  const router = useRouter();
  if (auth.status !== "authenticated" || local) return null;
  const initials = auth.user.display_name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <div className="flex items-center gap-3 rounded-xl border border-line bg-surface p-2.5">
      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-ink text-xs font-semibold text-lime" aria-hidden="true">
        {initials || "U"}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium text-ink">{auth.user.display_name}</p>
        <p className="truncate text-xs text-subtle">{auth.user.email}</p>
      </div>
      <button
        type="button"
        onClick={async () => {
          await auth.signOut();
          router.replace(routes.login);
        }}
        className="grid size-8 place-items-center rounded-lg text-subtle transition-colors hover:bg-mist hover:text-ink"
        aria-label="Log out"
        title="Log out"
      >
        <LogOut className="size-4" aria-hidden="true" />
      </button>
    </div>
  );
}

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      <ButtonLink href={routes.newProject} variant="primary" className="mt-6" onClick={onNavigate} icon={<Plus className="size-4" aria-hidden="true" />}>
        New project
      </ButtonLink>
      <div className="mt-6">
        <NavLinks onNavigate={onNavigate} />
      </div>
      <div className="mt-auto space-y-2 pt-6">
        <ModeNote />
        <BackendStatusPill />
        <UserMenu />
      </div>
    </>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  // The drawer remembers the route it was opened on, so navigating closes it automatically.
  const [openedOn, setOpenedOn] = useState<string | null>(null);
  const mobileOpen = openedOn === pathname;
  const setMobileOpen = (open: boolean) => setOpenedOn(open ? pathname : null);

  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpenedOn(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  return (
    <div className="relative min-h-dvh bg-canvas">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-4 focus:py-2 focus:shadow-lift"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-line bg-surface px-4 py-5 lg:flex">
        <Link href={routes.home} className="px-2" aria-label="IDK Clips home">
          <Logo />
        </Link>
        <SidebarBody />
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-surface/95 px-4 lg:hidden">
        <Link href={routes.home} aria-label="IDK Clips home">
          <Logo />
        </Link>
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="grid size-10 place-items-center rounded-xl text-ink hover:bg-mist"
          aria-label="Open navigation"
          aria-expanded={mobileOpen}
          aria-controls="mobile-nav"
        >
          <Menu className="size-5" aria-hidden="true" />
        </button>
      </header>

      {/* Mobile drawer */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation" id="mobile-nav">
          <button type="button" className="absolute inset-0 bg-ink/40" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />
          <div className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] animate-fade-up flex-col overflow-y-auto border-r border-line bg-surface px-4 py-5">
            <div className="flex items-center justify-between px-2">
              <Logo />
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="grid size-9 place-items-center rounded-lg text-subtle hover:bg-mist hover:text-ink"
                aria-label="Close navigation"
              >
                <X className="size-5" aria-hidden="true" />
              </button>
            </div>
            <SidebarBody onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      <main id="main" className="lg:pl-64">
        <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-10">{children}</div>
      </main>
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="font-display text-[28px] font-bold leading-tight tracking-tight text-ink sm:text-[32px]">{title}</h1>
        {description ? <p className="mt-1.5 max-w-2xl text-sm text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}
