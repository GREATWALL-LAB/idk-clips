"use client";

import { useCallback, useEffect, useState } from "react";
import { Cpu, Laptop, Pencil, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/layout/app-shell";
import { PairingDialog } from "@/components/workers/pairing-dialog";
import { Badge, StatusDot } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { Alert, EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/progress";
import { useToast } from "@/components/ui/toast";
import { probeBridge } from "@/lib/api/bridge";
import { errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { Worker } from "@/lib/api/types";
import { formatRelative } from "@/lib/format";
import { usePolling } from "@/lib/hooks/use-polling";

const workersInterval = () => 10_000;

function EditWorkerDialog({ worker, onClose, onSaved }: { worker: Worker; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [name, setName] = useState(worker.name);
  const [model, setModel] = useState(worker.preferred_model ?? "");
  const [saving, setSaving] = useState(false);
  const models = worker.capabilities.ollama_models ?? [];
  async function save() {
    setSaving(true);
    try {
      await api.updateWorker(worker.id, { name: name.trim() || worker.name, preferred_model: model });
      toast.success("Worker updated.");
      onSaved();
      onClose();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }
  return (
    <Dialog
      open
      onClose={onClose}
      title="Worker settings"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={save} loading={saving}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Name" htmlFor="worker-name">
          <Input id="worker-name" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="AI model for finding clips" htmlFor="worker-model" hint="Chosen from the Ollama models installed on this worker. The worker's own Ollama is always used.">
          <Select id="worker-model" value={model} onChange={(e) => setModel(e.target.value)}>
            <option value="">Automatic (first installed model)</option>
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </Select>
        </Field>
      </div>
    </Dialog>
  );
}

function WorkerCard({ worker, here, onChanged }: { worker: Worker; here: boolean; onChanged: () => void }) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [removing, setRemoving] = useState(false);
  const components = worker.capabilities.components ?? [];
  const models = worker.capabilities.ollama_models ?? [];

  async function remove() {
    setRemoving(true);
    try {
      await api.deleteWorker(worker.id);
      toast.success(`“${worker.name}” was disconnected. Its credentials no longer work.`);
      setConfirm(false);
      onChanged();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setRemoving(false);
    }
  }

  return (
    <li className="surface-card p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-ink text-lime">
          <Laptop className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[15px] font-semibold text-ink">{worker.name}</h3>
            <Badge tone={worker.online ? "success" : "neutral"}>
              <StatusDot tone={worker.online ? "success" : "neutral"} pulse={worker.online} />
              {worker.online ? "Online" : "Offline"}
            </Badge>
            {here ? <Badge tone="lime">This computer</Badge> : null}
            {worker.active_jobs ? <Badge tone="brand">{worker.active_jobs} job(s)</Badge> : null}
          </div>
          <p className="text-xs text-subtle">
            {[worker.platform, worker.app_version && `v${worker.app_version}`, worker.capabilities.gpu ?? "CPU", worker.last_seen_at && `seen ${formatRelative(worker.last_seen_at)}`]
              .filter(Boolean)
              .join(" · ")}
          </p>
          {components.length ? (
            <ul className="flex flex-wrap gap-1.5">
              {components.map((c) => (
                <li key={c.key}>
                  <Badge tone={c.status === "ok" ? "success" : c.status === "misconfigured" ? "warning" : "danger"}>{c.name}</Badge>
                </li>
              ))}
            </ul>
          ) : null}
          <p className="text-xs text-subtle">
            AI model: <span className="font-mono text-ink">{worker.preferred_model ?? (models[0] ? `${models[0]} (automatic)` : "none installed")}</span>
          </p>
        </div>
        <div className="flex gap-2 sm:flex-col">
          <Button size="sm" onClick={() => setEditing(true)} icon={<Pencil className="size-3.5" aria-hidden="true" />}>
            Settings
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setConfirm(true)} icon={<Trash2 className="size-3.5" aria-hidden="true" />}>
            Disconnect
          </Button>
        </div>
      </div>
      {editing ? <EditWorkerDialog worker={worker} onClose={() => setEditing(false)} onSaved={onChanged} /> : null}
      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        onConfirm={remove}
        busy={removing}
        confirmLabel="Disconnect"
        title={`Disconnect “${worker.name}”?`}
        description="Its credentials stop working immediately and its waiting jobs are cancelled. Videos and clips stored on that computer are not deleted; remove them there with “worker purge”."
      />
    </li>
  );
}

export function WorkersView() {
  const fetcher = useCallback((signal: AbortSignal) => api.workers(signal), []);
  const { data, error, loading, refresh } = usePolling(fetcher, workersInterval);
  const [pairing, setPairing] = useState(false);
  const [here, setHere] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    let cancelled = false;
    (async () => {
      for (const worker of data.filter((w) => w.online)) {
        if (await probeBridge(worker.bridge_port, worker.id)) {
          if (!cancelled) setHere(worker.id);
          return;
        }
      }
      if (!cancelled) setHere(null);
    })();
    return () => {
      cancelled = true;
    };
  }, [data]);

  return (
    <>
      <PageHeader
        title="Workers"
        description="Your own computers that process your videos. The website coordinates; the work and the video files stay on your machines."
        actions={
          <Button variant="primary" onClick={() => setPairing(true)} icon={<Plus className="size-4" aria-hidden="true" />}>
            Connect a worker
          </Button>
        }
      />
      {error && !data ? <Alert className="mb-6">{errorMessage(error)}</Alert> : null}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0">
          {loading && !data ? (
            <Skeleton className="h-40" />
          ) : data && data.length === 0 ? (
            <EmptyState
              icon={<Cpu className="size-5" aria-hidden="true" />}
              title="No worker connected yet"
              description="Connect the computer you want to process videos on. You need a one-time code from this page and about a minute."
              action={
                <Button variant="primary" onClick={() => setPairing(true)}>
                  Connect a worker
                </Button>
              }
            />
          ) : (
            <ul className="space-y-3">
              {data?.map((worker) => (
                <WorkerCard key={worker.id} worker={worker} here={here === worker.id} onChanged={refresh} />
              ))}
            </ul>
          )}
        </div>
        <Card>
          <CardHeader icon={<ShieldCheck className="size-4" />} title="How workers stay safe" />
          <CardBody className="space-y-2.5 text-sm text-muted">
            <p>Pairing codes work once and expire after a few minutes.</p>
            <p>Each worker gets its own credential, stored only as a hash on the server. Disconnecting a worker revokes it instantly.</p>
            <p>A worker only receives jobs from your account and can only report results for those jobs. It cannot be told to run commands.</p>
            <p>Videos travel from your browser to the worker on the same computer, never through the website.</p>
          </CardBody>
        </Card>
      </div>
      {pairing ? (
        <PairingDialog
          open={pairing}
          onClose={() => {
            setPairing(false);
            refresh();
          }}
        />
      ) : null}
    </>
  );
}
