import { ButtonLink } from "@/components/ui/button";
import { Logo } from "@/components/brand/logo";

export default function NotFound() {
  return (
    <main className="grid min-h-dvh place-items-center px-4">
      <div className="text-center">
        <Logo className="justify-center" />
        <p className="mt-10 font-mono text-sm text-brand">404</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink">Page not found</h1>
        <p className="mt-3 text-muted">The page you are looking for does not exist or was removed.</p>
        <div className="mt-8 flex justify-center gap-3">
          <ButtonLink href="/dashboard/" variant="primary">
            Go to dashboard
          </ButtonLink>
          <ButtonLink href="/">Home</ButtonLink>
        </div>
      </div>
    </main>
  );
}
