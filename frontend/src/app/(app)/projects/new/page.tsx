import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/app-shell";
import { ImportForm } from "@/components/projects/import-form";

export const metadata: Metadata = { title: "New project" };

export default function NewProjectPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="New project" description="Upload a long video. IDK Clips will transcribe it and suggest the best short clips." />
      <ImportForm />
    </div>
  );
}
