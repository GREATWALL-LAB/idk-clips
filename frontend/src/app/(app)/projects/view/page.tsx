"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ProjectView } from "@/components/projects/project-view";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { isUuid, routes } from "@/lib/routes";

function ProjectPageInner() {
  const id = useSearchParams().get("id");
  if (!isUuid(id)) {
    return <EmptyState title="Project not found" description="The link is incomplete." action={<ButtonLink href={routes.projects}>Back to projects</ButtonLink>} />;
  }
  return <ProjectView key={id} projectId={id} />;
}

export default function ProjectPage() {
  return (
    <Suspense>
      <ProjectPageInner />
    </Suspense>
  );
}
