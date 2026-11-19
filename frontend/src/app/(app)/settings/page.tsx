"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState, type FormEvent } from "react";
import { Cpu, Database, KeyRound, UserRound } from "lucide-react";
import { useAuth, useMode } from "@/components/auth/auth-provider";
import { PageHeader } from "@/components/layout/app-shell";
import { AISettingsCard } from "@/components/settings/ai-settings-card";
import { SystemStatusPanel } from "@/components/status/system-status-panel";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { Alert } from "@/components/ui/empty-state";
import { Field, Input, Select } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/progress";
import { useToast } from "@/components/ui/toast";
import { errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import { formatBytes } from "@/lib/format";
import { usePolling } from "@/lib/hooks/use-polling";
import { routes } from "@/lib/routes";

const RETENTION_OPTIONS = [
  { value: 0, label: "Keep until I delete them" },
  { value: 1, label: "Delete after 1 day" },
  { value: 7, label: "Delete after 7 days" },
  { value: 30, label: "Delete after 30 days" },
  { value: 90, label: "Delete after 90 days" },
];

function PasswordForm() {
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mismatch = confirm.length > 0 && confirm !== next;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (mismatch) return;
    setSaving(true);
    setError(null);
    try {
      await api.changePassword(current, next);
      setCurrent("");
      setNext("");
      setConfirm("");
      toast.success("Password changed. Your other sessions were logged out.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      {error ? <Alert>{error}</Alert> : null}
      <Field label="Current password" htmlFor="current-password">
        <Input id="current-password" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="New password" htmlFor="new-password" hint="At least 10 characters.">
          <Input id="new-password" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
        </Field>
        <Field label="Confirm new password" htmlFor="confirm-password" error={mismatch ? "The passwords do not match." : null}>
          <Input id="confirm-password" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </Field>
      </div>
      <div className="flex justify-end">
        <Button type="submit" loading={saving} disabled={!current || next.length < 10 || mismatch}>
          Change password
        </Button>
      </div>
    </form>
  );
}

function DataCard() {
  const toast = useToast();
  const router = useRouter();
  const auth = useAuth();
  const { hybrid } = useMode();
  const fetcher = useCallback((signal: AbortSignal) => api.account(signal), []);
  const account = usePolling(fetcher, null);
  const [saving, setSaving] = useState(false);
  const [confirmProjects, setConfirmProjects] = useState(false);
  const [deletingProjects, setDeletingProjects] = useState(false);
  const [accountDialog, setAccountDialog] = useState(false);
  const [password, setPassword] = useState("");
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [accountError, setAccountError] = useState<string | null>(null);

  async function setRetention(days: number) {
    setSaving(true);
    try {
      await api.updateAccount({ retention_days: days });
      toast.success(days ? `Source videos will be deleted ${days} day(s) after upload.` : "Source videos are kept until you delete them.");
      account.refresh();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  async function deleteProjects() {
    setDeletingProjects(true);
    try {
      const result = await api.deleteAllProjects();
      toast.success(`${result.deleted_projects} project(s) deleted.`);
      setConfirmProjects(false);
      account.refresh();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setDeletingProjects(false);
    }
  }

  async function deleteAccount(event: FormEvent) {
    event.preventDefault();
    setDeletingAccount(true);
    setAccountError(null);
    try {
      await api.deleteAccount(password);
      await auth.signOut().catch(() => undefined);
      router.replace(routes.home);
    } catch (error) {
      setAccountError(errorMessage(error));
      setDeletingAccount(false);
    }
  }

  const data = account.data;
  return (
    <Card>
      <CardHeader icon={<Database className="size-4" />} title="Your data" description="What is stored, for how long, and how to delete it." />
      <CardBody className="space-y-5">
        {!data ? (
          <Skeleton className="h-32" />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-2xl bg-canvas p-3">
                <p className="text-xs text-subtle">Projects</p>
                <p className="mt-1 font-display text-xl font-bold text-ink">{data.projects}</p>
              </div>
              <div className="rounded-2xl bg-canvas p-3">
                <p className="text-xs text-subtle">{hybrid ? "Files on your workers" : "Storage used"}</p>
                <p className="mt-1 font-display text-xl font-bold text-ink">{formatBytes(data.storage_used_bytes)}</p>
              </div>
            </div>
            <Field
              label="Source video retention"
              htmlFor="retention"
              hint="Only the long source video is removed. Transcripts, clip lists and exported clips stay until you delete them."
            >
              <Select id="retention" value={data.retention_days} disabled={saving} onChange={(e) => void setRetention(Number(e.target.value))}>
                {RETENTION_OPTIONS.some((o) => o.value === data.retention_days) ? null : (
                  <option value={data.retention_days}>Delete after {data.retention_days} days</option>
                )}
                {RETENTION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="flex flex-wrap gap-2 border-t border-line pt-5">
              <Button variant="danger" size="sm" onClick={() => setConfirmProjects(true)} disabled={data.projects === 0}>
                Delete all projects
              </Button>
              {data.can_delete_account ? (
                <Button variant="ghost" size="sm" onClick={() => setAccountDialog(true)}>
                  Delete my account
                </Button>
              ) : null}
            </div>
          </>
        )}
      </CardBody>
      <ConfirmDialog
        open={confirmProjects}
        onClose={() => setConfirmProjects(false)}
        onConfirm={deleteProjects}
        busy={deletingProjects}
        confirmLabel="Delete everything"
        title="Delete all projects?"
        description="Every project, transcript, clip and exported file is deleted. This cannot be undone."
      />
      <Dialog open={accountDialog} onClose={() => setAccountDialog(false)} title="Delete your account?" description="Your account, projects and clips are deleted and your workers are disconnected. This cannot be undone.">
        <form onSubmit={deleteAccount} className="space-y-4">
          {accountError ? <Alert>{accountError}</Alert> : null}
          <Field label="Confirm with your password" htmlFor="delete-password">
            <Input id="delete-password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setAccountDialog(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="danger" loading={deletingAccount} disabled={!password}>
              Delete my account
            </Button>
          </div>
        </form>
      </Dialog>
    </Card>
  );
}

export default function SettingsPage() {
  const auth = useAuth();
  const { local, hybrid } = useMode();
  return (
    <>
      <PageHeader title="Settings" description={local ? "AI configuration, your data and the status of this computer." : "AI configuration, your account, your data and the status of this installation."} />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-6">
          {hybrid ? (
            <Card>
              <CardHeader icon={<Cpu className="size-4" />} title="AI runs on your worker" description="Each worker uses its own Ollama and models. Nothing is sent to an AI service by this website." />
              <CardBody>
                <ButtonLink href={routes.workers} size="sm">
                  Choose a model per worker
                </ButtonLink>
              </CardBody>
            </Card>
          ) : (
            <AISettingsCard />
          )}
          <DataCard />
          {!local ? (
            <Card>
              <CardHeader icon={<KeyRound className="size-4" />} title="Password" description="Changing your password logs out your other sessions." />
              <CardBody>
                <PasswordForm />
              </CardBody>
            </Card>
          ) : null}
        </div>
        <div className="space-y-6">
          {auth.status === "authenticated" && !local ? (
            <Card>
              <CardHeader icon={<UserRound className="size-4" />} title="Account" />
              <CardBody className="space-y-2 text-sm">
                <div className="flex justify-between gap-3">
                  <span className="text-muted">Name</span>
                  <span className="text-ink">{auth.user.display_name}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-muted">Email</span>
                  <span className="truncate text-ink">{auth.user.email}</span>
                </div>
              </CardBody>
            </Card>
          ) : null}
          {!hybrid ? <SystemStatusPanel /> : null}
          <Card>
            <CardBody className="space-y-1.5 text-xs text-subtle">
              <p>
                <span className="font-medium text-ink">IDK Clips</span> is free, open-source software under the MIT License.
              </p>
              <p>No subscriptions and no paid features. Speech is transcribed with faster-whisper and clips are rendered with FFmpeg.</p>
            </CardBody>
          </Card>
        </div>
      </div>
    </>
  );
}
