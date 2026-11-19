"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert } from "@/components/ui/empty-state";
import { Field, Input } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { errorMessage } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import { formatTimestamp, parseTimestamp } from "@/lib/format";

/** Create a clip by hand, prefilled from the video's current playback position. */
export function AddClipDialog({
  open,
  onClose,
  projectId,
  start,
  duration,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  start: number;
  duration: number;
  onCreated: () => void;
}) {
  const toast = useToast();
  const [title, setTitle] = useState("Custom clip");
  const [startText, setStartText] = useState(formatTimestamp(start));
  const [endText, setEndText] = useState(formatTimestamp(Math.min(start + 30, duration)));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const s = parseTimestamp(startText);
    const e = parseTimestamp(endText);
    if (s === null || e === null) return setError("Use times like 1:23.5 or 83.5.");
    if (e <= s) return setError("The end must be after the start.");
    if (e - s < 3) return setError("Clips must be at least 3 seconds long.");
    if (e > duration + 0.05) return setError(`The video is only ${formatTimestamp(duration)} long.`);
    setSaving(true);
    setError(null);
    try {
      await api.createClip(projectId, { title: title.trim() || "Custom clip", start_seconds: s, end_seconds: e });
      toast.success("Clip added.");
      onCreated();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Add a clip" description="Pick the start and end of the moment you want to export.">
      <form onSubmit={onSubmit} className="space-y-4">
        {error ? <Alert>{error}</Alert> : null}
        <Field label="Title" htmlFor="clip-title">
          <Input id="clip-title" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Start" htmlFor="clip-start" hint="m:ss.s">
            <Input id="clip-start" className="font-mono" value={startText} onChange={(e) => setStartText(e.target.value)} />
          </Field>
          <Field label="End" htmlFor="clip-end" hint="m:ss.s">
            <Input id="clip-end" className="font-mono" value={endText} onChange={(e) => setEndText(e.target.value)} />
          </Field>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={saving}>
            Add clip
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
