"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ClipEditorLoader } from "@/components/editor/clip-editor";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { isUuid, routes } from "@/lib/routes";

function ClipEditorPageInner() {
  const params = useSearchParams();
  const projectId = params.get("project");
  const clipId = params.get("clip");
  if (!isUuid(projectId) || !isUuid(clipId)) {
    return <EmptyState title="Clip not found" description="The link is incomplete." action={<ButtonLink href={routes.clips}>All clips</ButtonLink>} />;
  }
  return <ClipEditorLoader key={clipId} projectId={projectId} clipId={clipId} />;
}

export default function ClipEditorPage() {
  return (
    <Suspense>
      <ClipEditorPageInner />
    </Suspense>
  );
}
