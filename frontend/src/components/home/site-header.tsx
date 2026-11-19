"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { GitFork, Menu, X } from "lucide-react";
import { useOptionalAuth } from "@/components/auth/auth-provider";
import { Logo } from "@/components/brand/logo";
import { ButtonLink } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { publicLinks } from "@/lib/config";
import { headerActions } from "@/lib/header-actions";
import { routes } from "@/lib/routes";

export const HOME_NAV = [
  { href: "/#features", label: "Features" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#run-locally", label: "Run locally" },
  { href: "/#use-online", label: "Use online" },
  { href: "/#open-source", label: "Open source" },
  { href: routes.docs, label: "Docs" },
];

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const github = publicLinks().github;
  const auth = useOptionalAuth();
  const actions = headerActions(auth?.status ?? null, auth?.meta ?? null);
  const login = actions.find((action) => action.key === "login");

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className={cn("sticky top-0 z-40 transition-colors duration-300", scrolled || open ? "border-b border-line bg-canvas/95" : "border-b border-transparent")}>
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
        <Link href={routes.home} aria-label="IDK Clips home" className="shrink-0" onClick={() => setOpen(false)}>
          <Logo />
        </Link>
        <nav aria-label="Primary" className="hidden min-w-0 items-center gap-0.5 xl:flex">
          {HOME_NAV.map((item) => (
            <Link key={item.href} href={item.href} className="whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium text-ink-soft transition-colors hover:bg-mist hover:text-ink">
              {item.label}
            </Link>
          ))}
          {github ? (
            <a href={github} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-ink-soft transition-colors hover:bg-mist hover:text-ink" rel="noopener">
              <GitFork className="size-4" aria-hidden="true" /> GitHub
            </a>
          ) : null}
        </nav>
        <div className="flex shrink-0 items-center gap-2" data-testid="header-actions">
          {/* Phones: "Log in" stays in the bar, everything else is in the menu. The wrappers
              own the visibility, because buttons always set their own display. */}
          {login ? (
            <div className="sm:hidden">
              <ButtonLink href={login.href} variant="secondary" size="sm">
                {login.label}
              </ButtonLink>
            </div>
          ) : null}
          <div className="hidden items-center gap-2 sm:flex">
            {actions.map((action) => (
              <ButtonLink key={action.key} href={action.href} variant={action.variant} size="sm">
                {action.label}
              </ButtonLink>
            ))}
          </div>
          <button
            type="button"
            className="grid size-10 place-items-center rounded-xl text-ink hover:bg-mist xl:hidden"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            aria-controls="site-menu"
            onClick={() => setOpen(!open)}
          >
            {open ? <X className="size-5" aria-hidden="true" /> : <Menu className="size-5" aria-hidden="true" />}
          </button>
        </div>
      </div>
      {open ? (
        <nav id="site-menu" aria-label="Primary" className="max-h-[calc(100dvh-4rem)] overflow-y-auto border-t border-line bg-canvas px-4 pb-5 pt-2 xl:hidden">
          <ul className="space-y-1">
            {HOME_NAV.map((item) => (
              <li key={item.href}>
                <Link href={item.href} onClick={() => setOpen(false)} className="block rounded-xl px-3 py-3 text-base font-medium text-ink hover:bg-mist">
                  {item.label}
                </Link>
              </li>
            ))}
            {github ? (
              <li>
                <a href={github} className="block rounded-xl px-3 py-3 text-base font-medium text-ink hover:bg-mist" rel="noopener">
                  GitHub
                </a>
              </li>
            ) : null}
          </ul>
          <div className={cn("mt-3 grid gap-2", actions.length > 1 && "sm:grid-cols-2")}>
            {actions.map((action) => (
              <ButtonLink key={action.key} href={action.href} variant={action.variant} className="w-full" onClick={() => setOpen(false)}>
                {action.label}
              </ButtonLink>
            ))}
          </div>
        </nav>
      ) : null}
    </header>
  );
}
