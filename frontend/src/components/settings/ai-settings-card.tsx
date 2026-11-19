"use client";

import { useCallback, useState } from "react";
import { BrainCircuit, CircleCheck, CircleAlert, Cloud, Cpu, RefreshCw } from "lucide-react";
import { Badge, StatusDot } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Alert } from "@/components/ui/empty-state";
import { Field, Input, SegmentedControl, Select } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/progress";
import { useToast } from "@/components/ui/toast";
import { errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import type { AIProvider, AISettings, AIStatus } from "@/lib/api/types";
import { formatBytes } from "@/lib/format";
import { usePolling } from "@/lib/hooks/use-polling";

function Code({ children }: { children: string }) {
  return <code className="rounded-md bg-mist px-1.5 py-0.5 font-mono text-[12px] text-ink">{children}</code>;
}

function AIForm({ settings, status, onSaved }: { settings: AISettings; status: AIStatus; onSaved: () => void }) {
  const toast = useToast();
  const [provider, setProvider] = useState<AIProvider>(settings.provider);
  const [endpoint, setEndpoint] = useState(settings.ollama_base_url);
  const [model, setModel] = useState(settings.ollama_model ?? status.ollama.selected_model ?? "");
  const [saving, setSaving] = useState(false);
  const endpointEditable = settings.can_change_endpoint;
  const dirty = provider !== settings.provider || endpoint !== settings.ollama_base_url || (model || null) !== (settings.ollama_model ?? status.ollama.selected_model ?? null);

  async function save() {
    setSaving(true);
    try {
      await api.updateAiSettings({ provider, ...(endpointEditable ? { ollama_base_url: endpoint } : {}), ...(model ? { ollama_model: model } : {}) });
      toast.success("AI settings saved.");
      onSaved();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5">
      {settings.scope === "account" ? (
        <p className="text-sm text-muted">These choices apply to your projects only. Other people on this server keep their own.</p>
      ) : null}
      <SegmentedControl<AIProvider>
        label="AI provider"
        value={provider}
        onChange={setProvider}
        options={[
          { value: "ollama", label: "Local (Ollama)", icon: <Cpu className="size-3.5" aria-hidden="true" /> },
          { value: "external", label: "External provider", icon: <Cloud className="size-3.5" aria-hidden="true" /> },
        ]}
      />

      {provider === "ollama" ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {status.ollama.reachable ? (
              <Badge tone="success">
                <StatusDot tone="success" /> Connected{status.ollama.version ? ` · Ollama ${status.ollama.version}` : ""}
              </Badge>
            ) : (
              <Badge tone="danger">
                <StatusDot tone="danger" /> Not reachable
              </Badge>
            )}
            <span className="text-subtle">{status.ollama.models.length} model(s) installed</span>
          </div>
          {status.ollama.message ? <Alert tone="warning">{status.ollama.message}</Alert> : null}
          <Field
            label="Ollama endpoint"
            htmlFor="ollama-url"
            hint={endpointEditable ? "Usually http://127.0.0.1:11434 when Ollama runs on this computer." : "Set by the server's configuration (OPENCLIP_OLLAMA_BASE_URL)."}
          >
            <Input id="ollama-url" value={endpoint} disabled={!endpointEditable} onChange={(e) => setEndpoint(e.target.value)} />
          </Field>
          <Field label="Model used to find clips" htmlFor="ollama-model" hint="Larger models usually pick better clips but run slower. 7–14B models suit 8 GB GPUs.">
            <Select id="ollama-model" value={model} disabled={status.ollama.models.length === 0} onChange={(e) => setModel(e.target.value)}>
              {status.ollama.models.length === 0 ? <option value="">No models installed</option> : null}
              {status.ollama.models.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name}
                  {m.parameter_size ? ` · ${m.parameter_size}` : ""}
                  {m.size_bytes ? ` · ${formatBytes(m.size_bytes)}` : ""}
                </option>
              ))}
            </Select>
          </Field>
          <div className="rounded-2xl border border-line bg-canvas p-4 text-sm text-muted">
            <p className="font-medium text-ink">Setting up Ollama</p>
            <ol className="mt-2 list-decimal space-y-1.5 pl-5">
              <li>
                Install it from <span className="text-ink">ollama.com</span> and start it (the app, or <Code>ollama serve</Code>).
              </li>
              <li>
                Download a model, for example <Code>ollama pull gemma3:4b</Code> or <Code>ollama pull qwen2.5:7b</Code>.
              </li>
              <li>Choose it above and save.</li>
            </ol>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {status.external.configured ? (
            <Alert tone="success" title={`${status.external.name} is configured`}>
              Model <span className="font-mono">{status.external.model}</span>
              {settings.external_base_url_host ? ` on ${settings.external_base_url_host}` : ""}. Transcripts will be sent to this provider when finding clips.
            </Alert>
          ) : (
            <Alert tone="warning" title="No external provider is configured">
              External AI is optional. Whoever runs this server can connect any OpenAI-compatible service in its configuration.
            </Alert>
          )}
          <div className="rounded-2xl border border-line bg-canvas p-4 text-sm text-muted">
            <p className="font-medium text-ink">Configure it on the server (never in the browser)</p>
            <p className="mt-2">Set these in the backend&apos;s <Code>.env</Code> file and restart the backend:</p>
            <ul className="mt-2 space-y-1 font-mono text-[12px] text-ink-soft">
              <li>OPENCLIP_EXTERNAL_AI_BASE_URL=https://api.example.com/v1</li>
              <li>OPENCLIP_EXTERNAL_AI_MODEL=model-name</li>
              <li>OPENCLIP_EXTERNAL_AI_API_KEY=… (kept on the server)</li>
            </ul>
            <p className="mt-2">The API key is never sent to the browser or shown here.</p>
          </div>
        </div>
      )}

      <div className="flex justify-end">
        <Button variant="primary" onClick={save} loading={saving} disabled={!dirty || (provider === "external" && !status.external.configured)}>
          Save AI settings
        </Button>
      </div>
    </div>
  );
}

export function AISettingsCard() {
  const settingsFetcher = useCallback((signal: AbortSignal) => api.aiSettings(signal), []);
  const statusFetcher = useCallback((signal: AbortSignal) => api.aiStatus(signal), []);
  const settings = usePolling(settingsFetcher, null);
  const status = usePolling(statusFetcher, null);
  const [version, setVersion] = useState(0);

  const reload = () => {
    settings.refresh();
    status.refresh();
    setVersion((v) => v + 1);
  };

  return (
    <Card>
      <CardHeader
        icon={<BrainCircuit className="size-4" />}
        title="AI configuration"
        description="Which AI model finds the best moments in your transcripts."
        action={
          <Button size="sm" variant="ghost" onClick={reload} icon={<RefreshCw className="size-3.5" aria-hidden="true" />}>
            Refresh
          </Button>
        }
      />
      <CardBody>
        {settings.error || status.error ? (
          <Alert>{errorMessage(settings.error || status.error)}</Alert>
        ) : settings.data && status.data ? (
          <AIForm key={`${version}-${settings.data.provider}-${settings.data.ollama_model}`} settings={settings.data} status={status.data} onSaved={reload} />
        ) : (
          <Skeleton className="h-64" />
        )}
        <p className="mt-5 flex items-start gap-2 text-xs text-subtle">
          {status.data?.provider === "external" ? (
            <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          ) : (
            <CircleCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          )}
          {status.data?.provider === "external"
            ? "With an external provider, transcript text leaves this server. Videos never do."
            : "With Ollama, transcripts and videos stay on this machine."}
        </p>
      </CardBody>
    </Card>
  );
}
