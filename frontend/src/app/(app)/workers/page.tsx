"use client";

import { useMode } from "@/components/auth/auth-provider";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { WorkersView } from "@/components/workers/workers-view";
import { routes } from "@/lib/routes";

export default function WorkersPage() {
  const { hybrid, mode } = useMode();
  if (mode && !hybrid) {
    return (
      <EmptyState
        title="Workers are not used here"
        description={
          mode === "local"
            ? "In local mode this computer does all the processing itself, so there is nothing to connect."
            : "This server processes videos itself."
        }
        action={<ButtonLink href={routes.dashboard}>Back to the dashboard</ButtonLink>}
      />
    );
  }
  return <WorkersView />;
}
